"use client";

import { type ReactNode } from "react";
import { Link, usePathname } from "@/i18n/navigation";
import { cn } from "@/lib/utils";

export function NavLink({ href, children }: { href: string; children: ReactNode }) {
  const pathname = usePathname();
  const active =
    href === "/" ? pathname === "/" || pathname.startsWith("/checks") : pathname.startsWith(href);
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "rounded-button px-3 py-1.5 transition-colors",
        active ? "bg-bg-subtle font-medium text-fg" : "text-fg-muted hover:text-fg",
      )}
    >
      {children}
    </Link>
  );
}
