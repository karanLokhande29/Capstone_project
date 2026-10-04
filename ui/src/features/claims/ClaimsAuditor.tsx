import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { useData } from "@/data/store";
import { useDrawer } from "@/components/drawerState";
import { PageHeader } from "@/components/Page";
import { Badge, Card, CardBody } from "@/components/ui/primitives";
import { RuleCard } from "@/components/RuleCard";
import { claimStatus, gate, type ClaimStatus } from "./claimStatus";
import { cn } from "@/lib/utils";

const MARK: Record<ClaimStatus, { m: string; tone: "pos" | "warn" | "neg" | "neutral"; label: string }> = {
  matched: { m: "✓", tone: "pos", label: "matched" }, overclaim: { m: "⚠", tone: "warn", label: "CI includes 0 but wording asserts an effect" },
  notfound: { m: "✗", tone: "neg", label: "not found" }, ambiguous: { m: "?", tone: "neutral", label: "not in public sources" }, text: { m: "·", tone: "neutral", label: "effect verb, no number" },
};

export default function ClaimsAuditor() {
  const s = useData((st) => st.snapshot)!;
  const open = useDrawer((st) => st.open);
  const [sp, setSp] = useSearchParams();
  const doc = sp.get("doc") ?? "all";
  const filter = sp.get("filter") ?? "all";
  const rows = useMemo(() => s.claims.map((c) => ({ c, ...claimStatus(c, s) })), [s]);
  const g = gate(s);
  const shown = rows.filter((r) => (doc === "all" || r.c.doc === doc) && (filter === "all" || (filter === "r1" ? r.status === "overclaim" : r.status === filter)));
  const set = (k: string, v: string) => { const n = new URLSearchParams(sp); n.set(k, v); setSp(n, { replace: true }); };
  return (
    <div>
      <PageHeader title="Claims ↔ Evidence Auditor" tier="SHOULD"
        subtitle="Every number in main.tex, the table .tex files and Master Document v2 linked to a results key (the same index logic as scripts/scan_documents.py, public sources only), plus R1 over-claim checks." />
      <Card className="mb-3"><CardBody className="flex flex-wrap items-center gap-4 text-[13px]">
        <b>Pre-submission gate:</b>
        <span className={g.unmatched ? "text-neg" : "text-pos"}>{g.unmatched} unmatched numbers</span>·
        <span className={g.overclaims ? "text-warn" : "text-pos"}>{g.overclaims} over-claims</span>·
        <span className={g.placeholders ? "text-neg" : "text-pos"}>{g.placeholders} placeholders</span>·
        <span className="text-ink-3">{g.ambiguous} sentence(s) with numbers only in private constants (G-22)</span>
      </CardBody></Card>
      <div className="mb-3 flex flex-wrap gap-3 text-[12.5px]">
        <label>Document <select className="rounded border border-line bg-panel px-1" value={doc} onChange={(e) => set("doc", e.target.value)}>
          {["all", "paper", "table", "master"].map((x) => <option key={x}>{x}</option>)}</select></label>
        <label>Status <select className="rounded border border-line bg-panel px-1" value={filter} onChange={(e) => set("filter", e.target.value)}>
          {["all", "matched", "r1", "notfound", "ambiguous", "text"].map((x) => <option key={x}>{x}</option>)}</select></label>
        <span className="text-ink-3">{shown.length} of {rows.length} sentences</span>
      </div>
      <div className="space-y-2">
        {shown.map(({ c, status, r1, r6 }) => (
          <Card key={c.id} className={cn(status === "overclaim" && "border-warn/60", status === "notfound" && "border-neg/60")}>
            <CardBody className="space-y-1.5 py-2.5">
              <div className="flex flex-wrap items-center gap-2 text-[11.5px] text-ink-3">
                <Badge tone={MARK[status].tone}>{MARK[status].m} {MARK[status].label}</Badge><span>{c.doc} · {c.section}</span>
                {c.doc !== "master" && <button type="button" className="cursor-pointer text-accent" onClick={() => open(`claim:${c.id}`)}>lineage →</button>}
              </div>
              <p className="text-[13px]">{c.sentence}</p>
              {c.numbers.length > 0 && (
                <p className="flex flex-wrap gap-1.5 text-[11px]">{c.numbers.map((n, i) => (
                  <span key={i} title={n.keys.join("\n") || r6[i].reason} className={cn("num rounded px-1", n.nKeys ? "bg-pos-soft text-pos" : "bg-panel-2 text-ink-3")}>{n.text}{n.nKeys ? ` → ${n.keys[0]?.slice(0, 48)}` : " ?"}</span>
                ))}</p>
              )}
              {(status === "overclaim" || (r1.verdict === "supported" && Boolean(r1.inputs.direction))) && <RuleCard r={r1} />}
            </CardBody>
          </Card>
        ))}
      </div>
    </div>
  );
}
