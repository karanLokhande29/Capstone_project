/**
 * Generative-AI client. Live mode calls the local backend (/api/auditgen/ai/*), which calls a local Ollama model on
 * 127.0.0.1 only, or the hosted service (Gemini writes, the same NLI verifier checks). Replay mode reads the recorded
 * outputs written by `python3 scripts/auditgen.py ai-samples`.
 */
import { API, HOSTED, hosted } from "../api";
import type {
  ActivityRow, AiStatus, AiStore, AskResult, CalendarResult, ChangeResult, DiffResult, DraftResult, ExplainResult, MemoResult, PlanResult, SuggestResult,
} from "./aiTypes";

async function json<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let msg = `${r.status}`;
    try { msg = ((await r.json()) as { detail?: string }).detail ?? msg; } catch { /* keep status */ }
    throw new Error(msg);
  }
  return (await r.json()) as T;
}

const post = async <T>(path: string, body: unknown = {}) => HOSTED
  ? hosted.call<T>("POST", `ai${path}`, body)
  : json<T>(await fetch(`${API}/ai${path}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }));
const get = async <T>(path: string) => (HOSTED ? hosted.get<T>(`/ai${path}`) : json<T>(await fetch(`${API}/ai${path}`)));
const pk = (id: string) => `/packs/${encodeURIComponent(id)}`;

export const ai = {
  status: () => get<AiStatus>("/status"),
  store: (id: string) => get<AiStore>(pk(id)),
  /** Hosted service: saves the memo DOCX through a blob link (a plain link could hit Azure's dead backend). */
  memoDocx: (id: string) => hosted.download(`/ai${pk(id)}/memo.docx`, false),
  activity: async () => json<ActivityRow[]>(await fetch(`${API}/ai/activity`)),
  ask: (id: string, question: string, history: { question: string }[], model?: string) => post<AskResult>(`${pk(id)}/ask`, { question, history, model }),
  explain: (id: string, row_id: string, model?: string) => post<ExplainResult>(`${pk(id)}/explain`, { row_id, model }),
  change: (id: string, row_id: string, model?: string) => post<ChangeResult>(`${pk(id)}/change`, { row_id, model }),
  memo: (id: string, model?: string) => post<MemoResult>(`${pk(id)}/memo`, { model }),
  memoDocxUrl: (id: string) => `${API}/ai${pk(id)}/memo.docx`,
  plan: (id: string, model?: string) => post<PlanResult>(`${pk(id)}/plan`, { model }),
  draft: (id: string, row_id: string, section: "register" | "gaps", company: string, model?: string) =>
    post<DraftResult>(`${pk(id)}/draft`, { row_id, section, company, model }),
  calendar: (id: string, entry_ids: string[] | null, model?: string) => post<CalendarResult>(`${pk(id)}/calendar`, { entry_ids, model }),
  diff: (id: string, row_id: string, model?: string) => post<DiffResult>(`${pk(id)}/diff`, { row_id, model }),
  suggest: (id: string, section: string, row_id: string, model?: string) => post<SuggestResult>(`${pk(id)}/suggest`, { section, row_id, model }),
  /** Hosted service only: the general assistant over every RBI obligation in the corpus (or one entity class's). */
  askAll: (question: string, history: { question: string }[], entity_class: string | null) => post<AskResult & { scope: string }>("/ask", { question, history, entity_class }),
};

/** Recorded AI outputs for a sample pack (offline replay). Missing file → an empty store. */
export async function replayStore(packId: string): Promise<AiStore> {
  try {
    const r = await fetch(`/auditgen/ai_${packId}.json`);
    if (!r.ok) return { pack_id: packId };
    return (await r.json()) as AiStore;
  } catch {
    return { pack_id: packId };
  }
}
