import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "@/lib/api";
afterEach(() => vi.unstubAllGlobals());

describe("API client", () => {
  it("preserves real degraded dependency status", async () => {
    const status = {
      backend: "ok",
      database: "unavailable",
      redis: "ok",
      ollama: "ok",
    };
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify(status), { status: 503 }),
        ),
    );
    expect(await api.getSystemStatus()).toEqual(status);
  });
  it("accepts Redis as optional in native local mode", async () => {
    const status = {
      backend: "ok",
      database: "ok",
      redis: "not_required",
      ollama: "unavailable",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify(status))),
    );
    expect(await api.getSystemStatus()).toEqual(status);
  });
  it("accepts the dedicated AI status response without system-status validation", async () => {
    const status = {
      provider: "ollama",
      available: true,
      base_url_safe: "http://127.0.0.1:11434",
      llm_model: "qwen3:4b",
      llm_model_available: true,
      embedding_model: "all-minilm",
      embedding_model_available: true,
      message: null,
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify(status))),
    );
    expect(await api.getAIStatus()).toEqual(status);
  });
  it("rejects unrelated errors instead of displaying healthy services", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: { code: "INTERNAL_ERROR" } }), {
          status: 503,
        }),
      ),
    );
    await expect(api.getSystemStatus()).rejects.toBeInstanceOf(ApiError);
  });
  it("rejects malformed success responses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}")));
    await expect(api.getSystemStatus()).rejects.toThrow(
      "Invalid system status response",
    );
  });
  it("fetches the health endpoint", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ status: "ok", service: "codebase-time-machine" }),
        ),
      );
    vi.stubGlobal("fetch", fetcher);
    expect((await api.getHealth()).status).toBe("ok");
    expect(fetcher.mock.calls[0][0]).toContain("/api/health");
  });
});
