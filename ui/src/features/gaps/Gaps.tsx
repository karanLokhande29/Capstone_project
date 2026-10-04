import { useSearchParams } from "react-router-dom";
import { Download } from "lucide-react";
import { useData } from "@/data/store";
import { useDrawer } from "@/components/drawerState";
import { PageHeader } from "@/components/Page";
import { Badge, Button, Card, CardBody } from "@/components/ui/primitives";
import { downloadText } from "@/lib/utils";
import { ARTIFACT } from "@/lib/env";
import type { GapFinding, GapStatus } from "@/domain/types";

const TONE: Record<GapStatus, "pos" | "warn" | "neg" | "neutral" | "accent"> = {
  complete: "pos", partial: "warn", missing: "neg", unclear: "neutral", conflicting: "neg", duplicate: "neutral", needs_validation: "accent",
};
const ORDER: GapStatus[] = ["conflicting", "missing", "needs_validation", "partial", "unclear", "duplicate", "complete"];

export function gapsMarkdown(gaps: GapFinding[]): string {
  const rows = gaps.map((g) => `| ${g.id} | ${g.status} | ${g.category} | ${g.expected} | ${g.actual} | ${g.sourceRefs.join(", ")} | ${g.reasonDetected} | ${g.suggestedFix} | ${g.fixedInPartA ?? "—"} |`);
  return ["# RBI-ObliBench gap list", "", "| ID | Status | Category | Expected | Actual | Source | Reason detected | Suggested fix | Fixed in Part A? |", "|---|---|---|---|---|---|---|---|---|", ...rows, ""].join("\n");
}

export default function Gaps() {
  const s = useData((st) => st.snapshot)!;
  const open = useDrawer((st) => st.open);
  const [sp, setSp] = useSearchParams();
  const f = sp.get("status") ?? "open";
  const gaps = [...s.gaps].sort((a, b) => ORDER.indexOf(a.status) - ORDER.indexOf(b.status));
  const shown = gaps.filter((g) => f === "all" || (f === "open" ? g.status !== "complete" : g.status === f));
  const counts = ORDER.map((st) => [st, s.gaps.filter((g) => g.status === st).length] as const).filter(([, n]) => n);
  return (
    <div>
      <PageHeader title="Gap Analysis" tier="MUST" subtitle="Seeded from the prompt's §10, each seed verified; added gaps G-19 onward. Part A fixes are marked."
        actions={<Button variant="outline" size="sm" onClick={() => downloadText("rbi_oblibench_gaps.md", gapsMarkdown(gaps))}><Download size={13} />{ARTIFACT ? "Copy Markdown" : "Markdown"}</Button>} />
      <div className="mb-3 flex flex-wrap gap-1.5">
        {[["open", s.gaps.filter((g) => g.status !== "complete").length] as const, ["all", s.gaps.length] as const, ...counts].map(([k, n]) => (
          <button key={k} type="button" onClick={() => setSp({ status: k }, { replace: true })}
            className={`cursor-pointer rounded-full border px-2.5 py-0.5 text-[12px] ${f === k ? "border-accent bg-accent-soft text-accent" : "border-line"}`}>{k.replace("_", " ")} · {n}</button>
        ))}
      </div>
      <div className="grid gap-2 lg:grid-cols-2">
        {shown.map((g) => (
          <Card key={g.id} className="cursor-pointer hover:border-accent" onClick={() => open(`gap:${g.id}`)}>
            <CardBody className="space-y-1 text-[12.5px]">
              <div className="flex flex-wrap items-center gap-2"><b>{g.id}</b><Badge tone={TONE[g.status]}>{g.status.replace("_", " ")}</Badge><span className="text-ink-3">{g.category}</span>
                {g.fixedInPartA && <Badge tone="accent">Part A: {g.fixedInPartA}</Badge>}</div>
              <p><span className="text-ink-3">Expected:</span> {g.expected}</p>
              <p><span className="text-ink-3">Actual:</span> {g.actual}</p>
              <p className="text-ink-3">Fix: {g.suggestedFix}</p>
            </CardBody>
          </Card>
        ))}
      </div>
    </div>
  );
}
