import { useState } from "react";
import { MessageSquare } from "lucide-react";
import { Badge, Card, CardBody } from "@/components/ui/primitives";
import { useAudit } from "../state";
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

export default function AskPanel() {
  const { pack } = useAudit();
  const { store, run, model, canRun } = useAi();
  const [q, setQ] = useState("");
  const history = (store.ask ?? []).slice(0, 3).map((a) => ({ question: a.question })).reverse();
  const go = (question: string) => {
    if (!pack || !question.trim() || !canRun) return;
    void run("ask", () => ai.ask(pack.pack_id, question, history, model), (s, r) => ({ ...s, ask: [r, ...(s.ask ?? [])].slice(0, 50) }));
    setQ("");
  };
  return (
    <div className="space-y-3">
      <p className="text-[12.5px] text-ink-2">Ask a question about this pack's applicable obligations. The local model answers only from the retrieved RBI paragraphs
        (bge + BM25 over the register), cites each sentence, and the NLI verifier checks every sentence against its citation. Unsupported answers are retried once, then the assistant abstains.</p>
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); go(q); }} aria-label="Ask the pack">
        <input aria-label="Question" value={q} onChange={(e) => setQ(e.target.value)} maxLength={600} placeholder={`Ask about ${pack?.profile.name ?? "this pack"}…`}
          className="h-8 flex-1 rounded-md border border-line bg-panel px-2 text-[13px]" />
        <RunButton k="ask" onClick={() => go(q)} disabled={!q.trim()}>Ask</RunButton>
      </form>
      <div className="flex flex-wrap gap-1.5">
        {EXAMPLES.map((x) => <button key={x} disabled={!canRun} onClick={() => go(x)} className="rounded-full border border-line px-2 py-0.5 text-[11.5px] text-ink-2 hover:bg-panel-2 disabled:opacity-50">{x}</button>)}
      </div>
      <Err k="ask" />
      {(store.ask ?? []).length === 0 && <p className="text-[12.5px] text-ink-3">No questions asked for this pack yet.</p>}
      {(store.ask ?? []).map((r, i) => <Answer key={`${r.created_utc}-${i}`} r={r} />)}
    </div>
  );
}
