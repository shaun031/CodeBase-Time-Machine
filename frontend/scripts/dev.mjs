import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const frontendDirectory = path.resolve(scriptDirectory, "..");
const projectRoot = path.resolve(frontendDirectory, "..");

function readRootEnvironment(name) {
  const environmentFile = path.join(projectRoot, ".env");
  if (!fs.existsSync(environmentFile)) return undefined;
  const prefix = `${name}=`;
  const line = fs
    .readFileSync(environmentFile, "utf8")
    .split(/\r?\n/)
    .find((value) => value.startsWith(prefix));
  if (!line) return undefined;
  const value = line.slice(prefix.length).trim();
  if (
    (value.startsWith('"') && value.endsWith('"')) ||
    (value.startsWith("'") && value.endsWith("'"))
  ) {
    return value.slice(1, -1);
  }
  return value;
}

function portIsAvailable(port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.unref();
    server.once("error", () => resolve(false));
    server.listen({ host: "127.0.0.1", port }, () => {
      server.close(() => resolve(true));
    });
  });
}

function stopComposeFrontend() {
  const status = spawnSync(
    "docker",
    ["compose", "ps", "--services", "--filter", "status=running"],
    { cwd: projectRoot, encoding: "utf8", windowsHide: true },
  );
  if (status.status !== 0) return false;
  const services = status.stdout.split(/\r?\n/).filter(Boolean);
  if (!services.includes("frontend")) return false;
  console.log(
    "Port 3000 is used by the Docker frontend; stopping that service...",
  );
  const stopped = spawnSync("docker", ["compose", "stop", "frontend"], {
    cwd: projectRoot,
    stdio: "inherit",
    windowsHide: true,
  });
  return stopped.status === 0;
}

function resolveNextCli() {
  try {
    return require.resolve("next/dist/bin/next");
  } catch {
    console.log("Installing locked frontend dependencies...");
    const npm = process.platform === "win32" ? "npm.cmd" : "npm";
    const command = fs.existsSync(
      path.join(frontendDirectory, "package-lock.json"),
    )
      ? "ci"
      : "install";
    const installed = spawnSync(npm, [command], {
      cwd: frontendDirectory,
      stdio: "inherit",
      windowsHide: true,
    });
    if (installed.status !== 0) {
      console.error("Frontend dependency installation failed.");
      process.exit(installed.status ?? 1);
    }
    return require.resolve("next/dist/bin/next");
  }
}

if (!(await portIsAvailable(3000))) {
  stopComposeFrontend();
  for (
    let attempt = 0;
    attempt < 10 && !(await portIsAvailable(3000));
    attempt += 1
  ) {
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
}

if (!(await portIsAvailable(3000))) {
  console.error(
    "Port 3000 is already in use. Stop the existing frontend process and retry.",
  );
  process.exit(1);
}

const nextCli = resolveNextCli();
const childEnvironment = { ...process.env };
const apiBaseUrl = readRootEnvironment("NEXT_PUBLIC_API_BASE_URL");
if (apiBaseUrl) childEnvironment.NEXT_PUBLIC_API_BASE_URL = apiBaseUrl;
const child = spawn(
  process.execPath,
  [nextCli, "dev", "--hostname", "127.0.0.1", "--port", "3000"],
  { cwd: frontendDirectory, env: childEnvironment, stdio: "inherit" },
);

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => child.kill(signal));
}

child.on("error", (error) => {
  console.error(`Could not start Next.js: ${error.message}`);
  process.exit(1);
});
child.on("exit", (code) => process.exit(code ?? 0));
