"use client";

import { Check, Circle, Loader2, MinusCircle } from "lucide-react";
import { useTranslations } from "next-intl";
import { type CheckStatus } from "@/lib/api/schemas";
import { cn } from "@/lib/utils";

const ICONS = { pending: Circle, active: Loader2, done: Check, skipped: MinusCircle } as const;

export function CheckProgress({ check }: { check: CheckStatus }) {
  const t = useTranslations("check");
  const steps = check.steps.length > 0 ? check.steps : [];
  const done = steps.filter((s) => s.state === "done" || s.state === "skipped").length;
  const percent = steps.length ? Math.round((done / steps.length) * 100) : 0;

  return (
    <section
      aria-labelledby="progress-title"
      className="rounded-card-lg border border-border p-6 sm:p-8"
    >
      <div className="flex items-center justify-between gap-4">
        <h1 id="progress-title" className="text-xl font-semibold text-fg">
          {t(`status.${check.status}`)}
        </h1>
        {check.filename && (
          <span className="truncate font-mono text-sm text-fg-muted">{check.filename}</span>
        )}
      </div>
      <div
        role="progressbar"
        aria-label={t("progressLabel")}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        className="mt-5 h-1.5 overflow-hidden rounded-badge bg-bg-subtle"
      >
        <div
          className="h-full bg-accent transition-[width] duration-500"
          style={{ width: `${percent}%` }}
        />
      </div>
      <ol className="mt-6 space-y-3" aria-live="polite">
        {steps.map((step) => {
          const Icon = ICONS[step.state];
          const title = t.has(`steps.${step.id}`) ? t(`steps.${step.id}`) : step.title;
          return (
            <li key={step.id} className="flex items-center gap-3 text-sm">
              <span
                className={cn(
                  "flex size-6 items-center justify-center rounded-badge border",
                  step.state === "done" && "border-ok bg-ok-subtle text-ok-fg",
                  step.state === "active" && "border-accent text-accent",
                  step.state === "pending" && "border-border text-fg-muted",
                  step.state === "skipped" && "border-border text-fg-muted",
                )}
              >
                <Icon
                  className={cn("size-3.5", step.state === "active" && "motion-safe:animate-spin")}
                  aria-hidden
                />
              </span>
              <span
                className={cn("flex-1", step.state === "pending" ? "text-fg-muted" : "text-fg")}
              >
                {title}
              </span>
              <span className="text-xs text-fg-muted">{t(`stepState.${step.state}`)}</span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
