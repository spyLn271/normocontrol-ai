"use client";

import { useTranslations } from "next-intl";
import { Gauge } from "@/components/charts/gauge";
import { scoreTone } from "@/lib/format";
import { useIsClient } from "@/lib/use-is-client";
import { cn } from "@/lib/utils";

const TONE_FILL = {
  ok: "var(--nc-ok)",
  warning: "var(--nc-warning)",
  error: "var(--nc-error)",
} as const;

interface ScoreGaugeProps {
  score: number;
  size?: number;
  className?: string;
}

/** Балл соответствия 0–100 — Gauge из Bklit UI. */
export function ScoreGauge({ score, size = 240, className }: ScoreGaugeProps) {
  const t = useTranslations("report");
  const value = Math.max(0, Math.min(100, Math.round(score)));
  const tone = scoreTone(value);
  const isClient = useIsClient();
  const height = Math.round(size * 0.62);
  return (
    <figure
      role="img"
      aria-label={t("scoreAria", { score: value })}
      data-tone={tone}
      className={cn("flex flex-col items-center", className)}
    >
      <div aria-hidden className="pointer-events-none" style={{ width: size, height }}>
        {isClient && (
          <Gauge
            value={value}
            centerValue={value}
            defaultLabel={t("scoreOf")}
            activeFill={TONE_FILL[tone]}
            inactiveFillOpacity={0.35}
            totalNotches={40}
            spacing={25}
            width={size}
            height={height}
          />
        )}
      </div>
      <figcaption className="mt-1 text-sm font-medium text-fg-muted">{t("score")}</figcaption>
    </figure>
  );
}
