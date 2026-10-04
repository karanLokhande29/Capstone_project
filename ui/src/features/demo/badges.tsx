import { Archive, FlaskConical, History, PencilLine, Radio, Split } from "lucide-react";
import { Tip } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";

/** Status badge taxonomy (Demo Build Spec §0.2). One component, used everywhere. */
export type Status = "sealed" | "live" | "replay" | "unvalidated" | "postpaper" | "mismatch";

const META: Record<Status, { label: string; tip: string; cls: string; Icon: typeof Archive }> = {
  sealed: { label: "Benchmark · sealed", tip: "Read from the frozen phase-4 outputs and the expert gold labels. Nothing here was produced just now.", cls: "border-line bg-panel-2 text-ink-2", Icon: Archive },
  live: { label: "Live re-run", tip: "Produced just now by the frozen prompt and rule through the backend.", cls: "border-accent/50 bg-accent-soft text-accent", Icon: Radio },
  replay: { label: "Cached replay", tip: "A previously recorded live run, replayed. The recording time is shown next to it.", cls: "border-warn/50 bg-warn-soft text-warn", Icon: History },
  unvalidated: { label: "Unvalidated input", tip: "Text pasted or edited by a user. No expert label exists; this is outside what was evaluated.", cls: "border-neg/40 bg-neg-soft text-neg", Icon: PencilLine },
  postpaper: { label: "Post-paper", tip: "Analysis that is not in the paper (confidence model, triage, sensitivity analysis, edit lab).", cls: "border-product/40 bg-product-soft text-product", Icon: FlaskConical },
  mismatch: { label: "Live ≠ sealed", tip: "This live re-run differs from the sealed benchmark output. Open the field-level diff.", cls: "border-neg/50 bg-neg-soft text-neg", Icon: Split },
};

export function StatusBadge({ status, detail, className }: { status: Status; detail?: string; className?: string }) {
  const m = META[status];
  return (
    <Tip content={<span className="block max-w-xs">{m.tip}{detail ? ` ${detail}` : ""}</span>}>
      <span data-status={status} tabIndex={0}
        className={cn("inline-flex cursor-help items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11.5px] font-medium", m.cls, className)}>
        <m.Icon size={12} aria-hidden />{m.label}{detail && <span className="font-normal opacity-80">· {detail}</span>}
      </span>
    </Tip>
  );
}

export const PostPaper = ({ className }: { className?: string }) => <StatusBadge status="postpaper" className={className} />;
