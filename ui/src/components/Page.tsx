import * as React from "react";
import { cn } from "@/lib/utils";
import { Badge } from "./ui/primitives";

export function PageHeader({ title, subtitle, tier, product, actions }: {
  title: string; subtitle?: React.ReactNode; tier?: "MUST" | "SHOULD" | "COULD"; product?: boolean; actions?: React.ReactNode;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-[20px] font-semibold tracking-tight">{title}</h1>
          {product && <Badge tone="product">Product view</Badge>}
          {tier && <Badge tone="outline">{tier}</Badge>}
        </div>
        {subtitle && <p className="mt-1 max-w-3xl text-[13px] text-ink-2">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function EmptyState({ title, file, command, children }: { title: string; file?: string; command?: string; children?: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-line p-6 text-center text-sm">
      <p className="font-medium">{title}</p>
      {file && <p className="mt-1 text-ink-3">Missing or unreadable: <code>{file}</code></p>}
      {command && <p className="mt-1 text-ink-3">Produce it with <code className="rounded bg-panel-2 px-1">{command}</code></p>}
      {children}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-panel-2", className)} />;
}

export function LoadingPage() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading">
      <Skeleton className="h-7 w-72" />
      <div className="grid gap-3 md:grid-cols-4">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-28" />)}</div>
      <Skeleton className="h-40" />
    </div>
  );
}

export function Section({ title, children, className, actions }: { title: string; children: React.ReactNode; className?: string; actions?: React.ReactNode }) {
  return (
    <section className={cn("mt-6", className)}>
      <div className="mb-2 flex items-center justify-between gap-2"><h2 className="text-[14px] font-semibold">{title}</h2>{actions}</div>
      {children}
    </section>
  );
}
