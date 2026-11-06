import { afterEach, describe, expect, it, vi } from "vitest";
import { createCheck, deleteCheck, getCheck, listProfiles } from "./client";
import { ApiError } from "./errors";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const status = {
  id: "abc",
  status: "queued",
  step: null,
  steps: [],
  filename: "a.docx",
  profile_id: "p",
  created_at: "2026-10-25T10:00:00Z",
  updated_at: "2026-10-25T10:00:00Z",
  expires_at: null,
  error: null,
  report: null,
  annotated_url: null,
};

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("createCheck отправляет multipart-форму на /api/checks", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(status, 202));
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["x"], "a.docx");
    const result = await createCheck({ file, profileId: "p", annotate: true });
    expect(result.id).toBe("abc");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/checks");
    expect(init.method).toBe("POST");
    const form = init.body as FormData;
    expect(form.get("profile_id")).toBe("p");
    expect(form.get("annotate")).toBe("true");
    expect(form.get("use_llm")).toBeNull();
    expect((form.get("file") as File).name).toBe("a.docx");
  });

  it("ошибка API превращается в ApiError с сообщением сервера", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse(
            { error: { code: "invalid_document", message: "Повреждённый архив .docx" } },
            422,
          ),
        ),
    );
    const error = await createCheck({
      file: new File(["x"], "a.docx"),
      profileId: "p",
      annotate: false,
    }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      code: "invalid_document",
      status: 422,
      message: "Повреждённый архив .docx",
    });
  });

  it("сбой сети → код network", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(getCheck("abc")).rejects.toMatchObject({ code: "network" });
  });

  it("неожиданный формат ответа → код invalid_response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ hello: "world" })));
    await expect(listProfiles()).rejects.toMatchObject({ code: "invalid_response" });
  });

  it("ответ без JSON-тела (502 прокси) → http_502", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("Bad gateway", { status: 502 })));
    await expect(getCheck("abc")).rejects.toMatchObject({ code: "http_502", status: 502 });
  });

  it("getCheck экранирует id", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(status));
    vi.stubGlobal("fetch", fetchMock);
    await getCheck("a/b");
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/checks/a%2Fb");
  });

  it("deleteCheck считает 404 успехом (уже удалено)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 404 })));
    await expect(deleteCheck("abc")).resolves.toBeUndefined();
  });
});
