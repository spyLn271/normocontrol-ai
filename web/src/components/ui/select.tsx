"use client";

import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";
import { type ComponentProps } from "react";
import { cn } from "@/lib/utils";

export const Select = SelectPrimitive.Root;
export const SelectValue = SelectPrimitive.Value;

export function SelectTrigger({
  className,
  children,
  ...props
}: ComponentProps<typeof SelectPrimitive.Trigger>) {
  return (
    <SelectPrimitive.Trigger
      className={cn(
        "flex h-10 w-full items-center justify-between gap-2 rounded-input border border-border bg-bg px-3 text-left text-sm text-fg focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-ring disabled:opacity-50 aria-invalid:border-error data-[placeholder]:text-fg-muted [&>span]:truncate",
        className,
      )}
      {...props}
    >
      {children}
      <SelectPrimitive.Icon asChild>
        <ChevronDown className="size-4 shrink-0 text-fg-muted" aria-hidden />
      </SelectPrimitive.Icon>
    </SelectPrimitive.Trigger>
  );
}

export function SelectContent({
  className,
  children,
  position = "popper",
  ...props
}: ComponentProps<typeof SelectPrimitive.Content>) {
  return (
    <SelectPrimitive.Portal>
      <SelectPrimitive.Content
        position={position}
        sideOffset={4}
        className={cn(
          "relative z-50 max-h-[min(24rem,var(--radix-select-content-available-height))] min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-card border border-border bg-bg text-fg",
          className,
        )}
        {...props}
      >
        <SelectPrimitive.Viewport className="p-1">{children}</SelectPrimitive.Viewport>
      </SelectPrimitive.Content>
    </SelectPrimitive.Portal>
  );
}

export function SelectItem({
  className,
  children,
  ...props
}: ComponentProps<typeof SelectPrimitive.Item>) {
  return (
    <SelectPrimitive.Item
      className={cn(
        "relative flex w-full cursor-default items-start gap-2 rounded-input py-2 pr-8 pl-2 text-sm outline-none select-none data-[disabled]:opacity-50 data-[highlighted]:bg-bg-subtle",
        className,
      )}
      {...props}
    >
      <span className="absolute top-2.5 right-2 flex size-4 items-center justify-center">
        <SelectPrimitive.ItemIndicator>
          <Check className="size-4" aria-hidden />
        </SelectPrimitive.ItemIndicator>
      </span>
      {children}
    </SelectPrimitive.Item>
  );
}

export const SelectItemText = SelectPrimitive.ItemText;
