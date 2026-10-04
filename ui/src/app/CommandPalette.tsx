import { Command } from "cmdk";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import * as Dialog from "@radix-ui/react-dialog";
import { useData } from "@/data/store";
import { useDrawer } from "@/components/drawerState";
import { QUERIES } from "@/features/palette/queries";
import { ALL_ROUTES } from "./nav";

export function useCommandPalette() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setOpen((o) => !o); }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);
  return { open, setOpen };
}

/** ⌘K: typed deterministic queries, navigation, and global search over ids, entities, systems, findings, caveats and paper sentences. */
export function CommandPalette({ open, setOpen }: { open: boolean; setOpen: (v: boolean) => void }) {
  const nav = useNavigate();
  const openNode = useDrawer((s) => s.open);
  const s = useData((st) => st.snapshot);
  const [q, setQ] = useState("");
  const index = useMemo(() => {
    if (!s) return [];
    const rows: { id: string; label: string; group: string; node?: string }[] = [];
    s.findings.forEach((f) => rows.push({ id: `finding:${f.id}`, label: `${f.id} ${f.statement}`, group: "Findings", node: `finding:${f.id}` }));
    s.systems.forEach((x) => rows.push({ id: `system:${x.id}`, label: `${x.displayName} (${x.id})`, group: "Systems", node: `system:${x.id}` }));
    s.caveats.forEach((c) => rows.push({ id: `caveat:${c.id}`, label: `${c.id}: ${c.text}`, group: "Caveats", node: `caveat:${c.id}` }));
    s.gaps.forEach((g) => rows.push({ id: `gap:${g.id}`, label: `${g.id} ${g.expected}`, group: "Gaps", node: `gap:${g.id}` }));
    s.futureWork.forEach((f) => rows.push({ id: `fw:${f.rank}`, label: `Future Work #${f.rank} ${f.item}`, group: "Future Work", node: `fw:${f.rank}` }));
    s.t1Items.forEach((i) => rows.push({ id: `item:${i.id}`, label: `${i.id} ${i.sourceClass} ${i.subjectFamily ?? ""}`, group: "T1 items", node: `item:${i.id}` }));
    s.entityClasses.forEach((c) => rows.push({ id: `class:${c.id}`, label: `${c.label} (${c.kind})`, group: "Entity classes" }));
    s.directions.forEach((dd) => rows.push({ id: `md:${dd.id}`, label: `${dd.id} ${dd.title}`, group: "Directions" }));
    s.claims.filter((c) => c.doc !== "master").forEach((c) => rows.push({ id: `claim:${c.id}`, label: c.sentence, group: "Paper sentences", node: `claim:${c.id}` }));
    return rows;
  }, [s]);
  const hits = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (t.length < 2) return [];
    return index.filter((r) => r.label.toLowerCase().includes(t) || r.id.toLowerCase().includes(t)).slice(0, 40);
  }, [q, index]);
  const ql = q.trim().toLowerCase();
  const qMatches = QUERIES.filter((x) => !ql || x.label.toLowerCase().includes(ql) || x.keywords.some((k) => ql.includes(k) || k.includes(ql)));
  const navMatches = ALL_ROUTES.filter((r) => !ql || r.label.toLowerCase().includes(ql));
  const go = (fn: () => void) => { setOpen(false); setQ(""); fn(); };
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[70] bg-black/30" />
        <Dialog.Content aria-describedby={undefined} className="fixed left-1/2 top-[10vh] z-[71] w-[calc(100%-32px)] max-w-2xl -translate-x-1/2 overflow-hidden rounded-xl border border-line bg-panel shadow-2xl">
          <Dialog.Title className="sr-only">Command palette</Dialog.Title>
          <Command shouldFilter={false} label="Command palette" className="text-sm">
            <Command.Input value={q} onValueChange={setQ} autoFocus placeholder="Ask a typed question, jump to a screen, or search ids (t1_…, md_…)…"
              className="w-full border-b border-line bg-transparent px-4 py-3 text-[14px] outline-none placeholder:text-ink-3" />
            <Command.List className="max-h-[60vh] overflow-y-auto p-2">
              <Command.Empty className="px-3 py-6 text-center text-ink-3">No match. Try “different”, “F7”, “md_12925”.</Command.Empty>
              {qMatches.length > 0 && <Command.Group heading="Questions (deterministic)" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:text-ink-3">
                {qMatches.map((x) => (
                  <Command.Item key={x.id} value={`q-${x.id}`} onSelect={() => go(() => nav(`/assistant?q=${x.id}`))}
                    className="cursor-pointer rounded-md px-2 py-1.5 aria-selected:bg-accent-soft">{x.label}</Command.Item>
                ))}
              </Command.Group>}
              {navMatches.length > 0 && <Command.Group heading="Go to" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:text-ink-3">
                {navMatches.map((r) => (
                  <Command.Item key={r.to} value={`nav-${r.to}`} onSelect={() => go(() => nav(r.to))} className="cursor-pointer rounded-md px-2 py-1.5 aria-selected:bg-accent-soft">
                    {r.label}{r.product && <span className="ml-2 text-[10px] text-product">product</span>}
                  </Command.Item>
                ))}
              </Command.Group>}
              {hits.length > 0 && (
                <Command.Group heading="Search" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:text-ink-3">
                  {hits.map((h) => (
                    <Command.Item key={h.id} value={`s-${h.id}`} onSelect={() => go(() => {
                      if (h.node) openNode(h.node);
                      else if (h.id.startsWith("md:")) nav(`/atlas?md=${h.id.slice(3)}`);
                      else if (h.id.startsWith("class:")) nav(`/atlas?class=${encodeURIComponent(h.id.slice(6))}`);
                    })} className="cursor-pointer rounded-md px-2 py-1.5 aria-selected:bg-accent-soft">
                      <span className="mr-2 text-[10px] text-ink-3">{h.group}</span>{h.label.slice(0, 110)}
                    </Command.Item>
                  ))}
                </Command.Group>
              )}
            </Command.List>
          </Command>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
