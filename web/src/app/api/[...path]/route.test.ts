// @vitest-environment node
import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GET, POST } from "./route";

const context = (path: string[]) => ({ params: Promise.resolve({ path }) });

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("API proxy", () => {
  it("проксирует путь и query на API_URL, убирая hop-by-hop заголовки и cookie", async () => {
    vi.stubEnv("API_URL", "http://api.internal:8000/");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response('{"ok":true}', {
        status: 200,
        headers: {
          "content-type": "application/json",
          "transfer-encoding": "chunked",
          "set-cookie": "x=1",
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const request = new NextRequest("http://localhost:3000/api/checks/abc?x=1", {
      headers: { cookie: "NEXT_LOCALE=kk", connection: "keep-alive", "x-request-id": "r1" },
    });
    const response = await GET(request, context(["checks", "abc"]));
    const [url, init] = fetchMock.mock.calls[0] as [URL, RequestInit];
    expect(url.toString()).toBe("http://api.internal:8000/api/checks/abc?x=1");
    const sent = new Headers(init.headers);
    expect(sent.get("cookie")).toBeNull();
    expect(sent.get("connection")).toBeNull();
    expect(sent.get("x-request-id")).toBe("r1");
    expect(init.body).toBeUndefined();
    expect(response.status).toBe(200);
    expect(response.headers.get("set-cookie")).toBeNull();
    expect(await response.json()).toEqual({ ok: true });
  });

  it("передаёт тело POST потоком и сохраняет статус ответа", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 202 }));
    vi.stubGlobal("fetch", fetchMock);
    const form = new FormData();
    form.set("profile_id", "p");
    const request = new NextRequest("http://localhost:3000/api/checks", {
      method: "POST",
      body: form,
    });
    const response = await POST(request, context(["checks"]));
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit & { duplex?: string };
    expect(init.method).toBe("POST");
    expect(init.duplex).toBe("half");
    expect(init.body).toBeInstanceOf(ReadableStream);
    expect(response.status).toBe(202);
  });

  it("экранирует сегменты пути", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}"));
    vi.stubGlobal("fetch", fetchMock);
    await GET(new NextRequest("http://localhost:3000/api/x"), context(["checks", "../admin"]));
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(
      "http://localhost:8000/api/checks/..%2Fadmin",
    );
  });

  it("недоступный бэкенд → 502 в формате ошибок API", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));
    const response = await GET(
      new NextRequest("http://localhost:3000/api/profiles"),
      context(["profiles"]),
    );
    expect(response.status).toBe(502);
    expect(await response.json()).toMatchObject({ error: { code: "upstream_unavailable" } });
  });
});
