import * as React from "react";
import { ChevronDown } from "lucide-react";
import { Tip } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";

/** A section with an eyebrow, a plain-language headline and body. */
export function Block({ eyebrow, title, children, className, id }: { eyebrow?: string; title: React.ReactNode; children: React.ReactNode; className?: string; id?: string }) {
  return (
    <section id={id} className={cn("scroll-mt-20 py-10", className)}>
      {eyebrow && <p className="mb-2 text-[12px] font-semibold uppercase tracking-[0.12em] text-accent">{eyebrow}</p>}
      <h2 className="max-w-3xl text-[24px] font-semibold leading-tight tracking-tight [text-wrap:balance] sm:text-[28px]">{title}</h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}

/** Collapsible caveats and sources, so the headline stays simple and the detail is one click away. */
export function FinePrint({ children, source }: { children: React.ReactNode; source?: string }) {
  return (
    <details className="group mt-4 rounded-lg border border-line bg-panel px-4 py-2.5 text-[13px] text-ink-2">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 font-medium text-ink [&::-webkit-details-marker]:hidden">
        <ChevronDown size={15} className="transition-transform group-open:rotate-180" />The fine print
      </summary>
      <div className="mt-2 space-y-1.5 leading-relaxed">{children}</div>
      {source && <p className="mt-2 text-[11px] text-ink-3"><span title={source} className="cursor-help underline decoration-dotted">Source: the project's published results file</span></p>}
    </details>
  );
}

/** "What this means" callout. */
export function Meaning({ children }: { children: React.ReactNode }) {
  return (
    <div className="prose-links mt-4 border-l-[3px] border-accent bg-accent-soft/60 px-4 py-3 text-[14px] leading-relaxed text-ink">
      <span className="mr-1 font-semibold">What this means:</span>{children}
    </div>
  );
}

/** Horizontal bars with a value label; `highlight` marks our system. */
export function Bars({ rows, max = 1, format, unit, caption }: {
  rows: { label: string; value: number; highlight?: boolean; note?: string; secondary?: number }[];
  max?: number; format: (v: number) => string; unit?: string; caption?: string;
}) {
  return (
    <figure className="space-y-2.5">
      {rows.map((r) => (
        <div key={r.label} className="grid grid-cols-1 gap-1 sm:grid-cols-[minmax(0,260px)_1fr] sm:items-center sm:gap-4">
          <span className={cn("text-[13.5px]", r.highlight ? "font-semibold text-ink" : "text-ink-2")}>{r.label}</span>
          <div className="flex items-center gap-3">
            <div className="h-6 min-w-0 flex-1 overflow-hidden rounded-md bg-panel-2" role="img" aria-label={`${r.label}: ${format(r.value)}${unit ?? ""}`}>
              <div className={cn("h-full rounded-md", r.highlight ? "bg-accent" : "bg-ink-3/45")} style={{ width: `${Math.max(1.5, (r.value / max) * 100)}%` }} />
            </div>
            <span className={cn("num w-28 shrink-0 text-right text-[13px]", r.highlight ? "font-semibold text-ink" : "text-ink-2")}>{format(r.value)}{unit}</span>
          </div>
          {r.note && <span className="text-[12px] text-ink-3 sm:col-start-2">{r.note}</span>}
        </div>
      ))}
      {caption && <figcaption className="pt-1 text-[12px] text-ink-3">{caption}</figcaption>}
    </figure>
  );
}

export function Stat({ value, label, hint }: { value: React.ReactNode; label: string; hint?: string }) {
  const body = (
    <div className="min-w-0">
      <p className="num text-[30px] font-semibold leading-none tracking-tight text-ink sm:text-[34px]">{value}</p>
      <p className="mt-1.5 text-[13px] leading-snug text-ink-2">{label}</p>
    </div>
  );
  return hint ? <Tip content={hint}><div className="cursor-help">{body}</div></Tip> : body;
}

/** Inline glossary term. */
export function Term({ children, def }: { children: React.ReactNode; def: string }) {
  return <Tip content={<span className="block max-w-xs">{def}</span>}><span className="cursor-help underline decoration-dotted underline-offset-4">{children}</span></Tip>;
}

export const pct0 = (x: number) => `${Math.round(x * 100)}%`;

/** A difference with its 95% interval, in plain words. */
export function plainCI(diff: number, lo: number, hi: number) {
  const f = (x: number) => `${x >= 0 ? "+" : "−"}${Math.abs(x).toFixed(2)}`;
  const verdict = lo > 0 ? "clearly above zero, so the advantage is real" : hi < 0 ? "clearly below zero, so the drop is real" : "the range includes zero, so it could be no difference";
  return `${f(diff)} (95% range ${f(lo)} to ${f(hi)}; ${verdict})`;
}
