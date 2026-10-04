import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Copy, ExternalLink, Send, X } from "lucide-react";
import { useData, useSettings } from "@/data/store";
import { useDrawer } from "@/components/drawerState";
import { Badge, Button } from "@/components/ui/primitives";
import { matchQuery, QUERIES, type QueryResult } from "@/features/palette/queries";
import { cn } from "@/lib/utils";
import { NO_PROXY } from "@/lib/env";

export interface Turn {
  question: string;
  route: "palette" | "grounded_llm" | "none";
  state: "ok" | "off" | "quota" | "offline" | "blocked" | "pending" | "unmatched";
  result?: QueryResult;
  answer?: string;
  grounding?: "Exact" | "Partial" | "Unsupported";
  reason?: string;
  citations?: string[];
}

interface Status { assistant: { enabled: boolean; cap: number; used: number; remaining: number }; live: { available: boolean } }

export function useProxyStatus(active: boolean) {
  const [status, setStatus] = useState<Status | null>(null);
  const [offline, setOffline] = useState(false);
  useEffect(() => {
    if (!active) return;
    if (NO_PROXY) { setOffline(true); return; }
    let alive = true;
    fetch("/api/status").then((r) => (r.ok ? r.json() : Promise.reject())).then((j) => { if (alive) { setStatus(j); setOffline(false); } })
      .catch(() => alive && setOffline(true));
    return () => { alive = false; };
  }, [active]);
  return { status, offline, setStatus };
}

export function useAssistant() {
  const s = useData((st) => st.snapshot)!;
  const d = useData((st) => st.derived)!;
  const model = useData((st) => st.confidence);
  const enabled = useSettings((st) => st.assistantEnabled);
  const [turns, setTurns] = useState<Turn[]>([]);
  const ask = async (question: string, forcedId?: string) => {
    const q = forcedId ? QUERIES.find((x) => x.id === forcedId) ?? null : matchQuery(question);
    if (q) {
      const result = q.run({ s, d, model, now: new Date() });
      setTurns((t) => [...t, { question: q.label, route: "palette", state: "ok", result }]);
      return;
    }
    if (!enabled || NO_PROXY) {
      setTurns((t) => [...t, { question, route: "none", state: "unmatched",
        reason: NO_PROXY ? "No deterministic query matches. The hosted version answers typed questions only (the grounded-LLM route needs the local proxy). Try a suggested question or ⌘K search."
          : "No deterministic query matches, and the grounded-LLM route is off (Settings). Try one of the suggested questions or ⌘K search." }]);
      return;
    }
    setTurns((t) => [...t, { question, route: "grounded_llm", state: "pending" }]);
    try {
      const r = await fetch("/api/assistant", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ question }) });
      const j = await r.json();
      setTurns((t) => [...t.slice(0, -1), { question, route: "grounded_llm", state: j.state, answer: j.answer ?? undefined, grounding: j.grounding,
        reason: j.reason ?? j.message, citations: j.citations }]);
    } catch {
      setTurns((t) => [...t.slice(0, -1), { question, route: "grounded_llm", state: "offline", reason: "The local proxy is not running (cd ui && npm run server)." }]);
    }
  };
  return { turns, ask };
}

function copyText(t: Turn) {
  if (t.result) return `${t.result.title}\n${t.result.summary}\n${t.result.rows.map((r) => `- ${r.label}${r.detail ? ` (${r.detail})` : ""}`).join("\n")}\nSources: ${t.result.sourceKeys.join("; ")}`;
  return `${t.answer ?? ""}\nCitations: ${(t.citations ?? []).join("; ")}\nGrounding: ${t.grounding}`;
}

export function TurnView({ t }: { t: Turn }) {
  const open = useDrawer((st) => st.open);
  const nav = useNavigate();
  const firstNode = t.result?.rows.find((r) => r.node)?.node;
  return (
    <div className="space-y-1.5 rounded-lg border border-line bg-panel p-3 text-[13px]">
      <p className="font-medium">{t.question}</p>
      <div className="flex flex-wrap gap-1">
        <Badge tone={t.route === "palette" ? "accent" : "product"}>{t.route === "palette" ? "palette route" : t.route === "grounded_llm" ? "grounded LLM" : "not answered"}</Badge>
        {t.route === "palette" && <Badge tone="pos">confidence basis: exact (read from snapshot keys)</Badge>}
        {t.grounding && <Badge tone={t.grounding === "Exact" ? "pos" : t.grounding === "Partial" ? "warn" : "neg"}>grounding: {t.grounding}</Badge>}
        {t.state !== "ok" && t.state !== "pending" && <Badge tone="warn">{t.state}</Badge>}
      </div>
      {t.state === "pending" && <p className="animate-pulse text-ink-3">Retrieving chunks and asking the model…</p>}
      {t.result && (
        <>
          <p className="font-semibold">{t.result.title}</p>
          <p>{t.result.summary}</p>
          <ul className="max-h-64 space-y-1 overflow-y-auto">
            {t.result.rows.slice(0, 60).map((r, i) => (
              <li key={i} className="text-[12.5px]">
                {r.node ? <button type="button" className="cursor-pointer text-left text-accent hover:underline" onClick={() => open(r.node!)}>{r.label}</button>
                  : r.href ? <Link to={r.href} className="text-accent hover:underline">{r.label}</Link> : r.label}
                {r.detail && <span className="text-ink-3"> · {r.detail}</span>}
              </li>
            ))}
            {t.result.rows.length > 60 && <li className="text-ink-3">… {t.result.rows.length - 60} more</li>}
          </ul>
          {t.result.sourceKeys.length > 0 && <p className="text-[11px] text-ink-3">Exact: read from {t.result.sourceKeys.map((k) => <code key={k} className="mr-1">{k}</code>)}</p>}
        </>
      )}
      {t.answer && <p className="whitespace-pre-wrap">{t.answer}</p>}
      {t.reason && <p className={cn("text-[12.5px]", t.state === "ok" ? "text-ink-3" : "text-warn")}>{t.reason}</p>}
      {(t.result || t.answer) && (
        <div className="flex gap-1 pt-1">
          <Button variant="ghost" size="sm" onClick={() => navigator.clipboard?.writeText(copyText(t))}><Copy size={12} />Copy with citations</Button>
          {(firstNode || t.result?.href) && <Button variant="ghost" size="sm" onClick={() => (firstNode ? open(firstNode) : nav(t.result!.href!))}><ExternalLink size={12} />Open evidence</Button>}
        </div>
      )}
    </div>
  );
}

export function AssistantChat({ initial }: { initial?: string | null }) {
  const { turns, ask } = useAssistant();
  const enabled = useSettings((st) => st.assistantEnabled);
  const { status, offline } = useProxyStatus(enabled);
  const [q, setQ] = useState("");
  const asked = useMemo(() => ({ done: false }), []);
  useEffect(() => { if (initial && !asked.done) { asked.done = true; void ask("", initial); } }, [initial, asked, ask]);
  return (
    <div className="flex h-full flex-col gap-2">
      <div className="text-[11.5px] text-ink-3">
        {NO_PROXY ? "Hosted version: deterministic answers from the project snapshot. The grounded-LLM route runs only with the local proxy."
          : !enabled ? "Grounded-LLM route: off (Settings). Palette answers are deterministic and free."
          : offline ? "Grounded-LLM route: offline — start the proxy with `npm run server`."
            : status && !status.assistant.enabled ? "Grounded-LLM route: proxy has no ASSISTANT_GEMINI_API_KEY (off)."
              : status ? `Grounded-LLM route on · ${status.assistant.used}/${status.assistant.cap} calls today` : "Checking proxy…"}
      </div>
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto">
        {turns.length === 0 && (
          <div className="space-y-1">
            <p className="text-[12.5px] text-ink-2">Try a typed question:</p>
            {QUERIES.slice(0, 10).map((x) => <button key={x.id} type="button" onClick={() => ask("", x.id)} className="block cursor-pointer text-left text-[12.5px] text-accent hover:underline">{x.label}</button>)}
          </div>
        )}
        {turns.map((t, i) => <TurnView key={i} t={t} />)}
      </div>
      <form className="flex gap-1.5" onSubmit={(e) => { e.preventDefault(); if (q.trim()) { void ask(q.trim()); setQ(""); } }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about the project…" aria-label="Question"
          className="min-w-0 flex-1 rounded-md border border-line bg-panel px-2 py-1.5 text-[13px] outline-none focus:border-accent" />
        <Button type="submit" size="icon" aria-label="Ask"><Send size={14} /></Button>
      </form>
    </div>
  );
}

export function AssistantPanel({ onClose }: { onClose: () => void }) {
  return (
    <aside className="fixed inset-y-0 right-0 z-30 flex w-full max-w-[400px] flex-col border-l border-line bg-bg p-3 pt-3 shadow-xl" aria-label="Assistant">
      <div className="mb-2 flex items-center justify-between"><h2 className="text-[14px] font-semibold">Ask RBI-ObliBench</h2>
        <Button variant="ghost" size="icon" aria-label="Close assistant" onClick={onClose}><X size={16} /></Button></div>
      <AssistantChat />
      <p className="mt-2 text-[11px] text-ink-3">Research system. Not legal or compliance advice.</p>
    </aside>
  );
}
