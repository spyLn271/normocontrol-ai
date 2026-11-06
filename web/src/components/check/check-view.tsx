"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { CheckProgress } from "@/components/check/check-progress";
import { ErrorState } from "@/components/layout/error-state";
import { ReportView } from "@/components/report/report-view";
import { getCheck } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { isFinal } from "@/lib/api/schemas";

const POLL_MS = 1000;

export function CheckView({ id }: { id: string }) {
  const t = useTranslations();
  const query = useQuery({
    queryKey: ["check", id],
    queryFn: () => getCheck(id),
    refetchInterval: (q) => (q.state.data && isFinal(q.state.data.status) ? false : POLL_MS),
    refetchOnWindowFocus: (q) => !(q.state.data && isFinal(q.state.data.status)),
    retry: (failureCount, error) =>
      !(error instanceof ApiError && error.status === 404) && failureCount < 3,
  });

  if (query.isPending) {
    return (
      <p className="py-16 text-center text-sm text-fg-muted" role="status">
        {t("check.loading")}
      </p>
    );
  }

  if (query.isError) {
    const error = query.error;
    if (error instanceof ApiError && error.status === 404) {
      return <ErrorState title={t("check.notFoundTitle")} text={t("check.notFoundText")} />;
    }
    return (
      <ErrorState
        title={t("check.failedTitle")}
        text={errorText(error, t)}
        onRetry={() => void query.refetch()}
      />
    );
  }

  const check = query.data;
  if (check.status === "failed") {
    return (
      <ErrorState
        title={t("check.failedTitle")}
        text={check.error?.message ?? t("check.failedText")}
      />
    );
  }
  if (check.status === "expired") {
    return <ErrorState title={t("check.expiredTitle")} text={t("check.expiredText")} />;
  }
  if (check.status === "done" && check.report) {
    return <ReportView check={check} report={check.report} />;
  }
  return <CheckProgress check={check} />;
}

export function errorText(error: unknown, t: ReturnType<typeof useTranslations>): string {
  if (error instanceof ApiError) {
    if (error.code === "network") return t("errors.network");
    if (error.code === "invalid_response") return t("errors.invalidResponse");
    if (!error.code.startsWith("http_")) return error.message;
  }
  return t("errors.generic");
}
