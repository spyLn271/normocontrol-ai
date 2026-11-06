import { type ComponentProps } from "react";
import { cn } from "@/lib/utils";

export function Input({ className, ...props }: ComponentProps<"input">) {
  return (
    <input
      className={cn(
        "h-10 w-full rounded-input border border-border bg-bg px-3 text-sm text-fg placeholder:text-fg-muted focus-visible:border-accent focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-ring disabled:opacity-50 aria-invalid:border-error",
        className,
      )}
      {...props}
    />
  );
}
