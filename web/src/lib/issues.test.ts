import { describe, expect, it } from "vitest";
import sample from "@/mocks/kru-sample.report.json";
import { reportSchema, type Issue } from "./api/schemas";
import {
  categoriesByCount,
  countBySeverity,
  EMPTY_FILTER,
  filterIssues,
  sortIssues,
  toggle,
} from "./issues";

const issues = reportSchema.parse(sample).issues;

describe("filterIssues", () => {
  it("без фильтров возвращает все замечания", () => {
    expect(filterIssues(issues, EMPTY_FILTER)).toHaveLength(issues.length);
  });

  it("фильтрует по серьёзности", () => {
    const errors = filterIssues(issues, { severities: new Set(["error"]), categories: new Set() });
    expect(errors.length).toBeGreaterThan(0);
    expect(errors.every((issue) => issue.severity === "error")).toBe(true);
  });

  it("сочетает серьёзность и категорию (И), значения внутри фильтра — ИЛИ", () => {
    const result = filterIssues(issues, {
      severities: new Set(["error", "warning"]),
      categories: new Set(["page", "tables"]),
    });
    expect(result.map((issue) => issue.category).sort()).toEqual(["page", "tables"]);
  });

  it("неизвестная категория даёт пустой результат", () => {
    expect(filterIssues(issues, { severities: new Set(), categories: new Set(["nope"]) })).toEqual(
      [],
    );
  });
});

describe("helpers", () => {
  it("toggle добавляет и убирает значение, не меняя исходный набор", () => {
    const base = new Set(["a"]);
    expect([...toggle(base, "b")].sort()).toEqual(["a", "b"]);
    expect([...toggle(base, "a")]).toEqual([]);
    expect([...base]).toEqual(["a"]);
  });

  it("countBySeverity совпадает со сводкой отчёта", () => {
    expect(countBySeverity(issues)).toEqual({ error: 4, warning: 3, info: 0 });
  });

  it("categoriesByCount сортирует по убыванию и отбрасывает нули", () => {
    expect(categoriesByCount({ page: 1, font: 3, text: 0, heading: 3 })).toEqual([
      ["font", 3],
      ["heading", 3],
      ["page", 1],
    ]);
  });

  it("sortIssues: сначала ошибки, затем по странице", () => {
    const make = (severity: Issue["severity"], page: number): Issue => ({
      ...issues[0]!,
      severity,
      location: { ...issues[0]!.location, pages: [page] },
    });
    const sorted = sortIssues([
      make("info", 1),
      make("error", 9),
      make("warning", 2),
      make("error", 3),
    ]);
    expect(sorted.map((i) => `${i.severity}:${i.location.pages[0]}`)).toEqual([
      "error:3",
      "error:9",
      "warning:2",
      "info:1",
    ]);
  });
});
