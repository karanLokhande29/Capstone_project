import { useEffect, useMemo, useState } from "react";
import { ArrowRight, RotateCcw } from "lucide-react";
import { Button, Card, CardBody } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";
import { useApi } from "../api";
import { fetchJson, shardName, useIndex } from "../data";
import { Loading, LoadError, PageHead } from "../DemoLayout";
import { SYSTEM_NAME } from "../names";
import type { Judgement, Pointer, Shard, Unit } from "../types";
import { CasesNav } from "../cases/CasesNav";
import { Round, score } from "./Round";

type Mode = "curated" | "random";
const STORE = "rbiob-play-v1";

function shuffle<T>(xs: T[], seed: number): T[] {
  const a = [...xs];
  let s = seed >>> 0;
  for (let i = a.length - 1; i > 0; i--) {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    const j = s % (i + 1);
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function remember(v: unknown) { try { localStorage.setItem(STORE, JSON.stringify(v)); } catch { /* per-viewer convenience only */ } }
function recall(): { best?: number } { try { return JSON.parse(localStorage.getItem(STORE) ?? "{}") as { best?: number }; } catch { return {}; } }

export default function Play() {
  const idx = useIndex();
  const api = useApi();
  const [mode, setMode] = useState<Mode>("curated");
  const [seed, setSeed] = useState(() => Math.floor(Math.random() * 2 ** 31));
  const [pos, setPos] = useState(0);
  const [current, setCurrent] = useState<{ unit: Unit; pointers: Record<string, Pointer> } | null>(null);
  const [played, setPlayed] = useState<{ unit: Unit; guess: Judgement }[]>([]);
  const order = useMemo(() => {
    if (!idx.data) return [];
    const pool = mode === "curated" ? idx.data.units.filter((u) => u.missedA) : idx.data.units;
    return shuffle(pool.map((u) => u.id), seed);
  }, [idx.data, mode, seed]);
  const id = order[pos] ?? null;
  useEffect(() => {
    if (!id) return;
    let live = true;
    setCurrent(null);
    fetchJson<Shard>(`cases/${shardName(id.split("|")[0])}.json`).then((s) => {
      const unit = s.units.find((u) => u.id === id)!;
      if (live) setCurrent({ unit, pointers: s.pointers });
    });
    return () => { live = false; };
  }, [id]);
  const restart = (m: Mode) => { setMode(m); setSeed(Math.floor(Math.random() * 2 ** 31)); setPos(0); setPlayed([]); };
  const sc = score(played);
  const guessed = played.find((p) => p.unit.id === id)?.guess ?? null;
  const prevBest = recall().best;

  if (idx.error) return <LoadError error={idx.error} />;
  return (
    <div>
      <PageHead eyebrow="Cases · Play" title="Can you spot the difference?">
        Two rules on the same topic, for two kinds of regulated institution. Decide whether the second institution type has the same requirement,
        a different one, or no matching rule at all. Then see what the expert, five AI systems and the structured comparator said.
      </PageHead>
      <CasesNav />
      <div className="mt-4 flex flex-wrap gap-2" role="radiogroup" aria-label="Mode">
        {([["curated", "Curated hard cases"], ["random", "Random draw"]] as [Mode, string][]).map(([m, label]) => (
          <button key={m} type="button" role="radio" aria-checked={mode === m} onClick={() => restart(m)}
            className={cn("rounded-full border px-3 py-1 text-[13px]", mode === m ? "border-accent bg-accent text-white dark:text-black" : "border-line bg-panel text-ink-2")}>{label}</button>
        ))}
      </div>
      <p className="mt-2 text-[12.5px] text-ink-3">
        {mode === "curated" ? "Chosen because every AI system missed them; your score here is not comparable to overall accuracy." : "Drawn uniformly from all 412 expert-labelled comparisons."}
      </p>

      <Card className="mt-4"><CardBody className="flex flex-wrap items-center gap-x-6 gap-y-1 text-[14px]" aria-live="polite">
        {sc.n === 0 ? <span className="text-ink-3">Your score appears after the first round.</span> : (
          <>
            <span><b className="num">You {sc.you}/{sc.n}</b></span>
            <span>Best single AI system {sc.best}/{sc.n} <span className="text-[12px] text-ink-3">({SYSTEM_NAME[sc.bestSystem]})</span></span>
            <span>Structured comparator {sc.cmp}/{sc.n}</span>
          </>
        )}
        {prevBest != null && <span className="text-[12px] text-ink-3">Your best earlier session: {prevBest} correct</span>}
      </CardBody></Card>

      <section className="mt-5" aria-label={`Round ${pos + 1}`}>
        <p className="mb-2 text-[13px] text-ink-3">Round {pos + 1} of {order.length}{current ? ` · ${current.unit.topic ?? ""} · ${current.unit.sourceClass} → ${current.unit.targetClass}` : ""}</p>
        {!current ? <Loading what="the round" /> : (
          <Round key={current.unit.id} unit={current.unit} pointers={current.pointers} api={api} guess={guessed}
            onGuess={(g) => { const next = [...played, { unit: current.unit, guess: g }]; setPlayed(next); const s = score(next); remember({ best: Math.max(prevBest ?? 0, s.you) }); }} />
        )}
        <div className="mt-5 flex flex-wrap gap-2">
          {guessed && pos < order.length - 1 && <Button onClick={() => setPos(pos + 1)}>Next round <ArrowRight size={15} /></Button>}
          <Button variant="ghost" onClick={() => restart(mode)}><RotateCcw size={15} />New session</Button>
        </div>
      </section>
    </div>
  );
}
