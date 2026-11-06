import { describe, expect, it } from "vitest";
import { formatPageRanges, reportFileName, scoreTone } from "./format";

describe("formatPageRanges", () => {
  it("сворачивает последовательности в диапазоны", () => {
    expect(formatPageRanges([1, 2, 3, 5, 7, 8])).toBe("1–3, 5, 7–8");
  });

  it("сортирует и убирает дубли", () => {
    expect(formatPageRanges([9, 3, 4, 3, 10])).toBe("3–4, 9–10");
  });

  it("одна страница и пустой список", () => {
    expect(formatPageRanges([5])).toBe("5");
    expect(formatPageRanges([])).toBe("");
  });
});

describe("scoreTone", () => {
  it.each([
    [100, "ok"],
    [85, "ok"],
    [84, "warning"],
    [60, "warning"],
    [59, "error"],
    [0, "error"],
  ] as const)("%i → %s", (score, tone) => {
    expect(scoreTone(score)).toBe(tone);
  });
});

describe("reportFileName", () => {
  it("заменяет расширение .docx", () => {
    expect(reportFileName("Курсовая.DOCX")).toBe("Курсовая.normocontrol.json");
    expect(reportFileName(null)).toBe("document.normocontrol.json");
  });
});
