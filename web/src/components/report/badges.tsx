"use client";

import { Bot, Ruler, Network } from "lucide-react";
import { useTranslations } from "next-intl";
import { Badge } from "@/components/ui/badge";
import { type Checker, type Severity } from "@/lib/api/schemas";

const SEVERITY_TONE = { error: "error", warning: "warning", info: "info" } as const;

export function SeverityBadge({ severity }: { severity: Severity }) {
  const t = useTranslations("severity");
  return (
    <Badge tone={SEVERITY_TONE[severity]}>
      <span aria-hidden className="size-1.5 rounded-badge bg-current" />
      {t(severity)}
    </Badge>
  );
}

const CHECKER_ICON = { rule: Ruler, structure: Network, llm: Bot } as const;

export function CheckerBadge({ checker }: { checker: Checker }) {
  const t = useTranslations("checker");
  const Icon = CHECKER_ICON[checker];
  return (
    <Badge tone="outline">
      <Icon className="size-3" aria-hidden />
      {t(checker)}
    </Badge>
  );
}

export function SeverityCount({ severity, count }: { severity: Severity; count: number }) {
  const t = useTranslations("severityCount");
  return (
    <Badge tone={count > 0 ? SEVERITY_TONE[severity] : "neutral"}>{t(severity, { count })}</Badge>
  );
}
