"use client";

import * as CheckboxPrimitive from "@radix-ui/react-checkbox";
import { Check } from "lucide-react";
import { type ComponentProps } from "react";
import { cn } from "@/lib/utils";

export function Checkbox({ className, ...props }: ComponentProps<typeof CheckboxPrimitive.Root>) {
  return (
    <CheckboxPrimitive.Root
      className={cn(
        "peer size-5 shrink-0 rounded-[4px] border border-border-strong bg-bg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-50 data-[state=checked]:border-primary data-[state=checked]:bg-primary data-[state=checked]:text-primary-fg",
        className,
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator className="flex items-center justify-center">
        <Check className="size-3.5" strokeWidth={3} aria-hidden />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}
