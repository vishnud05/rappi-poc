import assert from "node:assert/strict";
import test from "node:test";
import { api, ApiError } from "./api.ts";

test("API reads stay fresh and distinguish missing runs from retryable failures", async () => {
  const originalFetch = globalThis.fetch;
  try {
    globalThis.fetch = async (url, options) => {
      assert.equal(url, "/api/runs/example");
      assert.equal(options.cache, "no-store");
      return Response.json({ id: "example" });
    };
    assert.deepEqual(await api("/runs/example"), { id: "example" });
    for (const status of [404, 409, 503]) {
      globalThis.fetch = async () => Response.json({ detail: "Run unavailable" }, { status });
      await assert.rejects(api("/runs/example"), (error) => error instanceof ApiError && error.status === status && error.message === "Run unavailable");
    }
    globalThis.fetch = async () => new Response("<html>Proxy unavailable</html>", { status: 502 });
    await assert.rejects(api("/runs/example"), (error) => error instanceof ApiError && error.status === 502 && !error.message.includes("<html>"));
  } finally {
    globalThis.fetch = originalFetch;
  }
});
