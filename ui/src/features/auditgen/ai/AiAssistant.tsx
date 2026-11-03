import { useNavigate, useParams } from "react-router-dom";
import { Cpu, RefreshCw, ShieldCheck, Sparkles } from "lucide-react";
import { Badge, Button, Card, CardBody, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { PageHeader } from "@/components/Page";
import { useAudit } from "../state";
import { AiProvider, useAi } from "./aiState";
import AskPanel from "./AskPanel";
import { ActivityPanel, BriefingPanel, CalendarPanel } from "./PackPanels";
import { ChangesPanel, DiffPanel, ObligationPanel } from "./RowPanels";
import { PUBLIC_DEMO } from "../parts";
import { HOSTED } from "../api";

const TABS = [
  { id: "ask", label: HOSTED ? "Ask (any RBI question)" : "Ask the pack", el: <AskPanel /> },
  { id: "obligations", label: "Obligation copilot", el: <ObligationPanel /> },
  { id: "changes", label: "Changes explained", el: <ChangesPanel /> },
  { id: "briefing", label: "Memo & action plan", el: <BriefingPanel /> },
  { id: "calendar", label: "Calendar check", el: <CalendarPanel /> },
  { id: "differential", label: "Differential 2nd opinion", el: <DiffPanel /> },
  { id: "activity", label: "How it works & log", el: <ActivityPanel /> },
];

function StatusCard() {
  const { mode } = useAudit();
  const { status, model, setModel, refreshStatus } = useAi();
  return (
    <Card className="mb-3"><CardBody className="flex flex-wrap items-center gap-2 text-[12.5px]">
      <Cpu size={15} className="text-ink-3" />
      {mode !== "live" && <Badge tone="warn">{PUBLIC_DEMO ? "read-only demo · recorded outputs of the local model (RBI quotes cut to 12 words)" : "offline replay · recorded AI outputs only (start the backend and Ollama to run the model)"}</Badge>}
      {mode === "live" && status?.available && <Badge tone="pos">{HOSTED ? "assistant ready" : "local model ready"} · {model ?? status.model}</Badge>}
      {mode === "live" && status && !status.available && <Badge tone="neg">{HOSTED ? "model unavailable" : "local model unavailable"}</Badge>}
      {mode === "live" && status && !status.available && <span className="text-ink-3">{status.reason}</span>}
      {mode === "live" && (status?.pulled.length ?? 0) > 1 && (
        <label className="flex items-center gap-1"><span className="text-ink-3">Model</span>
          <select aria-label="Local model" className="h-7 rounded-md border border-line bg-panel px-2" value={model ?? status?.model ?? ""}
            onChange={(e) => setModel(e.target.value || undefined)}>
            {status!.pulled.map((m) => <option key={m}>{m}</option>)}
          </select>
        </label>
      )}
      <span className="inline-flex items-center gap-1 text-ink-3"><ShieldCheck size={13} />{HOSTED && mode === "live"
        ? "hosted · Gemini writes, the NLI verifier on our server checks every sentence · RBI text and your questions only, no uploads"
        : "127.0.0.1 only · no remote API · NLI-verified"}</span>
      {mode === "live" && <Button size="sm" variant="ghost" className="ml-auto" onClick={() => void refreshStatus()}><RefreshCw size={12} />Recheck</Button>}
    </CardBody></Card>
  );
}

function Body() {
  const { tab } = useParams();
  const nav = useNavigate();
  const { pack } = useAudit();
  const cur = TABS.some((t) => t.id === tab) ? tab! : "ask";
  return (
    <div>
      <PageHeader title="AI assistant"
        subtitle={HOSTED
          ? <>An AI assistant for RBI compliance: ask any question about the Master Directions, or have it explain, summarise and plan from your audit pack. Gemini writes; every sentence cites RBI text and is checked by an NLI verifier, and unsupported sentences are held back. Outputs are drafts that need human review. The installed version runs the same features with a local model inside your network.</>
          : <>Generative-AI features on top of the audit pack, run by a <b>local</b> language model. Every sentence cites RBI text and is checked by the NLI verifier; unsupported sentences are held back. Outputs are drafts that need human review.</>}
        actions={<Badge tone="product"><Sparkles size={11} />Generative AI</Badge>} />
      <StatusCard />
      {!pack ? <p className="text-[13px] text-ink-3">{PUBLIC_DEMO ? "Loading the sample pack…" : "No pack loaded. Generate one on the Audit pack tab, or start the backend to load the samples."}</p> : (
        <Tabs value={cur} onValueChange={(v) => nav(`/auditgen/ai/${v}`)}>
          <TabsList aria-label="AI features">{TABS.map((t) => <TabsTrigger key={t.id} value={t.id}>{t.label}</TabsTrigger>)}</TabsList>
          {TABS.map((t) => <TabsContent key={t.id} value={t.id} className="pt-3">{t.el}</TabsContent>)}
        </Tabs>
      )}
    </div>
  );
}

export default function AiAssistant() {
  return <AiProvider><Body /></AiProvider>;
}
