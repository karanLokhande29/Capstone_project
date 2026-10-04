import { useRef } from "react";
import { Download } from "lucide-react";
import { ciReading } from "@/lib/ci";
import { exportPng, exportSvg } from "@/lib/export";
import { ARTIFACT } from "@/lib/env";
import { Button, Tip } from "./ui/primitives";
import { CICell } from "./CICell";

export interface ForestRow {
  id: string;
  label: string;
  sub?: string;
  delta: number;
  ci: [number, number];
  ciLabel: string;
  sourceKey: string;
  badge?: string;
}

const color = (lo: number, hi: number) => {
  const r = ciReading(lo, hi);
  return r.includes("above") ? "var(--pos)" : r.includes("below") ? "var(--neg)" : "var(--neutral)";
};

/** All paired comparisons on one axis with a zero line, coloured by the CI's reading against 0. */
export function ForestPlot({ rows, onOpen, name = "forest_plot" }: { rows: ForestRow[]; onOpen?: (id: string) => void; name?: string }) {
  const ref = useRef<SVGSVGElement>(null);
  if (!rows.length) return <p className="text-sm text-ink-3">No comparisons match the filter.</p>;
  const ext = Math.max(0.1, ...rows.flatMap((r) => [Math.abs(r.ci[0]), Math.abs(r.ci[1])])) * 1.08;
  const W = 1080, labelW = 400, plotW = 330, rowH = 22, top = 26;
  const H = top + rows.length * rowH + 14;
  const x = (v: number) => labelW + ((v + ext) / (2 * ext)) * plotW;
  return (
    <div>
      <div className="mb-2 flex justify-end gap-1 no-print">
        <Button variant="ghost" size="sm" onClick={() => exportSvg(ref.current, name)}><Download size={13} />{ARTIFACT ? "Copy SVG" : "SVG"}</Button>
        {!ARTIFACT && <Button variant="ghost" size="sm" onClick={() => exportPng(ref.current, name)}><Download size={13} />PNG</Button>}
      </div>
      {/* Desktop: one SVG (exportable). Mobile: cards. */}
      <svg ref={ref} viewBox={`0 0 ${W} ${H}`} className="hidden w-full md:block" role="img" aria-label="Forest plot of paired comparisons">
        <text x={x(0)} y={14} textAnchor="middle" fontSize={11} fill="var(--ink-3)">0</text>
        <text x={x(-ext)} y={14} fontSize={11} fill="var(--ink-3)">{(-ext).toFixed(2)}</text>
        <text x={x(ext)} y={14} textAnchor="end" fontSize={11} fill="var(--ink-3)">+{ext.toFixed(2)}</text>
        <line x1={x(0)} x2={x(0)} y1={top - 6} y2={H - 8} stroke="var(--ink-3)" strokeDasharray="3 3" />
        {rows.map((r, i) => {
          const y = top + i * rowH + rowH / 2;
          const c = color(r.ci[0], r.ci[1]);
          return (
            <g key={r.id} onClick={() => onOpen?.(r.id)} style={{ cursor: onOpen ? "pointer" : "default" }} data-source-key={r.sourceKey}>
              <title>{`${r.label}\n${r.ciLabel}\nsource: reports/results_v2.json → ${r.sourceKey}`}</title>
              {i % 2 === 0 && <rect x={0} y={y - rowH / 2} width={W} height={rowH} fill="var(--panel-2)" opacity={0.5} />}
              <text x={6} y={y + 4} fontSize={11.5} fill="var(--ink)">{r.label.length > 64 ? r.label.slice(0, 63) + "…" : r.label}</text>
              {r.badge && <text x={labelW - 8} y={y + 4} fontSize={10} textAnchor="end" fill="var(--warn)">{r.badge}</text>}
              <line x1={x(r.ci[0])} x2={x(r.ci[1])} y1={y} y2={y} stroke={c} strokeWidth={2.4} strokeLinecap="round" />
              <circle cx={x(r.delta)} cy={y} r={4} fill={c} />
              <text x={labelW + plotW + 12} y={y + 4} fontSize={11} fill="var(--ink-2)" fontFamily="var(--font-mono)">{r.ciLabel}</text>
            </g>
          );
        })}
      </svg>
      <ul className="space-y-2 md:hidden">
        {rows.map((r) => (
          <li key={r.id} className="rounded-md border border-line p-2">
            <Tip content={r.sourceKey}><p className="text-[12.5px] text-ink">{r.label} {r.badge && <span className="text-warn">· {r.badge}</span>}</p></Tip>
            <div className="mt-1 overflow-hidden"><CICell point={r.delta} ci={r.ci} label={r.ciLabel} sourceKey={r.sourceKey} signed domain={[-ext, ext]} compact
              onOpen={onOpen ? () => onOpen(r.id) : undefined} /></div>
          </li>
        ))}
      </ul>
    </div>
  );
}
