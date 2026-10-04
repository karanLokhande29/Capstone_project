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

export const usePersona = create<{ persona: Persona; set: (p: Persona) => void }>((set) => ({
  persona: read(),
  set(p) { try { localStorage.setItem("cc-persona", p); } catch { /* per-viewer convenience only */ } set({ persona: p }); },
}));
