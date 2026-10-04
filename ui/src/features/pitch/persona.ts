import { create } from "zustand";

export type Persona = "compliance" | "researcher" | "investor";

export const PERSONAS: { id: Persona; label: string; short: string }[] = [
  { id: "compliance", label: "I work in compliance or risk", short: "Compliance" },
  { id: "researcher", label: "I'm a researcher or reviewer", short: "Research" },
  { id: "investor", label: "I'm evaluating the product", short: "Evaluator" },
];

function read(): Persona {
  try { return (localStorage.getItem("cc-persona") as Persona) || "compliance"; } catch { return "compliance"; }
}

function readClass(): string {
  try { return localStorage.getItem("cc-persona-class") ?? ""; } catch { return ""; }
}

export const usePersona = create<{ persona: Persona; myClass: string; set: (p: Persona) => void; setClass: (c: string) => void }>((set) => ({
  persona: read(),
  myClass: readClass(),
  set(p) { try { localStorage.setItem("cc-persona", p); } catch { /* per-viewer convenience only */ } set({ persona: p }); },
  setClass(c) { try { localStorage.setItem("cc-persona-class", c); } catch { /* per-viewer convenience only */ } set({ myClass: c }); },
}));
