"use client";
import { useSystemStatus } from "@/hooks/use-system-status";

export function SystemStatus() {
  const { data, isError, isPending } = useSystemStatus();
  return (
    <div className="status-bar" role="status" aria-live="polite">
      <span className="mono status-label">LOCAL SERVICES</span>
      {(["backend", "database", "redis"] as const).map((service) => {
        const state = isPending
          ? "checking"
          : isError
            ? service === "backend"
              ? "unreachable"
              : "unknown"
            : (data?.[service] ?? "unknown");
        return (
          <span className="service" key={service}>
            <span
              className={`dot ${state === "ok" ? "online" : state === "unavailable" || state === "unreachable" ? "offline" : ""}`}
            />
            {service}
            {state === "not_required" && " (optional)"}
            <span className="sr-only">: {state.replace("_", " ")}</span>
          </span>
        );
      })}
      {isError && <span className="status-note">Backend unreachable</span>}
      {!isError &&
        data &&
        (data.database !== "ok" || data.redis === "unavailable") && (
          <span className="status-note">Some services unavailable</span>
        )}
    </div>
  );
}
