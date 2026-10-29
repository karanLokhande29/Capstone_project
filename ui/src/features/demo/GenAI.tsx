import { Link } from "react-router-dom";
import { ArrowDown, Cpu, Database, FileLock2, KeyRound, Repeat, ShieldCheck } from "lucide-react";
import { Card, CardBody } from "@/components/ui/primitives";
import { f3, fmtInt } from "@/lib/utils";
import { Block, FinePrint, Meaning } from "../pitch/ui";
import { useJson } from "./data";
import { Loading, LoadError, PageHead } from "./DemoLayout";
import { SYSTEM_NAME } from "./names";
import type { GenAIShard } from "./types";

// One section per generative-AI component, in the order of the GenAI presentation. Every number is read from genai.json.
const SECTIONS = [
  ["infra", "LLM infrastructure"], ["rag", "The RAG pipeline"], ["t1", "LLM systems on T1"], ["verifier", "The fact-checker"],
  ["dates", "Date grounding"], ["comparator", "Structured comparator"], ["repass", "Auditing a GenAI metric"],
  ["extensions", "Four extensions"], ["auditgen", "AuditGen AI assistant"], ["controls", "Controls and cost"],
] as const;

const PIPELINE = [
  ["Retrieve", "Keyword (BM25) and meaning (bge) search, merged by reciprocal-rank fusion; top 20"],
  ["Institution filter", "Keep Directions written for the institution type being asked about"],
  ["Date check", "Drop deleted text and attach amendments as of the question's date"],
  ["Generate", "The LLM answers from the top 5 paragraphs in JSON, citing paragraph ids"],
  ["Fact-check", "A local NLI model checks each sentence; retry once, otherwise decline to answer"],
];

const REPASS_TYPE: Record<string, string> = {
  genuine: "Genuine answer (LLM)", concatenated: "Obligation sentences pasted together", adv_negated: "Negated obligations", adv_offtopic: "Off-topic answer",
};

const AUDITGEN = [
  ["Ask the pack", "Cited answer over the pack's obligations"], ["Explain obligation", "Plain-language summary with a key quote"],
  ["Draft policy clause", "Scored by the gap analyser's rule"], ["Review suggestion", "Confirm or dispute; a person must agree"],
  ["Change explainer", "What an amendment changed"], ["Executive memo", "Every number must appear in the cited facts"],
  ["Action plan", "Each action points to a deadline, change or gap"], ["Calendar check", "Re-extracts a deadline; quote must occur"],
  ["Differential second opinion", "Decided by the frozen comparator rule"],
];

const signed = (x: number) => `${x > 0 ? "+" : x < 0 ? "−" : ""}${f3(Math.abs(x))}`;
const ci = ([lo, hi]: [number, number]) => `[${signed(lo)}, ${signed(hi)}]`;

export default function GenAI() {
  const g = useJson<GenAIShard>("genai.json");
  if (g.error) return <LoadError error={g.error} />;
  if (!g.data) return <Loading what="the generative-AI overview" />;
  const G = g.data;
  const V = G.verifier, X = G.extensions, C = G.comparator;
  const n = (i: number) => String(i + 1).padStart(2, "0");

  return (
    <div>
      <PageHead eyebrow="Generative AI" title="Generative AI in RBI-ObliBench: ten components, each one checked">
        From the LLM client to the AuditGen assistant: what each part does, how it is checked, and what it measured. Every number on this page is read from the
        project's published results file and its extension reports.
      </PageHead>

      <nav aria-label="Generative AI sections" className="mt-6 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
        {SECTIONS.map(([id, label], i) => (
          <a key={id} href={`#${id}`} className="rounded-lg border border-line bg-panel px-3 py-2 text-[13.5px] hover:border-accent">
            <span className="num mr-1.5 font-semibold text-accent">{n(i)}</span>{label}
          </a>
        ))}
      </nav>

      <Block id="infra" eyebrow={`GenAI ${n(0)}`} title="One LLM client, built for free-tier quotas and repeatable runs">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[
            { icon: Cpu, t: "Two providers", d: `Gemini first, Groq as fallback, over plain REST. A run never mixes two models' answers. Main model: ${G.model}.` },
            { icon: Repeat, t: "Repeatable", d: "Temperature 0 and a response cache keyed by sha256, so a rerun replays exactly." },
            { icon: Database, t: "Quota-safe", d: "A rate throttle, back-off, a per-run call cap and a daily ledger with a soft cap." },
            { icon: FileLock2, t: "Frozen prompts", d: "JSON-only prompts, locked by sha256; the pipeline refuses to run if one changes." },
            { icon: KeyRound, t: "Key hygiene", d: "Keys come only from a git-ignored .env file, travel in headers and are redacted from errors." },
            { icon: ShieldCheck, t: "Cache-only mode", d: "Tests and the LangGraph port replay with no key and no network." },
          ].map((x) => <Card key={x.t}><CardBody className="space-y-1.5"><x.icon size={18} className="text-accent" /><p className="text-[15px] font-semibold">{x.t}</p><p className="text-[13.5px] leading-relaxed text-ink-2">{x.d}</p></CardBody></Card>)}
        </div>
      </Block>

      <Block id="rag" eyebrow={`GenAI ${n(1)}`} title="An advanced RAG pipeline: hybrid search, two filters and a fact-check loop">
        <ol className="max-w-2xl">
          {PIPELINE.map(([t, d], i) => (
            <li key={t}>
              <div className="rounded-md border border-line px-3 py-2"><p className="text-[14px] font-medium"><span className="num mr-1.5 text-accent">{i + 1}</span>{t}</p><p className="text-[13px] text-ink-2">{d}</p></div>
              {i < PIPELINE.length - 1 && <div className="flex justify-center py-0.5 text-ink-3" aria-hidden><ArrowDown size={14} /></div>}
            </li>
          ))}
        </ol>
        <Meaning>The same pipeline was later rebuilt as a LangGraph agent and checked to give identical outputs (section {n(7)}). It does not use query rewriting, multi-hop or graph retrieval. <Link to="/method#lanes">How it fits the method</Link>.</Meaning>
      </Block>

      <Block id="t1" eyebrow={`GenAI ${n(2)}`} title="Spotting a real difference is where LLMs struggle">
        <div className="overflow-x-auto rounded-lg border border-line">
          <table className="w-full min-w-[640px] text-left text-[13.5px]">
            <thead className="bg-panel-2 text-[12.5px] text-ink-3"><tr><th className="px-3 py-1.5 font-medium">System</th><th className="px-3 text-right font-medium">Items</th><th className="px-3 text-right font-medium">3-way flag F1</th><th className="px-3 text-right font-medium">Judgement F1</th><th className="px-3 text-right font-medium">“Different” F1</th><th className="px-3 text-right font-medium">Coverage</th></tr></thead>
            <tbody>{G.t1.map((s) => (
              <tr key={s.id} className={s.id === "comparator" ? "border-t border-line bg-accent-soft/50 font-medium" : "border-t border-line"}>
                <td className="px-3 py-1.5">{SYSTEM_NAME[s.id]}</td><td className="num px-3 text-right">{s.n}</td><td className="num px-3 text-right">{f3(s.flag)}</td>
                <td className="num px-3 text-right">{f3(s.judgement)}</td><td className="num px-3 text-right">{f3(s.different)}</td><td className="num px-3 text-right">{f3(s.coverage)}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        <Meaning>{G.missedByEveryLlm} of {G.goldDifferent} real differences were missed by every one of the five LLM systems, usually with the right paragraph in front of them. <Link to="/cases/failures">See the Failure Map</Link>.</Meaning>
      </Block>

      <Block id="verifier" eyebrow={`GenAI ${n(3)}`} title="The fact-checker: safer answers, but fewer of them">
        <div className="grid gap-3 sm:grid-cols-3">
          <Stat value={signed(V.t4Unsupported.diff)} label={`Unsupported-sentence rate on T4 (${V.t4Unsupported.n} answers), CI ${ci(V.t4Unsupported.ci)}`} />
          <Stat value={signed(V.t1Flag.diff)} label={`T1 3-way flag F1 (${V.t1Flag.n} items), CI ${ci(V.t1Flag.ci)}`} warn />
          <Stat value={signed(V.t1Coverage.diff)} label={`T1 coverage: more questions declined, CI ${ci(V.t1Coverage.ci)}`} warn />
        </div>
        <Meaning>Turning the fact-checker on stops unsupported sentences, mostly by declining to answer (T4 abstention {signed(V.t4Abstention.diff)}). On the main task it costs accuracy: a small NLI model judging one sentence against a whole paragraph rejects correct paraphrases.</Meaning>
      </Block>

      <Block id="dates" eyebrow={`GenAI ${n(4)}`} title="Give the model the date status, and it uses it">
        <div className="flex flex-wrap items-end gap-6">
          <div><p className="text-[13px] text-ink-3">Without the date check</p><p className="num text-[40px] font-semibold text-ink-3">{f3(G.temporal.off)}</p></div>
          <span aria-hidden className="pb-3 text-[24px] text-accent">→</span>
          <div><p className="text-[13px] text-ink-3">With the date check</p><p className="num text-[40px] font-semibold">{f3(G.temporal.on)}</p></div>
        </div>
        <p className="mt-2 text-[14px] text-ink-2">T3 status exact match on {G.temporal.n} items: {signed(G.temporal.diff)}, CI {ci(G.temporal.ci)}.</p>
        <FinePrint>T3's answers come from the same amendment parser that feeds the date check, so this measures whether the LLM uses the date information, not whether the parser is right.</FinePrint>
      </Block>

      <Block id="comparator" eyebrow={`GenAI ${n(5)}`} title="Structured comparator: the LLM extracts, a frozen rule decides">
        <div className="grid gap-3 sm:grid-cols-3">
          <Stat value={`${f3(C.differentGain.b)} → ${f3(C.differentGain.a)}`} label="“Different” F1: LLM with institution-filtered search → comparator" />
          <Stat value={signed(C.differentGain.diff)} label={`Pre-registered gain, CI ${ci(C.differentGain.ci)}`} />
          <Stat value={`${f3(C.recall)} / ${f3(C.precision)}`} label="“Different” recall / precision: it over-flags, so a flag means look closer" warn />
        </div>
        <Meaning>The model fills 13 named fields for both paragraphs and marks each one equal, different or one-sided; it never gives the verdict. The rule was frozen by sha256 on {C.frozenAtUtc.slice(0, 10)}, before any test run. <Link to="/lab">Re-run it live in the Lab</Link>.</Meaning>
      </Block>

      <Block id="repass" eyebrow={`GenAI ${n(6)}`} title="Auditing a GenAI metric: can RePASs be gamed on RBI text?">
        <p className="mb-3 max-w-3xl text-[14.5px] leading-relaxed text-ink-2">An LLM ({G.repass.llm}) drafted {G.repass.n} questions and genuine, cited answers. Three answer types made without an LLM were then scored by RePASs, a faithfulness metric for LLM answers.</p>
        <div className="max-w-xl overflow-x-auto rounded-lg border border-line">
          <table className="w-full text-left text-[13.5px]">
            <thead className="bg-panel-2 text-[12.5px] text-ink-3"><tr><th className="px-3 py-1.5 font-medium">Answer type</th><th className="px-3 text-right font-medium">RePASs</th><th className="px-3 font-medium">Fools it?</th></tr></thead>
            <tbody>{Object.entries(G.repass.byType).map(([k, v]) => (
              <tr key={k} className="border-t border-line"><td className="px-3 py-1.5">{REPASS_TYPE[k] ?? k}</td><td className="num px-3 text-right">{f3(v)}</td>
                <td className="px-3 text-ink-2">{k === "genuine" ? "baseline" : G.repass.verdicts[k] === "reproduces" ? "yes, scores higher" : "no"}</td></tr>
            ))}</tbody>
          </table>
        </div>
        <Meaning>Pasting obligation sentences together scores {signed(G.repass.gaming.mean)} above a genuine answer (CI [{signed(G.repass.gaming.ci_low)}, {signed(G.repass.gaming.ci_high)}]). <Link to="/results">Try the RePASs playground</Link>.</Meaning>
      </Block>

      <Block id="extensions" eyebrow={`GenAI ${n(7)}`} title="Four extensions beyond the main systems">
        <div className="grid gap-3 sm:grid-cols-2">
          <Ext t="Cross-encoder reranking" d={`Standard-search 3-way flag F1 ${signed(X.rerank.diff)}, CI ${ci(X.rerank.ci)}. Reranking hurt.`} />
          <Ext t="A larger open model" d={`Groq gpt-oss-120b on ${X.groq.n} items: 3-way flag F1 ${f3(X.groq.flag)}, against Gemini ${signed(X.groq.vsGemini.diff)} (CI ${ci(X.groq.vsGemini.ci)}), a tie. “Different” F1 ${f3(X.groq.different)}, no better.`} />
          <Ext t="IndiaFinBench transfer" d={`Accuracy ${f3(X.indiafinbench.accuracy)} on ${fmtInt(X.indiafinbench.n)} of ${fmtInt(X.indiafinbench.of)} items; regulatory interpretation ${f3(X.indiafinbench.byTask.regulatory_interpretation)}, numerical reasoning ${f3(X.indiafinbench.byTask.numerical_reasoning)}.`} />
          <Ext t="LangGraph port" d={`${X.langgraph.passed} of ${X.langgraph.systems} systems × ${X.langgraph.items} items replayed from the cache with identical prompts and outputs; ${X.langgraph.cacheMisses} API calls.`} />
        </div>
      </Block>

      <Block id="auditgen" eyebrow={`GenAI ${n(8)}`} title="AuditGen: nine assistant features on a local model">
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {AUDITGEN.map(([t, d]) => <div key={t} className="rounded-md border border-line px-3 py-2"><p className="text-[14px] font-medium">{t}</p><p className="text-[13px] text-ink-2">{d}</p></div>)}
        </div>
        <Meaning>AuditGen runs on your own machine with Ollama ({G.auditgen.models.join(", then ")}) and refuses any host that is not localhost; it is not part of this public site. Every sentence must pass NLI against its cited paragraph, output is marked “AI draft, needs review”, and logs keep hashes, never text. Its accuracy has not yet been measured against gold labels.</Meaning>
      </Block>

      <Block id="controls" eyebrow={`GenAI ${n(9)}`} title="Controls and cost">
        <ul className="max-w-3xl list-disc space-y-2 pl-5 text-[14.5px] leading-relaxed text-ink-2">
          <li><b className="text-ink">Human labels kept apart from AI output.</b> A rater marked “AI-assisted” is left out of every human agreement figure; LLM outputs are system outputs, never labels.</li>
          <li><b className="text-ink">Fixed before testing.</b> Prompts and rules frozen by sha256, verdict rules pre-registered, predictions sealed before any comparison with the expert labels.</li>
          <li><b className="text-ink">Cite or drop.</b> Every generated sentence cites a paragraph and must pass the NLI check; otherwise the system declines.</li>
          <li><b className="text-ink">Free tiers only.</b> {fmtInt(G.usage.p4Calls)} Gemini calls for every retrieval system over {G.usage.p4QuotaDays} quota days, {G.usage.t4GroqCalls} Groq calls to build T4 and {G.usage.smokeCalls} smoke tests. The comparator's own run is on the <Link to="/method#cost">Method page</Link>.</li>
        </ul>
      </Block>
    </div>
  );
}

function Stat({ value, label, warn }: { value: string; label: string; warn?: boolean }) {
  return (
    <Card><CardBody className="space-y-1">
      <p className={`num text-[28px] font-semibold ${warn ? "text-warn" : "text-ink"}`}>{value}</p>
      <p className="text-[13px] leading-relaxed text-ink-2">{label}</p>
    </CardBody></Card>
  );
}

function Ext({ t, d }: { t: string; d: string }) {
  return <Card><CardBody className="space-y-1.5"><p className="text-[15px] font-semibold">{t}</p><p className="text-[13.5px] leading-relaxed text-ink-2">{d}</p></CardBody></Card>;
}
