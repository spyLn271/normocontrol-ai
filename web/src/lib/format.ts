/** Форматирование значений для отчёта (без зависимости от React — легко тестировать). */

/** `[1, 2, 3, 5, 7, 8]` → `"1–3, 5, 7–8"` (как format_page_ranges на бэкенде). */
export function formatPageRanges(pages: readonly number[]): string {
  const ordered = [...new Set(pages)].filter(Number.isFinite).sort((a, b) => a - b);
  if (ordered.length === 0) return "";
  const ranges: string[] = [];
  let start = ordered[0]!;
  let prev = start;
  for (const page of ordered.slice(1)) {
    if (page === prev + 1) {
      prev = page;
      continue;
    }
    ranges.push(start === prev ? String(start) : `${start}–${prev}`);
    start = prev = page;
  }
  ranges.push(start === prev ? String(start) : `${start}–${prev}`);
  return ranges.join(", ");
}

/** Цвет балла: ≥ 85 — хорошо, ≥ 60 — есть что исправить, ниже — много ошибок. */
export function scoreTone(score: number): "ok" | "warning" | "error" {
  if (score >= 85) return "ok";
  if (score >= 60) return "warning";
  return "error";
}

export function formatFileSize(bytes: number, locale: string): string {
  const mb = bytes / (1024 * 1024);
  if (mb >= 1) return `${mb.toLocaleString(locale, { maximumFractionDigits: 1 })} МБ`;
  return `${Math.max(1, Math.round(bytes / 1024)).toLocaleString(locale)} КБ`;
}

export function reportFileName(filename: string | null | undefined): string {
  const base = (filename ?? "document").replace(/\.docx$/i, "");
  return `${base}.normocontrol.json`;
}
