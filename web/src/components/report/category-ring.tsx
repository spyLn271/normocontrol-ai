"use client";

import { useTranslations } from "next-intl";
import { Ring } from "@/components/charts/ring";
import { RingCenter } from "@/components/charts/ring-center";
import { RingChart } from "@/components/charts/ring-chart";
import { categoriesByCount } from "@/lib/issues";
import { useIsClient } from "@/lib/use-is-client";
import { cn } from "@/lib/utils";

const PALETTE = [1, 2, 3, 4, 5, 6, 7, 8].map((n) => `var(--nc-chart-${n})`);

interface CategoryRingProps {
  byCategory: Record<string, number>;
  selected?: ReadonlySet<string>;
  onSelect?: (category: string) => void;
  size?: number;
  /** stacked — диаграмма над легендой (узкая колонка), inline — рядом (широкий блок) */
  layout?: "stacked" | "inline";
}

/** Замечания по категориям — Ring Chart из Bklit UI + доступная легенда-фильтр. */
export function CategoryRing({
  byCategory,
  selected,
  onSelect,
  size = 220,
  layout = "inline",
}: CategoryRingProps) {
  const t = useTranslations();
  const isClient = useIsClient();
  const entries = categoriesByCount(byCategory);
  const total = entries.reduce((sum, [, count]) => sum + count, 0);
  const label = (category: string) =>
    t.has(`category.${category}`) ? t(`category.${category}`) : category;
  const data = entries.map(([category, count], index) => ({
    label: label(category),
    value: count,
    maxValue: total,
    color: PALETTE[index % PALETTE.length],
  }));

  if (entries.length === 0) return null;

  return (
    <div
      className={cn(
        "flex flex-col items-center gap-6",
        layout === "inline" && "sm:flex-row sm:items-center",
      )}
    >
      <div aria-hidden className="shrink-0" style={{ width: size, height: size }}>
        {isClient && (
          <RingChart
            data={data}
            size={size}
            strokeWidth={10}
            ringGap={5}
            baseInnerRadius={Math.max(40, size / 2 - entries.length * 15 - 12)}
          >
            {data.map((item, index) => (
              <Ring key={item.label} index={index} color={item.color} />
            ))}
            <RingCenter defaultLabel={t("report.ringTotal")} />
          </RingChart>
        )}
      </div>
      <ul className="grid w-full gap-1" aria-label={t("report.byCategory")}>
        {entries.map(([category, count], index) => {
          const active = selected?.has(category) ?? false;
          return (
            <li key={category}>
              <button
                type="button"
                onClick={() => onSelect?.(category)}
                aria-pressed={onSelect ? active : undefined}
                disabled={!onSelect}
                className={cn(
                  "flex w-full items-center gap-3 rounded-input px-2 py-1.5 text-left text-sm text-fg transition-colors enabled:hover:bg-bg-subtle",
                  active && "bg-bg-subtle font-medium",
                )}
              >
                <span
                  aria-hidden
                  className="size-2.5 shrink-0 rounded-badge"
                  style={{ backgroundColor: PALETTE[index % PALETTE.length] }}
                />
                <span className="flex-1">{label(category)}</span>
                <span className="font-mono text-fg-muted tabular-nums">{count}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
