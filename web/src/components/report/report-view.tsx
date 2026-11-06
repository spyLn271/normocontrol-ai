"use client";

import { useMutation } from "@tanstack/react-query";
import { Download, FileJson, Trash2 } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { SeverityCount } from "@/components/report/badges";
import { CategoryRing } from "@/components/report/category-ring";
import { IssueCard } from "@/components/report/issue-card";
import { IssueFilters } from "@/components/report/issue-filters";
import { ScoreGauge } from "@/components/report/score-gauge";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useRouter } from "@/i18n/navigation";
import { deleteCheck } from "@/lib/api/client";
import { type CheckStatus, type Report, SEVERITIES } from "@/lib/api/schemas";
import { downloadJson } from "@/lib/download";
import { reportFileName } from "@/lib/format";
import {
  categoriesByCount,
  countBySeverity,
  EMPTY_FILTER,
  filterIssues,
  type IssueFilter,
  sortIssues,
  toggle,
} from "@/lib/issues";

interface ReportViewProps {
  check: CheckStatus;
  report: Report;
}

export function ReportView({ check, report }: ReportViewProps) {
  const t = useTranslations();
  const format = useFormatter();
  const router = useRouter();
  const [filter, setFilter] = useState<IssueFilter>(EMPTY_FILTER);

  const severityCounts = useMemo(() => countBySeverity(report.issues), [report.issues]);
  const categories = useMemo(
    () => categoriesByCount(report.summary.by_category),
    [report.summary.by_category],
  );
  const visible = useMemo(
    () => sortIssues(filterIssues(report.issues, filter)),
    [report.issues, filter],
  );

  const remove = useMutation({
    mutationFn: () => deleteCheck(check.id),
    onSuccess: () => router.push("/"),
  });

  const isDraft = report.profile.status === "draft";
  const pages = report.document.pages_estimated;

  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="summary-title" className="rounded-card-lg border border-border">
        <h1 id="summary-title" className="sr-only">
          {t("report.summary")}
        </h1>
        <div className="grid gap-6 p-6 sm:p-8 md:grid-cols-[auto_1fr] md:items-center">
          <ScoreGauge score={report.score} />
          <div className="flex min-w-0 flex-col gap-4">
            <div className="flex flex-wrap gap-2">
              {SEVERITIES.map((severity) => (
                <SeverityCount
                  key={severity}
                  severity={severity}
                  count={report.summary.by_severity[severity] ?? 0}
                />
              ))}
            </div>
            <dl className="grid gap-3 text-sm sm:grid-cols-2">
              <div className="min-w-0">
                <dt className="text-fg-muted">{t("report.document")}</dt>
                <dd
                  className="truncate font-mono text-fg"
                  title={report.document.filename ?? undefined}
                >
                  {report.document.filename ?? "—"}
                </dd>
                <dd className="text-fg-muted">
                  {pages
                    ? report.document.page_source === "libreoffice"
                      ? t("report.pages", { count: pages })
                      : t("report.approxPages", { pages: t("report.pages", { count: pages }) })
                    : t("report.paragraphs", { count: report.document.paragraphs })}
                </dd>
              </div>
              <div className="min-w-0">
                <dt className="text-fg-muted">{t("report.profile")}</dt>
                <dd className="flex flex-wrap items-center gap-2 text-fg">
                  <span>{report.profile.title}</span>
                  {isDraft && (
                    <Badge tone="warning" title={t("report.draftHint")}>
                      {t("profiles.status.draft")}
                    </Badge>
                  )}
                </dd>
              </div>
            </dl>
            <p className="text-xs text-fg-muted">
              {t("report.duration", {
                seconds: format.number(report.duration_ms / 1000, { maximumFractionDigits: 1 }),
              })}
              {check.expires_at &&
                ` · ${t("report.expires", {
                  time: format.dateTime(new Date(check.expires_at), {
                    hour: "2-digit",
                    minute: "2-digit",
                  }),
                })}`}
            </p>
            <div className="flex flex-wrap gap-2">
              {check.annotated_url && (
                <Button asChild>
                  <a href={check.annotated_url} download>
                    <Download aria-hidden />
                    {t("report.downloadDocx")}
                  </a>
                </Button>
              )}
              <Button
                variant="secondary"
                onClick={() => downloadJson(report, reportFileName(report.document.filename))}
              >
                <FileJson aria-hidden />
                {t("report.downloadJson")}
              </Button>
              <Button
                variant="danger"
                onClick={() => remove.mutate()}
                disabled={remove.isPending}
                title={t("report.deleteHint")}
              >
                <Trash2 aria-hidden />
                {remove.isPending ? t("report.deleting") : t("report.delete")}
              </Button>
            </div>
          </div>
        </div>
      </section>

      {(isDraft || report.notices.length > 0) && (
        <section aria-labelledby="notices-title" className="flex flex-col gap-2">
          <h2 id="notices-title" className="sr-only">
            {t("report.notices")}
          </h2>
          {report.notices.map((notice) => (
            <Alert key={notice.code} tone={notice.level === "warning" ? "warning" : "info"}>
              {notice.message}
            </Alert>
          ))}
        </section>
      )}

      {report.issues.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center">
            <p className="text-lg font-semibold text-ok-fg">{t("report.noIssues")}</p>
            <p className="mt-1 text-sm text-fg-muted">{t("report.noIssuesText")}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px] lg:items-start">
          <section
            aria-labelledby="issues-title"
            className="order-2 flex flex-col gap-4 lg:order-1"
          >
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 id="issues-title" className="text-lg font-semibold text-fg">
                {t("report.issues")}
              </h2>
              <p className="text-sm text-fg-muted" aria-live="polite">
                {t("report.shown", { shown: visible.length, total: report.issues.length })}
              </p>
            </div>
            <IssueFilters
              filter={filter}
              severityCounts={severityCounts}
              categories={categories}
              onToggleSeverity={(severity) =>
                setFilter((f) => ({ ...f, severities: toggle(f.severities, severity) }))
              }
              onToggleCategory={(category) =>
                setFilter((f) => ({ ...f, categories: toggle(f.categories, category) }))
              }
              onReset={() => setFilter(EMPTY_FILTER)}
            />
            {visible.length === 0 ? (
              <p className="rounded-card border border-dashed border-border p-6 text-center text-sm text-fg-muted">
                {t("report.noMatches")}
              </p>
            ) : (
              <ul className="flex flex-col gap-3">
                {visible.map((issue, index) => (
                  <li key={`${issue.rule_id}-${issue.location.paragraph_ids.join(",")}-${index}`}>
                    <IssueCard issue={issue} />
                  </li>
                ))}
              </ul>
            )}
          </section>
          <Card className="order-1 lg:sticky lg:top-20 lg:order-2">
            <CardHeader>
              <CardTitle>{t("report.byCategory")}</CardTitle>
            </CardHeader>
            <CardContent>
              <CategoryRing
                byCategory={report.summary.by_category}
                selected={filter.categories}
                onSelect={(category) =>
                  setFilter((f) => ({ ...f, categories: toggle(f.categories, category) }))
                }
                size={200}
                layout="stacked"
              />
            </CardContent>
          </Card>
        </div>
      )}
      {remove.isError && <Alert tone="error">{t("errors.generic")}</Alert>}
    </div>
  );
}
