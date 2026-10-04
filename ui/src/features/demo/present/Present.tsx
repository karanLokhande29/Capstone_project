import { useCallback, useEffect, useMemo, useState } from "react";
import { CheckCircle2, CircleDashed, XCircle } from "lucide-react";
import { Button, TooltipProvider } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";
import { fetchReplay, getHealth, liveAvailable, presenter, useApi } from "../api";
import { StatusBadge } from "../badges";
import { fetchJson, useHome, useJson } from "../data";
import { DecisionTrace, Microscope, ParagraphCards } from "../case/parts";
import { LIVE_STEP_IDS, STEPS, type StepId } from "./script";
import { Round } from "../play/Round";
import { cacheKey, useLiveRun } from "../lab/live";
import { LivePanel, SealedPanel } from "../lab/panels";
import FailureMap from "../cases/FailureMap";
import Triage from "../Triage";
import type { Pointer, T4Shard, Unit } from "../types";

type Check = { label: string; state: "pending" | "ok" | "fail" | "skip"; note?: string };

export default function Present() {
  const api = useApi();
  const home = useHome().data;
  const t4 = useJson<T4Shard>("t4.json").data;
  const [started, setStarted] = useState(false);
  const [i, setI] = useState(0);
  const [big, setBig] = useState(true);
  const [mode, setMode] = useState<"live" | "replay">("live");
  const [checks, setChecks] = useState<Check[]>([]);
  const [replayKey, setReplayKey] = useState<string | null>(null);
  const [replayOk, setReplayOk] = useState(false);
  const live = liveAvailable(api);
  const { run, start, replay } = useLiveRun();
  const steps = useMemo(() => STEPS.filter((s) => !LIVE_STEP_IDS.includes(s.id) || (s.id === "live" && (live || replayOk)) || (s.id === "edit" && live && presenter(api))), [live, replayOk, api]);
  const step = steps[Math.min(i, steps.length - 1)];

  const preflight = useCallback(async () => {
    const list: Check[] = [{ label: "Sealed data (home, cases, triage, results)", state: "pending" }, { label: "Comparator API /api/health", state: "pending" }, { label: "Prompt and rule hashes verified", state: "pending" }, { label: "Live model reachable", state: "pending" }, { label: "Replay recorded for the live step", state: "pending" }];
    setChecks([...list]);
    try { await Promise.all(["home.json", "cases/index.json", "triage_grid.json", "results.json", "t4.json"].map((n) => fetchJson(n))); list[0] = { ...list[0], state: "ok" }; } catch (e) { list[0] = { ...list[0], state: "fail", note: (e as Error).message }; }
    setChecks([...list]);
    try {
      const h = await getHealth(true);
      list[1] = { ...list[1], state: "ok", note: `mode ${h.mode}, streaming ${h.streaming}` };
      list[2] = { ...list[2], state: h.hashes.verified ? "ok" : "fail", note: h.hashes.mismatches?.join(", ") };
      list[3] = h.model.available && !h.model.mock ? { ...list[3], state: "ok", note: h.model.id }
        : h.model.mock ? { ...list[3], state: "skip", note: "test double only (mock model): the live step is labelled “Test double”, never “Live”" }
        : { ...list[3], state: "skip", note: h.model.reason ?? "no key: live steps hidden" };
    } catch (e) {
      list[1] = { ...list[1], state: "skip", note: (e as Error).message };
      list[2] = { ...list[2], state: "skip" };
      list[3] = { ...list[3], state: "skip", note: "no API: live steps hidden" };
    }
    setChecks([...list]);
    if (home) {
      const u = home.hero;
      const key = await cacheKey(String(u.provenance.prompt_sha256), String(u.provenance.rule_sha256), String(u.provenance.model), { mode: "benchmark", unitId: u.id });
      setReplayKey(key);
      let ok = false;
      try { const h = await getHealth(); if (h.model.available) { await start({ mode: "benchmark", unitId: u.id }); } } catch { /* no API */ }
      try { ok = !!(await fetchReplay(key)); } catch { ok = false; }
      setReplayOk(ok);
      list[4] = ok ? { ...list[4], state: "ok" } : { ...list[4], state: "skip", note: "none recorded: the live step is hidden in replay mode" };
      setChecks([...list]);
    }
  }, [home, start]);
  useEffect(() => { void preflight(); }, [preflight]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!started || (e.target as HTMLElement)?.tagName === "SELECT" || (e.target as HTMLElement)?.tagName === "INPUT") return;
      if (e.key === "ArrowRight") setI((x) => Math.min(x + 1, steps.length - 1));
      else if (e.key === "ArrowLeft") setI((x) => Math.max(x - 1, 0));
      else if (e.key.toLowerCase() === "r") setI(0);
      else if (e.key.toLowerCase() === "l") setMode((m) => (m === "live" ? "replay" : "live"));
      else if (e.key.toLowerCase() === "b") setBig((b) => !b);
      else if (e.key.toLowerCase() === "f") { if (document.fullscreenElement) void document.exitFullscreen?.(); else void document.documentElement.requestFullscreen?.().catch(() => undefined); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [started, steps.length]);

  if (!home) return <div className="grid min-h-screen place-items-center bg-bg text-[24px]">Loading…</div>;
  const hero = home.hero;

  if (!started) {
    return (
      <main className="min-h-screen bg-bg px-6 py-10 text-[20px] text-ink">
        <div className="mx-auto max-w-3xl">
          <h1 className="text-[36px] font-semibold">Presenter preflight</h1>
          <ul className="mt-6 space-y-3">
            {checks.map((c) => (
              <li key={c.label} className="flex items-start gap-3">
                {c.state === "ok" ? <CheckCircle2 className="mt-1 text-pos" /> : c.state === "fail" ? <XCircle className="mt-1 text-neg" /> : <CircleDashed className="mt-1 text-ink-3" />}
                <span>{c.label}{c.note && <span className="block text-[15px] text-ink-3">{c.note}</span>}</span>
              </li>
            ))}
          </ul>
          <p className="mt-6 text-[16px] text-ink-2">Steps in this session: {steps.map((s) => s.title).join(" → ")}. Keys: → next, ← back, R restart, L live/replay, B big text, F fullscreen.</p>
          <Button className="mt-6 h-12 px-6 text-[18px]" onClick={() => setStarted(true)} disabled={checks[0]?.state !== "ok"}>Start</Button>
        </div>
      </main>
    );
  }

  return (
    <TooltipProvider>
      <main className={cn("min-h-screen bg-bg px-6 py-8 text-ink", big ? "text-[24px] [&_p]:leading-snug" : "text-[18px]")} data-present>
        <div className="mx-auto max-w-6xl">
          <div className="flex flex-wrap items-center justify-between gap-3 text-[15px] text-ink-3">
            <span>{i + 1} / {steps.length} · {step.title}</span>
            <span className="flex gap-2"><StatusBadge status="sealed" />{step.id === "live" && run.source === "replay" && <StatusBadge status="replay" detail={run.recordedUtc ? `recorded ${run.recordedUtc.slice(0, 16).replace("T", " ")} UTC` : undefined} />}
              {step.id === "live" && run.source === "live" && (api.health?.model.mock ? <span className="rounded-full border border-line px-2 py-0.5 text-[11.5px]">Test double (mock model, not live)</span> : <StatusBadge status="live" />)}</span>
          </div>
          <h1 className="mt-3 text-[40px] font-semibold leading-tight [text-wrap:balance]">{step.headline}</h1>
          <div className="mt-6">
            <StepBody id={step.id} hero={hero} pointers={home.heroPointers} api={api} t4={t4} live={live && mode === "live"} replayKey={replayKey} run={run} start={start} replay={replay} />
          </div>
        </div>
      </main>
    </TooltipProvider>
  );
}

function StepBody({ id, hero, pointers, api, t4, live, replayKey, run, start, replay }: {
  id: StepId; hero: Unit; pointers: Record<string, Pointer>;
  api: ReturnType<typeof useApi>; t4: T4Shard | null; live: boolean; replayKey: string | null; run: ReturnType<typeof useLiveRun>["run"];
  start: ReturnType<typeof useLiveRun>["start"]; replay: ReturnType<typeof useLiveRun>["replay"];
}) {
  switch (id) {
    case "guess": return <Round key="present-guess" unit={hero} pointers={pointers} api={api} compact />;
    case "reveal": return <Round key="present-reveal" unit={hero} pointers={pointers} api={api} guess={hero.goldJudgement} compact />;
    case "microscope": return <div className="space-y-4 text-[16px]"><ParagraphCards unit={hero} pointers={pointers} api={api} /><Microscope unit={hero} compact /><DecisionTrace unit={hero} ruleSha={String(hero.provenance.rule_sha256)} /></div>;
    case "live": return (
      <div className="space-y-3 text-[16px]">
        <Button className="h-11 text-[17px]" onClick={() => (live ? void start({ mode: "benchmark", unitId: hero.id }) : replayKey && void replay(replayKey))}>{live ? "Re-run live" : "Play cached replay"}</Button>
        <div className="grid gap-4 md:grid-cols-2"><SealedPanel unit={hero} /><LivePanel run={run} unit={hero} mock={!!api.health?.model.mock} /></div>
      </div>
    );
    case "edit": return <p>Open the edit lab: <a className="text-accent underline" href="/lab/edit">/lab/edit</a> (control run first).</p>;
    case "triage": return <div className="text-[16px]"><Triage /></div>;
    case "failures": return <div className="text-[15px]"><FailureMap /></div>;
    case "close": return t4 ? (
      <div className="space-y-4">
        <p>Copying the evidence scores <b className="num">{t4.byType.concatenated.composite_score.mean.toFixed(3)}</b> on RePASs; a genuine answer scores <b className="num">{t4.byType.genuine.composite_score.mean.toFixed(3)}</b>.</p>
        <p className="text-ink-2">So we judge systems with expert labels, field by field, with every number traceable to a frozen file.</p>
      </div>
    ) : null;
  }
}
