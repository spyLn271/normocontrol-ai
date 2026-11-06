import { type Issue, type Severity, SEVERITIES } from "@/lib/api/schemas";

export interface IssueFilter {
  severities: ReadonlySet<Severity>;
  categories: ReadonlySet<string>;
}

export const EMPTY_FILTER: IssueFilter = { severities: new Set(), categories: new Set() };

/** Пустой набор в фильтре означает «все значения». */
export function filterIssues(issues: readonly Issue[], filter: IssueFilter): Issue[] {
  return issues.filter(
    (issue) =>
      (filter.severities.size === 0 || filter.severities.has(issue.severity)) &&
      (filter.categories.size === 0 || filter.categories.has(issue.category)),
  );
}

export function toggle<T>(set: ReadonlySet<T>, value: T): Set<T> {
  const next = new Set(set);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}

export function countBySeverity(issues: readonly Issue[]): Record<Severity, number> {
  const counts = Object.fromEntries(SEVERITIES.map((s) => [s, 0])) as Record<Severity, number>;
  for (const issue of issues) counts[issue.severity] += 1;
  return counts;
}

/** Категории в порядке убывания числа замечаний (для фильтров и диаграммы). */
export function categoriesByCount(byCategory: Record<string, number>): [string, number][] {
  return Object.entries(byCategory)
    .filter(([, count]) => count > 0)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

const SEVERITY_RANK: Record<Severity, number> = { error: 0, warning: 1, info: 2 };

export function sortIssues(issues: readonly Issue[]): Issue[] {
  return [...issues].sort(
    (a, b) =>
      SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity] ||
      (a.location.pages[0] ?? 0) - (b.location.pages[0] ?? 0),
  );
}
