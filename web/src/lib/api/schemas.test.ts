import { describe, expect, it } from "vitest";
import sample from "@/mocks/kru-sample.report.json";
import { checkStatusSchema, isFinal, profileListSchema, reportSchema } from "./schemas";

describe("reportSchema", () => {
  it("разбирает реальный отчёт бэкенда (tests/fixtures)", () => {
    const report = reportSchema.parse(sample);
    expect(report.score).toBe(39);
    expect(report.issues).toHaveLength(report.summary.total);
    expect(report.issues[0]?.location.paragraph_ids).toEqual([]);
  });

  it("отклоняет отчёт с неверной серьёзностью", () => {
    const broken = structuredClone(sample) as { issues: { severity: string }[] };
    broken.issues[0]!.severity = "fatal";
    expect(reportSchema.safeParse(broken).success).toBe(false);
  });

  it("допускает новую категорию с бэкенда", () => {
    const extended = structuredClone(sample) as { issues: { category: string }[] };
    extended.issues[0]!.category = "formulas";
    expect(reportSchema.safeParse(extended).success).toBe(true);
  });
});

describe("checkStatusSchema", () => {
  const base = {
    id: "c1",
    status: "running",
    step: "rules",
    steps: [{ id: "parse", title: "Чтение файла", state: "done" }],
    filename: "a.docx",
    profile_id: "kru-mi-049-2026",
    created_at: "2026-10-25T10:00:00Z",
    updated_at: "2026-10-25T10:00:01Z",
    expires_at: "2026-10-25T11:00:00Z",
    error: null,
    report: null,
    annotated_url: null,
  };

  it("разбирает статус проверки и заполняет значения по умолчанию", () => {
    const { steps: _steps, annotated_url: _url, ...minimal } = base;
    const parsed = checkStatusSchema.parse(minimal);
    expect(parsed.steps).toEqual([]);
    expect(parsed.annotated_url).toBeNull();
  });

  it("отклоняет неизвестный статус", () => {
    expect(checkStatusSchema.safeParse({ ...base, status: "paused" }).success).toBe(false);
  });

  it("isFinal", () => {
    expect(isFinal("done")).toBe(true);
    expect(isFinal("failed")).toBe(true);
    expect(isFinal("expired")).toBe(true);
    expect(isFinal("running")).toBe(false);
    expect(isFinal("queued")).toBe(false);
  });
});

describe("profileListSchema", () => {
  it("разбирает список профилей", () => {
    const profiles = profileListSchema.parse([
      { id: "gost-7.32-2017", title: "ГОСТ", status: "draft", doc_types: ["report"] },
    ]);
    expect(profiles[0]?.rag_sources).toEqual([]);
    expect(profiles[0]?.version).toBeNull();
  });
});
