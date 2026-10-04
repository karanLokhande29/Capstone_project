import { Link, useNavigate, useParams } from "react-router-dom";
import { useDrawer } from "@/components/drawerState";
import { PageHeader } from "@/components/Page";
import { Button, Card, CardBody } from "@/components/ui/primitives";

export const TOUR = [
  { title: "Start: three research questions", text: "Read the verbatim RQs and their answer status. RQ3's repair half is partial.", to: "/rq" },
  { title: "Chain 1 · RQ2 → comparator", text: "RQ2 → T1 → gold (106 items, 78 `different` units) → P2-002 + P2-004 → comparator vs class-aware → `different` F1 0.409 vs 0.154 → Finding 7 → paper §Results → caveats → Limitation → Future Work #2.", node: "rq:RQ2" },
  { title: "The 78 `different` units", text: "Every system's answer per unit; definition A/B; open any unit for the 13-field diff.", to: "/different?def=A" },
  { title: "Finding 7 itself", text: "+0.255 [+0.094, +0.411]: pre-registered, CI excludes 0. Follow Downstream to the paper sentence and Caveats to the single-expert gold.", node: "finding:F7" },
  { title: "Chain 2 · Finding 1 ← retrieval", text: "Class-aware hybrid 0.894 vs hybrid RRF 0.443 on t2_xclass_t1, with its bias statement and the by-construction caveat.", node: "finding:F1", tab: "upstream" },
  { title: "Chain 3 · T3 → ablation B → circular", text: "+0.462 from the temporal filter, never shown as a win: gold and filter share a parser. Future Work #6.", node: "dataset:t3", tab: "downstream" },
  { title: "Chain 4 · RQ3 → T4 → repair", text: "Concatenated − genuine +0.375 → repair ρ −0.126 → RQ3 partial → Future Work #7.", node: "rq:RQ3", tab: "downstream" },
  { title: "Reliability", text: "κ on a separate 30-item sample; gold is single-expert.", to: "/reliability" },
  { title: "Readiness", text: "What blocks the 10 Oct submission today.", to: "/readiness" },
] as const;

export default function Tour() {
  const { step = "0" } = useParams();
  const i = Math.min(TOUR.length - 1, Math.max(0, Number(step) || 0));
  const t = TOUR[i];
  const nav = useNavigate();
  const open = useDrawer((s) => s.open);
  const go = () => { if ("to" in t) nav(t.to); else open(t.node, ("tab" in t ? t.tab : "overview") as never); };
  return (
    <div>
      <PageHeader title="Reviewer / viva tour" tier="COULD" subtitle="A guided, deep-linkable walk through the traceability chains. Each step has its own URL (/tour/N)." />
      <Card><CardBody className="space-y-3">
        <p className="text-[12px] text-ink-3">Step {i + 1} of {TOUR.length}</p>
        <h2 className="text-[17px] font-semibold">{t.title}</h2>
        <p className="text-[13.5px]">{t.text}</p>
        <div className="flex flex-wrap gap-2">
          <Button onClick={go}>Open this step</Button>
          <Button variant="outline" disabled={i === 0} onClick={() => nav(`/tour/${i - 1}`)}>Previous</Button>
          <Button variant="outline" disabled={i === TOUR.length - 1} onClick={() => nav(`/tour/${i + 1}`)}>Next</Button>
        </div>
      </CardBody></Card>
      <ol className="mt-4 space-y-1 text-[13px]">{TOUR.map((x, k) => <li key={k}><Link to={`/tour/${k}`} className={k === i ? "font-semibold text-accent" : "text-ink-2 hover:text-accent"}>{k + 1}. {x.title}</Link></li>)}</ol>
    </div>
  );
}
