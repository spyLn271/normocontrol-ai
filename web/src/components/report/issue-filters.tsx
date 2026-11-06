"use client";

import { useTranslations } from "next-intl";
import { type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { type Severity, SEVERITIES } from "@/lib/api/schemas";
import { type IssueFilter } from "@/lib/issues";
import { cn } from "@/lib/utils";

interface IssueFiltersProps {
  filter: IssueFilter;
  severityCounts: Record<Severity, number>;
  categories: [string, number][];
  onToggleSeverity: (severity: Severity) => void;
  onToggleCategory: (category: string) => void;
  onReset: () => void;
}

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "inline-flex h-8 items-center gap-1.5 rounded-badge border px-3 text-sm transition-colors",
        active
          ? "border-primary bg-primary text-primary-fg"
          : "border-border bg-bg text-fg hover:bg-bg-subtle",
      )}
    >
      {children}
    </button>
  );
}

export function IssueFilters({
  filter,
  severityCounts,
  categories,
  onToggleSeverity,
  onToggleCategory,
  onReset,
}: IssueFiltersProps) {
  const t = useTranslations();
  const isFiltered = filter.severities.size > 0 || filter.categories.size > 0;
  return (
    <div className="flex flex-col gap-3">
      <fieldset className="flex flex-wrap items-center gap-2">
        <legend className="mb-2 text-xs font-medium tracking-wide text-fg-muted uppercase">
          {t("report.filterSeverity")}
        </legend>
        {SEVERITIES.filter((s) => severityCounts[s] > 0).map((severity) => (
          <Chip
            key={severity}
            active={filter.severities.has(severity)}
            onClick={() => onToggleSeverity(severity)}
          >
            {t(`severity.${severity}`)}
            <span className="font-mono text-xs opacity-70">{severityCounts[severity]}</span>
          </Chip>
        ))}
      </fieldset>
      {categories.length > 1 && (
        <fieldset className="flex flex-wrap items-center gap-2">
          <legend className="mb-2 text-xs font-medium tracking-wide text-fg-muted uppercase">
            {t("report.filterCategory")}
          </legend>
          {categories.map(([category, count]) => (
            <Chip
              key={category}
              active={filter.categories.has(category)}
              onClick={() => onToggleCategory(category)}
            >
              {t.has(`category.${category}`) ? t(`category.${category}`) : category}
              <span className="font-mono text-xs opacity-70">{count}</span>
            </Chip>
          ))}
        </fieldset>
      )}
      {isFiltered && (
        <div>
          <Button variant="link" size="sm" onClick={onReset}>
            {t("report.resetFilters")}
          </Button>
        </div>
      )}
    </div>
  );
}
