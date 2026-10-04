import { ciReading } from "@/lib/ci";
import { cn } from "@/lib/utils";
import { Num } from "./Provenance";

/** The visual signature: point, interval bar and a zero tick, with the project's exact label beside it. */
export function CIBar({ point, lo, hi, domain, width = 120, height = 14 }: {
  point: number; lo: number; hi: number; domain: [number, number]; width?: number; height?: number;
}) {
  const [d0, d1] = domain;
  const x = (v: number) => ((Math.min(Math.max(v, d0), d1) - d0) / (d1 - d0 || 1)) * (width - 4) + 2;
  const r = ciReading(lo, hi);
  const color = r.includes("above") ? "var(--pos)" : r.includes("below") ? "var(--neg)" : "var(--neutral)";
  const zero = d0 <= 0 && d1 >= 0;
  return (
    <svg width={width} height={height} role="img" aria-label={`${point.toFixed(3)} [${lo.toFixed(3)}, ${hi.toFixed(3)}] ${r}`} className="shrink-0">
      {zero && <line x1={x(0)} x2={x(0)} y1={0} y2={height} stroke="var(--ink-3)" strokeWidth={1} strokeDasharray="2 2" />}
      <line x1={x(lo)} x2={x(hi)} y1={height / 2} y2={height / 2} stroke={color} strokeWidth={2} strokeLinecap="round" />
      <circle cx={x(point)} cy={height / 2} r={3.2} fill={color} />
    </svg>
  );
}

export function CICell({ point, ci, label, sourceKey, domain, onOpen, compact, signed }: {
  point: number; ci: [number, number] | null; label?: string | null; sourceKey: string; domain?: [number, number];
  onOpen?: () => void; compact?: boolean; signed?: boolean;
}) {
  if (!ci) {
    return (
      <span className="inline-flex items-center gap-1.5">
        <Num value={signed ? (point >= 0 ? "+" : "") + point.toFixed(3) : point.toFixed(3)} sourceKey={sourceKey} onOpen={onOpen} />
        <span className="text-[10px] text-ink-3" title="R13: no CI computed for this metric (A5)">no CI</span>
      </span>
    );
  }
  const dom: [number, number] = domain ?? (signed ? [-Math.max(Math.abs(ci[0]), Math.abs(ci[1]), 0.05) * 1.1, Math.max(Math.abs(ci[0]), Math.abs(ci[1]), 0.05) * 1.1] : [0, 1]);
  return (
    <span className={cn("inline-flex min-w-0 max-w-full flex-wrap items-center gap-x-2 gap-y-0.5", compact && "gap-x-1.5")}>
      <CIBar point={point} lo={ci[0]} hi={ci[1]} domain={dom} width={compact ? 70 : 110} />
      <Num value={label ?? `${point.toFixed(3)} [${ci[0].toFixed(3)}, ${ci[1].toFixed(3)}]`} sourceKey={sourceKey} onOpen={onOpen}
        className={cn("min-w-0 break-words text-[12px]", compact ? "text-[11.5px]" : "lg:whitespace-nowrap")} />
    </span>
  );
}
