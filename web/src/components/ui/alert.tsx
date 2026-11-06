import { AlertTriangle, Info } from "lucide-react";
import { type ComponentProps } from "react";
import { cn } from "@/lib/utils";

interface AlertProps extends ComponentProps<"div"> {
  tone?: "info" | "warning" | "error";
}

export function Alert({ className, tone = "info", children, ...props }: AlertProps) {
  const Icon = tone === "info" ? Info : AlertTriangle;
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cn(
        "flex items-start gap-3 rounded-card border p-4 text-sm",
        tone === "info" && "border-border bg-bg-subtle text-fg",
        tone === "warning" && "border-warning/40 bg-warning-subtle text-warning-fg",
        tone === "error" && "border-error/40 bg-error-subtle text-error-fg",
        className,
      )}
      {...props}
    >
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
