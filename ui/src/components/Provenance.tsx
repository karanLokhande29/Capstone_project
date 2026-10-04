import * as React from "react";
import { Tip } from "./ui/primitives";
import { RESULTS_FILE } from "@/lib/keys";
import { cn } from "@/lib/utils";

/** Any displayed number: hover shows its JSON key path and file; click opens the drawer when `onOpen` is given. */
export function Num({ value, sourceKey, file = RESULTS_FILE, className, onOpen, title }: {
  value: React.ReactNode; sourceKey: string; file?: string; className?: string; onOpen?: () => void; title?: string;
}) {
  const body = (
    <span className="block max-w-xs">
      {title && <span className="mb-1 block font-medium">{title}</span>}
      <span className="block text-ink-3">{file}</span>
      <code className="block break-all font-mono text-[11px] text-accent">{sourceKey}</code>
      {onOpen && <span className="mt-1 block text-ink-3">Click for evidence and lineage</span>}
    </span>
  );
  const Comp = onOpen ? "button" : "span";
  return (
    <Tip content={body}>
      <Comp
        type={onOpen ? "button" : undefined}
        onClick={onOpen}
        data-source-key={sourceKey}
        className={cn("num cursor-help decoration-dotted underline-offset-2 hover:underline", onOpen && "cursor-pointer", className)}
      >
        {value}
      </Comp>
    </Tip>
  );
}
