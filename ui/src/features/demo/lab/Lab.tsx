import { useEffect, useState } from "react";
import { NavLink, useLocation, useSearchParams } from "react-router-dom";
import { AlertTriangle, Play, RotateCcw } from "lucide-react";
import { Button, Card, CardBody } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";
import { liveAvailable, testDouble, useApi, type ApiState } from "../api";
import { StatusBadge } from "../badges";
import { useCase, useHome, useIndex } from "../data";
import { Loading, PageHead } from "../DemoLayout";
import { CostMeter } from "./CostMeter";
import { EditLab } from "./EditLab";
import { cacheKey, useLiveRun } from "./live";
import { ErrorNote, LivePanel, SealedPanel } from "./panels";

const TABS = [{ to: "/lab", label: "Re-run a benchmark pair", end: true }, { to: "/lab/paste", label: "Paste (unvalidated)" }, { to: "/lab/edit", label: "Edit lab" }];

export default function Lab() {
  const api = useApi();
  const loc = useLocation();
  const tab = loc.pathname.endsWith("/paste") ? "paste" : loc.pathname.endsWith("/edit") ? "edit" : "rerun";
  const live = liveAvailable(api);
  return (
    <div>
      <PageHead eyebrow="Lab" title="Run the frozen comparator yourself.">
        The same prompt and fixed rule that produced the sealed benchmark output, called through a backend that verifies their hashes first. The key stays on the server.
      </PageHead>
      {!live && (
        <div className="mt-4 flex gap-2 rounded-lg border border-warn/50 bg-warn-soft px-4 py-3 text-[14px]" role="status">
          <AlertTriangle size={18} className="mt-0.5 shrink-0 text-warn" />
          <div>
            <p className="font-semibold">Live service unavailable — showing cached replays.</p>
            <p className="text-[13px] text-ink-2">{api.status === "checking" ? "Checking the comparator API…" : api.status === "offline" ? (api.reason ?? "No comparator API is reachable from this site.") : api.health?.model.reason ?? "The live model is not configured."}
              {" "}{api.status === "ready" ? `${api.health?.cache.replays ?? 0} cached replays are recorded.` : "No replays can be fetched without the API."} Sealed benchmark outputs are always shown.</p>
          </div>
        </div>
      )}
      {testDouble(api) && (
        <p className="mt-4 rounded-lg border border-line bg-panel-2 px-4 py-2 text-[13.5px]" role="status"><b>Test double.</b> This local server's “model” replays the sealed outputs; runs here are not live model calls.</p>
      )}
      <nav aria-label="Lab" className="mt-5 flex flex-wrap gap-1 border-b border-line">
        {TABS.map((t) => <NavLink key={t.to} to={t.to} end={t.end} className={({ isActive }) => cn("-mb-px border-b-2 px-3 py-2 text-[14px]", isActive ? "border-accent font-medium" : "border-transparent text-ink-3 hover:text-ink")}>{t.label}</NavLink>)}
      </nav>
      <div className="mt-5 grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="min-w-0">{tab === "rerun" ? <Rerun api={api} /> : tab === "paste" ? <Paste api={api} /> : <EditLab api={api} />}</div>
        <aside id="cost" className="scroll-mt-24"><Card><CardBody><p className="mb-2 text-[14px] font-semibold">Cost & latency</p><CostMeter /></CardBody></Card></aside>
      </div>
    </div>
  );
}

function Rerun({ api }: { api: ApiState }) {
  const [sp, setSp] = useSearchParams();
  const idx = useIndex().data;
  const home = useHome().data;
  const unitId = sp.get("unit") ?? home?.hero.id ?? null;
  const c = useCase(unitId);
  const { run, start, replay, stop } = useLiveRun();
  const [key, setKey] = useState<string | null>(null);
  const live = liveAvailable(api);
  const loaded = c.data?.unit ?? null;
  const loadedId = loaded?.id ?? null;
  useEffect(() => {
    stop();
    if (!loaded) return;
    void cacheKey(String(loaded.provenance.prompt_sha256), String(loaded.provenance.rule_sha256), String(loaded.provenance.model), { mode: "benchmark", unitId: loaded.id }).then(setKey);
  // eslint-disable-next-line react-hooks/exhaustive-deps -- re-key only when the selected unit changes
  }, [loadedId, stop]);
  if (!c.data) return <Loading what="the pair" />;
  const unit = c.data.unit;
  return (
    <div className="space-y-4">
      <label className="flex min-w-0 flex-col gap-1 text-[12.5px] text-ink-3">Benchmark pair
        <select value={unit.id} onChange={(e) => setSp({ unit: e.target.value }, { replace: true })} className="h-9 min-w-0 rounded-md border border-line bg-panel px-2 text-[13.5px] text-ink">
          {(idx?.units ?? [{ id: unit.id, src: unit.sourceClass, tgt: unit.targetClass, topic: unit.topic }]).map((u) => <option key={u.id} value={u.id}>{u.src} → {u.tgt} · {u.topic}</option>)}
        </select>
      </label>
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => void start({ mode: "benchmark", unitId: unit.id })} disabled={!live || run.phase === "receiving"}><Play size={15} />Re-run live</Button>
        {api.status === "ready" && key && <Button variant="outline" onClick={() => void replay(key)} disabled={run.phase === "receiving"}><RotateCcw size={15} />Play cached replay</Button>}
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <SealedPanel unit={unit} />
        <LivePanel run={run} unit={unit} mock={testDouble(api)} />
      </div>
      {run.phase === "error" && <ErrorNote run={run} onReplay={key && api.status === "ready" ? () => void replay(key) : undefined} />}
      {run.done && <CostMeter live={{ inputTokens: run.done.inputTokens, outputTokens: run.done.outputTokens, latencyMs: run.done.latencyMs }} />}
    </div>
  );
}

function Paste({ api }: { api: ApiState }) {
  const home = useHome().data;
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [ca, setCa] = useState("");
  const [cb, setCb] = useState("");
  const { run, start } = useLiveRun();
  const live = liveAvailable(api);
  const classes = home?.classes ?? [];
  return (
    <div className="space-y-3">
      <div className="rounded-lg border-2 border-neg/50 bg-neg-soft px-4 py-3 text-[14px]" role="note">
        <p className="font-semibold">Do not paste confidential or internal text.</p>
        <p className="text-ink-2">This runs on a third-party model API. Results on pasted text are unvalidated. The service keeps only a hash of the input and the structured output, never the text.</p>
      </div>
      <div className="flex flex-wrap items-center gap-2"><StatusBadge status="unvalidated" /><StatusBadge status="postpaper" /></div>
      <div className="grid gap-3 md:grid-cols-2">
        {[{ t: a, set: setA, c: ca, setC: setCa, label: "Rule A (source)" }, { t: b, set: setB, c: cb, setC: setCb, label: "Rule B (compare with)" }].map((x) => (
          <div key={x.label} className="space-y-1.5">
            <label className="flex flex-col gap-1 text-[12.5px] text-ink-3">{x.label}
              <textarea value={x.t} onChange={(e) => x.set(e.target.value.slice(0, 4000))} rows={7} maxLength={4000} className="rounded-md border border-line bg-panel p-2 text-[14px] text-ink" />
            </label>
            <label className="flex flex-col gap-1 text-[12.5px] text-ink-3">Institution type
              <select value={x.c} onChange={(e) => x.setC(e.target.value)} className="h-9 rounded-md border border-line bg-panel px-2 text-[13.5px] text-ink"><option value="">Choose…</option>{classes.map((c) => <option key={c}>{c}</option>)}</select>
            </label>
          </div>
        ))}
      </div>
      <Button disabled={!live || !a.trim() || !b.trim() || !ca || !cb || run.phase === "receiving"} onClick={() => void start({ mode: "paste", textA: a, textB: b, classA: ca, classB: cb })}><Play size={15} />Compare (unvalidated)</Button>
      {!live && <p className="text-[13px] text-ink-3">Paste mode needs the live service, which is not available on this site.</p>}
      {run.phase !== "idle" && <LivePanel run={run} unvalidated mock={testDouble(api)} />}
      {run.phase === "error" && <ErrorNote run={run} />}
    </div>
  );
}

