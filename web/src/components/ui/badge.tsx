import { cva, type VariantProps } from "class-variance-authority";
import { type ComponentProps } from "react";
import { cn } from "@/lib/utils";

export const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-badge px-2.5 py-0.5 text-xs font-medium whitespace-nowrap",
  {
    variants: {
      tone: {
        neutral: "bg-bg-subtle text-fg",
        outline: "border border-border text-fg",
        accent: "bg-accent-subtle text-info-fg",
        error: "bg-error-subtle text-error-fg",
        warning: "bg-warning-subtle text-warning-fg",
        info: "bg-info-subtle text-info-fg",
        ok: "bg-ok-subtle text-ok-fg",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export interface BadgeProps extends ComponentProps<"span">, VariantProps<typeof badgeVariants> {}

export function Badge({ className, tone, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
