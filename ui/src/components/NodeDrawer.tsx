import * as Dialog from "@radix-ui/react-dialog";
import { ArrowLeft, Copy, ExternalLink, X } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useData } from "@/data/store";
import { reach } from "@/data/derive";
import type { Derived } from "@/data/derive";
import type { Snapshot } from "@/domain/types";
import { r1ClaimCheck, r2ByConstruction, r3Circularity, r5SingleExpert, r6NumberDrift, type RuleOutput } from "@/intelligence/rules";
import { resolveKey } from "@/lib/keys";
import { useDrawer, type DrawerTab } from "./drawerState";
import { CICell } from "./CICell";
import { CaveatChips } from "./CaveatChip";
import { Badge, Button, Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/primitives";
import { RuleCard } from "./RuleCard";
import { UnitDetail } from "@/features/different/UnitDetail";

const TABS: DrawerTab[] = ["overview", "evidence", "upstream", "downstream", "caveats", "source"];

export function nodeTitle(id: string, d: Derived | null, s: Snapshot | null): string {
  if (!d || !s) return id;
  if (id.startsWith("unit:")) return `Unit ${id.slice(5).replace("|", " → ")}`;
  if (id.startsWith("item:")) return `Item ${id.slice(5)}`;
  return d.nodes.get(id)?.title ?? id;
}

export function NodeLink({ id, children, className }: { id: string; children?: React.ReactNode; className?: string }) {
  const open = useDrawer((st) => st.open);
  const d = useData((st) => st.derived);
  const s = useData((st) => st.snapshot);
  return (
    <button type="button" onClick={() => open(id)} className={`cursor-pointer text-left text-accent hover:underline ${className ?? ""}`}>
      {children ?? nodeTitle(id, d, s)}
    </button>
  );
}

function rulesFor(id: string, s: Snapshot, d: Derived): RuleOutput[] {
  const out: RuleOutput[] = [];
  const up = reach(d, id, "up");
  const r5 = r5SingleExpert(id.startsWith("unit:") || id.startsWith("item:") ? ["task:T1"] : up);
  if (r5.verdict !== "ok") out.push(r5);
  if (id.startsWith("paired:")) {
    const p = s.paired.find((x) => `paired:${x.id}` === id);
    if (p?.family === "T2" && p.dataset) out.push(r2ByConstruction(p.dataset, s));
    if (p?.family === "T3") out.push(r3Circularity({ datasetId: "t3", circular: true, sourceKey: p.sourceKey }));
  }
  if (id.startsWith("metric:")) {
    const m = s.metrics.find((x) => `metric:${x.systemId}:${x.datasetId}:${x.metric}` === id);
    if (m?.datasetId.startsWith("t2_")) out.push(r2ByConstruction(m.datasetId, s));
    if (m?.datasetId === "t3") { const r3 = r3Circularity(m); if (r3.verdict !== "ok") out.push(r3); }
  }
  if (id.startsWith("claim:")) {
    const c = s.claims.find((x) => `claim:${x.id}` === id);
    if (c) {
      out.push(r1ClaimCheck(c, s.results));
      c.numbers.forEach((n) => out.push(r6NumberDrift(n)));
    }
  }
  if (id.startsWith("finding:")) {
    const f = s.findings.find((x) => `finding:${x.id}` === id);
    if (f) out.push(r1ClaimCheck({ sentence: `${f.statement} ${f.ciLabel ?? ""}`, numbers: [] }, s.results));
  }
  return out;
}

function Overview({ id, s, d }: { id: string; s: Snapshot; d: Derived }) {
  const [kind, ...rest] = id.split(":");
  const key = rest.join(":");
  const node = d.nodes.get(id);
  switch (kind) {
    case "unit": return <UnitDetail unitId={key} />;
    case "item": {
      const it = d.itemById.get(key);
      if (!it) return <Missing id={id} />;
      return (
        <div className="space-y-2 text-sm">
          <p>Source class <b>{it.sourceClass}</b> · {it.subjectFamily} · route <b>{it.route}</b> · gold flag <b>{it.goldFlag}</b></p>
          <p className="text-ink-3">Pointer {it.sourcePid} · clause {it.clausePath}</p>
          <ul className="space-y-1">{it.unitIds.map((u) => <li key={u}><NodeLink id={`unit:${u}`}>{u.split("|")[1]}</NodeLink></li>)}</ul>
        </div>
      );
    }
    case "finding": {
      const f = s.findings.find((x) => x.id === key)!;
      return (
        <div className="space-y-3 text-sm">
          <p className="text-[15px] font-medium">{f.statement}</p>
          {f.ci ? <CICell point={f.delta!} ci={f.ci} label={f.ciLabel} sourceKey={f.sourceKey} signed /> : <p className="num">{f.count} (key {f.sourceKey})</p>}
          <CaveatChips ids={f.caveatIds} />
          <p className="flex flex-wrap gap-2">Answers: {f.rqIds.map((r) => <NodeLink key={r} id={`rq:${r}`}>{r}</NodeLink>)}
            {(f.id === "F3" || f.id === "F7") && <Link to="/different?def=A" className="text-accent hover:underline">Open the 78 `different` units →</Link>}</p>
          <p className="text-ink-3">Stated in: {f.paperLocations.join(" · ")}</p>
        </div>
      );
    }
    case "rq": {
      const r = d.rqs.find((x) => x.id === key)!;
      return (
        <div className="space-y-2 text-sm">
          <blockquote className="border-l-2 border-accent pl-3 italic">{r.text}</blockquote>
          <p><Badge tone={r.answeredStatus === "answered" ? "pos" : "warn"}>{r.answeredStatus}</Badge> {r.statusReason}</p>
          {r.operationalisation && <p className="text-ink-3">{r.operationalisation}</p>}
        </div>
      );
    }
    case "paired": {
      const p = s.paired.find((x) => x.id === key)!;
      return (
        <div className="space-y-2 text-sm">
          <p className="font-medium">{p.label} · {p.metric}</p>
          <CICell point={p.delta} ci={p.ci} label={p.ciLabel} sourceKey={p.sourceKey} signed />
          <p className="text-ink-3">n = {p.n} {p.sameItems && "(same items)"} {p.preregistered && "· pre-registered"}</p>
          {p.family === "T1" && <CaveatChips ids={["single_expert", "scoring_asymmetry", ...(p.sameItems ? ["item_set_102"] : [])]} />}
        </div>
      );
    }
    case "metric": {
      const m = s.metrics.find((x) => `${x.systemId}:${x.datasetId}:${x.metric}` === key);
      if (!m) return <p className="text-sm">{node?.title}</p>;
      return (
        <div className="space-y-2 text-sm">
          <p>{node?.title} on <b>{m.datasetId}</b> (n = {m.n})</p>
          <CICell point={m.value} ci={m.ci} label={m.ciLabel} sourceKey={m.sourceKey} />
          {m.datasetId === "t1_gold_v1" && <CaveatChips ids={["single_expert", "scoring_asymmetry"]} />}
        </div>
      );
    }
    case "dataset": {
      const ds = d.datasets.find((x) => x.id === key)!;
      return <div className="space-y-1 text-sm"><p>Task {ds.task} · n = {ds.n}</p><p className="text-warn">{ds.biasStatement}</p><p className="text-ink-3">{ds.sourcePath}</p></div>;
    }
    case "system": {
      const x = s.systems.find((y) => y.id === key)!;
      return (
        <div className="space-y-2 text-sm">
          <p>{x.description}</p>
          {x.model && <p>Model: <code>{x.model}</code> · temperature 0 · minimal thinking · JSON mode</p>}
          {x.frozenPromptSha && <ul className="text-xs">{Object.entries(x.frozenPromptSha).map(([k, v]) => <li key={k}><code>{k}</code> <code className="text-ink-3">{v.slice(0, 16)}…</code></li>)}</ul>}
          <p className="text-ink-3">Components: {x.componentIds.join(", ") || "—"}</p>
        </div>
      );
    }
    case "caveat": {
      const c = s.caveats.find((x) => x.id === key)!;
      return <div className="space-y-1 text-sm"><Badge tone="warn">{c.kind}</Badge><p>{c.text}</p><p className="text-ink-3">Applies to: {c.appliesTo.join(", ")}</p></div>;
    }
    case "fw": {
      const f = s.futureWork.find((x) => String(x.rank) === key)!;
      return (
        <div className="space-y-2 text-sm">
          <p><b>What:</b> {f.what}</p><p><b>Why:</b> {f.why}</p><p><b>Effort:</b> {f.effort}</p>
          <p><b>Blast radius:</b> {f.blastRadius.join(" · ") || "—"}</p>
          {f.openQuestions.length > 0 && <p><b>Open questions:</b> {f.openQuestions.join(" ")}</p>}
        </div>
      );
    }
    case "gap": {
      const g = s.gaps.find((x) => x.id === key)!;
      return (
        <dl className="grid grid-cols-[110px_1fr] gap-x-3 gap-y-1 text-sm">
          <dt className="text-ink-3">Status</dt><dd>{g.status}</dd>
          <dt className="text-ink-3">Expected</dt><dd>{g.expected}</dd>
          <dt className="text-ink-3">Actual</dt><dd>{g.actual}</dd>
          <dt className="text-ink-3">Source</dt><dd>{g.sourceRefs.join(", ")}</dd>
          <dt className="text-ink-3">Reason</dt><dd>{g.reasonDetected}</dd>
          <dt className="text-ink-3">Fix</dt><dd>{g.suggestedFix}</dd>
          <dt className="text-ink-3">Part A</dt><dd>{g.fixedInPartA ?? "—"}</dd>
        </dl>
      );
    }
    case "claim": {
      const c = s.claims.find((x) => x.id === key)!;
      return <div className="space-y-1 text-sm"><p className="text-ink-3">{c.doc} · {c.section}</p><p>{c.sentence}</p></div>;
    }
    default:
      return node ? <div className="space-y-1 text-sm"><p>{node.title}</p>{node.subtitle && <p className="text-ink-3">{node.subtitle}</p>}</div> : <Missing id={id} />;
  }
}

function Missing({ id }: { id: string }) {
  return <p className="text-sm text-ink-3">No node <code>{id}</code> in this snapshot. Re-run <code>cd ui && npm run ingest</code>.</p>;
}

function Neighbours({ id, d, dir }: { id: string; d: Derived; dir: "up" | "down" }) {
  const direct = (dir === "up" ? d.inc.get(id) ?? [] : d.out.get(id) ?? []).map((e) => ({ node: dir === "up" ? e.from : e.to, rel: e.rel }));
  const all = reach(d, id, dir);
  if (!direct.length) return <p className="text-sm text-ink-3">Nothing {dir === "up" ? "upstream" : "downstream"} in the traceability graph.</p>;
  return (
    <div className="space-y-3 text-sm">
      <ul className="space-y-1.5">
        {direct.map((x) => (
          <li key={x.node} className="flex gap-2"><span className="w-28 shrink-0 text-[11px] text-ink-3">{x.rel}</span><NodeLink id={x.node} /></li>
        ))}
      </ul>
      <p className="text-xs text-ink-3">{all.length} node(s) reachable {dir === "up" ? "upstream" : "downstream"} in total.</p>
    </div>
  );
}

export function NodeDrawer() {
  const { node, tab, setTab, close, trail, open } = useDrawer();
  const s = useData((st) => st.snapshot);
  const d = useData((st) => st.derived);
  const rules = useMemo(() => (node && s && d ? rulesFor(node, s, d) : []), [node, s, d]);
  if (!s || !d) return null;
  const n = node ? d.nodes.get(node) : undefined;
  const caveatNodes = node ? [...new Set([...(d.out.get(node) ?? []).map((e) => e.to), ...reach(d, node, "up").flatMap((u) => (d.out.get(u) ?? []).map((e) => e.to))])]
    .filter((x) => x.startsWith("caveat:")) : [];
  const unitCaveats = node?.startsWith("unit:") || node?.startsWith("item:") ? ["caveat:single_expert", "caveat:candidates_shown", "caveat:scoring_asymmetry"] : [];
  const link = typeof window !== "undefined" ? window.location.href : "";
  return (
    <Dialog.Root open={!!node} onOpenChange={(o) => !o && close()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/20" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[640px] flex-col border-l border-line bg-panel shadow-2xl outline-none" aria-describedby={undefined}>
          <div className="flex items-start gap-2 border-b border-line px-4 py-3">
            <div className="min-w-0 flex-1">
              {trail.length > 0 && (
                <nav className="mb-1 flex flex-wrap items-center gap-1 text-[11px] text-ink-3" aria-label="Breadcrumbs">
                  {trail.map((t) => <button key={t} type="button" onClick={() => open(t)} className="max-w-[160px] cursor-pointer truncate hover:text-accent">{nodeTitle(t, d, s)}</button>)}
                  <span>›</span>
                </nav>
              )}
              <Dialog.Title className="text-[15px] font-semibold leading-snug">{node ? nodeTitle(node, d, s) : ""}</Dialog.Title>
              <p className="mt-0.5 text-[11px] text-ink-3"><code>{node}</code>{n?.sourceKey && <> · key <code>{n.sourceKey}</code></>}</p>
            </div>
            {trail.length > 0 && <Button variant="ghost" size="icon" aria-label="Back" onClick={() => open(trail[trail.length - 1])}><ArrowLeft size={16} /></Button>}
            <Dialog.Close asChild><Button variant="ghost" size="icon" aria-label="Close"><X size={16} /></Button></Dialog.Close>
          </div>
          <Tabs value={tab} onValueChange={(v) => setTab(v as DrawerTab)} className="flex min-h-0 flex-1 flex-col">
            <TabsList className="px-3">{TABS.map((t) => <TabsTrigger key={t} value={t} className="capitalize">{t}</TabsTrigger>)}</TabsList>
            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
              {node && <>
                <TabsContent value="overview"><Overview id={node} s={s} d={d} /></TabsContent>
                <TabsContent value="evidence">
                  <div className="space-y-3">
                    {n?.sourceKey && (
                      <div>
                        <p className="mb-1 text-xs text-ink-3">reports/results_v2.json → <code>{n.sourceKey}</code></p>
                        <pre className="max-h-64 overflow-auto rounded bg-panel-2 p-2 text-[11px]">{JSON.stringify(resolveKey(s.results, n.sourceKey), (_k, v) => typeof v === "number" ? Number(v.toFixed(6)) : v, 1)?.slice(0, 4000)}</pre>
                      </div>
                    )}
                    {rules.length ? rules.map((r, i) => <RuleCard key={i} r={r} />) : <p className="text-sm text-ink-3">No rule fired for this node.</p>}
                  </div>
                </TabsContent>
                <TabsContent value="upstream">{node.startsWith("unit:") || node.startsWith("item:")
                  ? <ul className="space-y-1 text-sm"><li><NodeLink id="dataset:t1_gold_v1" /></li><li><NodeLink id="task:T1" /></li><li><NodeLink id="system:comparator" /></li></ul>
                  : <Neighbours id={node} d={d} dir="up" />}</TabsContent>
                <TabsContent value="downstream">{node.startsWith("unit:") || node.startsWith("item:")
                  ? <p className="text-sm text-ink-3">Units feed the T1 metrics: <NodeLink id="finding:F3" />, <NodeLink id="finding:F7" />.</p>
                  : <Neighbours id={node} d={d} dir="down" />}</TabsContent>
                <TabsContent value="caveats">
                  {[...caveatNodes, ...unitCaveats].length === 0 ? <p className="text-sm text-ink-3">No caveat attached.</p> : (
                    <ul className="space-y-2 text-sm">
                      {[...new Set([...caveatNodes, ...unitCaveats])].map((c) => {
                        const cv = s.caveats.find((x) => `caveat:${x.id}` === c);
                        return cv ? <li key={c}><Badge tone="warn">{cv.kind}</Badge> {cv.text}</li> : null;
                      })}
                    </ul>
                  )}
                </TabsContent>
                <TabsContent value="source">
                  <div className="space-y-2 text-sm">
                    <p>Deep link to this view:</p>
                    <div className="flex items-center gap-2">
                      <code className="min-w-0 flex-1 truncate rounded bg-panel-2 px-2 py-1 text-[11px]">{link}</code>
                      <Button variant="outline" size="sm" onClick={() => navigator.clipboard?.writeText(link)}><Copy size={12} />Copy</Button>
                    </div>
                    {n?.sourceKey && <p>Key: <code>{n.sourceKey}</code> in <code>reports/results_v2.json</code> (sha256 {s.meta.sources.find((x) => x.path === "reports/results_v2.json")?.sha256.slice(0, 12)}…)</p>}
                    <p className="text-ink-3">Snapshot generated {s.meta.generatedUtc} by {s.meta.generator}.</p>
                    {node.startsWith("unit:") && (() => {
                      const u = d.unitById.get(node.slice(5));
                      const p = u?.goldMatchedPid ? s.pointers[u.goldMatchedPid] : null;
                      return p?.url ? <a className="inline-flex items-center gap-1 text-accent hover:underline" href={p.url} target="_blank" rel="noreferrer">RBI source PDF <ExternalLink size={12} /></a> : null;
                    })()}
                  </div>
                </TabsContent>
              </>}
            </div>
          </Tabs>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
