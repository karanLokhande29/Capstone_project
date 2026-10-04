import { useEffect, useState } from "react";
import { Clock } from "lucide-react";
import { useData } from "@/data/store";
import { Tip } from "@/components/ui/primitives";

export function useNow(ms = 60_000) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => { const t = setInterval(() => setNow(new Date()), ms); return () => clearInterval(t); }, [ms]);
  return now;
}

/** Live countdown to the CMT deadline (2026-10-10 23:59 IST; DECISIONS D-14). */
export function Countdown() {
  const deadline = useData((s) => s.snapshot?.meta.deadline);
  const now = useNow(30_000);
  if (!deadline) return null;
  const ms = new Date(deadline).getTime() - now.getTime();
  const past = ms < 0;
  const d = Math.floor(Math.abs(ms) / 86_400_000);
  const h = Math.floor((Math.abs(ms) % 86_400_000) / 3_600_000);
  return (
    <Tip content={<span>CMT deadline 10 Oct 2026, 23:59 IST (AISIGH–SD 2026). 6 pages is the hard limit.</span>}>
      <span className={`hidden items-center gap-1 rounded-md px-2 py-1 text-[12px] sm:inline-flex ${past ? "bg-neg-soft text-neg" : d < 2 ? "bg-warn-soft text-warn" : "bg-panel-2 text-ink-2"}`}>
        <Clock size={13} />{past ? `deadline passed ${d}d ${h}h ago` : `${d}d ${h}h to CMT`}
      </span>
    </Tip>
  );
}
