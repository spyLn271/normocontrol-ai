"use client";

import { ChevronDown, FileText, Wrench } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId } from "react";
import { CheckerBadge, SeverityBadge } from "@/components/report/badges";
import { Badge } from "@/components/ui/badge";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { type Issue } from "@/lib/api/schemas";
import { formatPageRanges } from "@/lib/format";

export function useIssueLocation() {
  const t = useTranslations("issue");
  return (issue: Issue): string => {
    const { location, count } = issue;
    const parts: string[] = [];
    if (location.pages.length > 0)
      parts.push(t("pages", { pages: formatPageRanges(location.pages) }));
    else if (location.paragraph_ids[0])
      parts.push(t("paragraph", { id: location.paragraph_ids[0] }));
    else if (location.section_index !== null)
      parts.push(t("section", { number: location.section_index + 1 }));
    else parts.push(t("document"));
    if (count > 1 && location.pages.length === 0 && location.paragraph_ids.length > 0) {
      parts.push(t("more", { count: count - 1 }));
    }
    return parts.join(" ");
  };
}

export function IssueCard({ issue }: { issue: Issue }) {
  const t = useTranslations("issue");
  const where = useIssueLocation()(issue);
  const headingId = useId();
  const hasBasis = Boolean(issue.reference || issue.reference_quote);

  return (
    <article
      className="rounded-card border border-border bg-bg p-4 sm:p-5"
      aria-labelledby={headingId}
    >
      <header className="flex flex-wrap items-center gap-2">
        <SeverityBadge severity={issue.severity} />
        <CheckerBadge checker={issue.checker} />
        {issue.count > 1 && (
          <Badge tone="neutral">{t("occurrences", { count: issue.count })}</Badge>
        )}
        <span className="ml-auto font-mono text-xs text-fg-muted" title={t("ruleId")}>
          {issue.rule_id}
        </span>
      </header>

      <h3 id={headingId} className="mt-3 text-[15px] leading-snug font-medium text-fg">
        {issue.message}
      </h3>

      <p className="mt-1 flex items-center gap-1.5 text-sm text-fg-muted">
        <FileText className="size-3.5 shrink-0" aria-hidden />
        {where}
      </p>

      {issue.location.quote && (
        <blockquote className="mt-3 rounded-input border-l-2 border-border-strong bg-bg-subtle px-3 py-2 text-sm text-fg">
          <span className="sr-only">{t("quote")}: </span>
          {issue.location.quote}
        </blockquote>
      )}

      {(issue.expected || issue.actual) && (
        <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
          {issue.actual && (
            <>
              <dt className="text-fg-muted">{t("actual")}</dt>
              <dd className="font-mono text-fg">{issue.actual}</dd>
            </>
          )}
          {issue.expected && (
            <>
              <dt className="text-fg-muted">{t("expected")}</dt>
              <dd className="font-mono text-fg">{issue.expected}</dd>
            </>
          )}
        </dl>
      )}

      {issue.fix && (
        <div className="mt-3 flex gap-2 rounded-input bg-ok-subtle px-3 py-2 text-sm text-ok-fg">
          <Wrench className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          <p>
            <span className="font-medium">{t("fix")}: </span>
            {issue.fix}
          </p>
        </div>
      )}

      {hasBasis && (
        <Collapsible className="mt-3">
          <CollapsibleTrigger className="group inline-flex items-center gap-1 rounded-input text-sm font-medium text-accent hover:underline">
            {t("basis")}
            <ChevronDown
              className="size-4 transition-transform group-data-[state=open]:rotate-180"
              aria-hidden
            />
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-2 space-y-2 text-sm">
            {issue.reference && <p className="text-fg">{issue.reference}</p>}
            {issue.reference_quote && (
              <blockquote className="rounded-input border border-border px-3 py-2 text-fg-muted italic">
                {issue.reference_quote}
              </blockquote>
            )}
          </CollapsibleContent>
        </Collapsible>
      )}
    </article>
  );
}
