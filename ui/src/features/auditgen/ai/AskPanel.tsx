import { useEffect, useState } from "react";
import { MessageSquare } from "lucide-react";
import { Badge, Card, CardBody } from "@/components/ui/primitives";
import { useAudit } from "../state";
import { HOSTED, live } from "../api";
import { ai } from "./aiApi";
import { useAi } from "./aiState";
import { AiBadge, Err, Meta, RunButton, Sentences, SourceChip } from "./AiParts";
import type { AskResult } from "./aiTypes";

const EXAMPLES = [
  "What must we do to verify a customer's identity?",
  "Which obligations have a quarterly reporting deadline?",
  "What are the rules on outsourcing to third parties?",
  "When must fraud be reported to the RBI?",
];

function Answer({ r }: { r: AskResult }) {
  const [ev, setEv] = useState(false);
  return (
    <Card><CardBody className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <MessageSquare size={14} className="text-ink-3" />
        <p className="text-[13px] font-semibold">{r.question}</p>
        <AiBadge />
        {r.abstained && <Badge tone="warn">abstained: not answerable reliably</Badge>}
        {r.attempts > 1 && <Badge tone="outline">retried once</Badge>}
      </div>
      {r.abstained ? <p className="text-[13px] text-ink-2">{r.answer}</p> : null}
      <Sentences items={r.sentences} empty="No sentence passed the check against the cited text." />
      <button className="text-[12px] text-accent hover:underline" onClick={() => setEv(!ev)}>{ev ? "Hide" : "Show"} the {r.evidence.length} evidence paragraphs retrieved</button>
      {ev && (
        <ul className="space-y-1 rounded-md border border-line bg-panel-2 p-2 text-[12px]">
          {r.evidence.map((e) => (
            <li key={e.label} className="flex flex-wrap items-baseline gap-1.5">
              <SourceChip s={e} /><span className="text-ink-2">{e.excerpt}</span>
              <span className="text-ink-3">· {e.direction_title} · {e.status}{e.deadline ? ` · ${e.deadline}` : ""}</span>
            </li>
          ))}
        </ul>
      )}
      <Meta r={r} />
    </CardBody></Card>
  );
}

const ALL = "__all__";
const PACK = "__pack__";

export default function AskPanel() {
  const { pack } = useAudit();
  const { store, run, model, canRun } = useAi();
  const [q, setQ] = useState("");
  // Hosted service: the assistant answers from every RBI obligation in the corpus by default, or one entity type's, or this pack's.
  const [scope, setScope] = useState(HOSTED ? ALL : PACK);
  const [classes, setClasses] = useState<string[]>([]);
  const [general, setGeneral] = useState<(AskResult & { scope?: string })[]>([]);
  useEffect(() => { if (HOSTED) void live.vocab().then((v) => setClasses(v.classes)).catch(() => {}); }, []);
  const onPack = scope === PACK;
  const shown = onPack ? (store.ask ?? []) : general;
  const history = shown.slice(0, 3).map((a) => ({ question: a.question })).reverse();
  const go = (question: string) => {
    if (!question.trim() || !canRun) return;
    if (onPack) {
      if (!pack) return;
      void run("ask", () => ai.ask(pack.pack_id, question, history, model), (s, r) => ({ ...s, ask: [r, ...(s.ask ?? [])].slice(0, 50) }));
    } else {
      void run("ask", async () => { const r = await ai.askAll(question, history, scope === ALL ? null : scope); setGeneral((g) => [r, ...g].slice(0, 50)); return r; }, (s) => s);
    }
    setQ("");
  };
  return (
    <div className="space-y-3">
      {HOSTED ? (
        <p className="text-[12.5px] text-ink-2">Ask any question about RBI Master Directions. Gemini answers only from the RBI paragraphs retrieved for the question
          (bge + BM25 over {onPack ? "this pack's register" : scope === ALL ? "every obligation in the corpus, all 11 entity types" : `the obligations that apply to ${scope}`}), cites each sentence,
          and the NLI verifier on our server checks every sentence against its citation; sentences it cannot confirm are held back. Unsupported answers are retried once, then the assistant abstains.
          Your question goes to Google's Gemini API: do not type confidential information.</p>
      ) : (
        <p className="text-[12.5px] text-ink-2">Ask a question about this pack's applicable obligations. The local model answers only from the retrieved RBI paragraphs
          (bge + BM25 over the register), cites each sentence, and the NLI verifier checks every sentence against its citation. Unsupported answers are retried once, then the assistant abstains.</p>
      )}
      <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); go(q); }} aria-label="Ask the pack">
        {HOSTED && (
          <select aria-label="Answer from" value={scope} onChange={(e) => setScope(e.target.value)} className="h-8 rounded-md border border-line bg-panel px-2 text-[12.5px]">
            <option value={ALL}>All RBI obligations</option>
            {classes.map((c) => <option key={c} value={c}>{c}</option>)}
            <option value={PACK}>This pack ({pack?.profile.name ?? "none loaded"})</option>
          </select>
        )}
        <input aria-label="Question" value={q} onChange={(e) => setQ(e.target.value)} maxLength={600} placeholder={onPack ? `Ask about ${pack?.profile.name ?? "this pack"}…` : "Ask about any RBI obligation…"}
          className="h-8 min-w-0 flex-1 rounded-md border border-line bg-panel px-2 text-[13px]" />
        <RunButton k="ask" onClick={() => go(q)} disabled={!q.trim()}>Ask</RunButton>
      </form>
      <div className="flex flex-wrap gap-1.5">
        {EXAMPLES.map((x) => <button key={x} disabled={!canRun} onClick={() => go(x)} className="rounded-full border border-line px-2 py-0.5 text-[11.5px] text-ink-2 hover:bg-panel-2 disabled:opacity-50">{x}</button>)}
      </div>
      <Err k="ask" />
      {shown.length === 0 && <p className="text-[12.5px] text-ink-3">{onPack ? "No questions asked for this pack yet." : "No questions asked yet. Try one of the examples."}</p>}
      {shown.map((r, i) => <Answer key={`${r.created_utc}-${i}`} r={r} />)}
    </div>
  );
}
