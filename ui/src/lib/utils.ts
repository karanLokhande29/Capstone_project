import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const f3 = (x: number | null | undefined) => (x === null || x === undefined || Number.isNaN(x) ? "—" : x.toFixed(3));
export const pct = (x: number | null | undefined, d = 1) => (x === null || x === undefined ? "—" : `${(x * 100).toFixed(d)}%`);
export const fmtInt = (x: number) => x.toLocaleString("en-IN");

export function slug(s: string) {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
}

export function downloadText(name: string, text: string, type = "text/markdown") {
  if (import.meta.env.VITE_ARTIFACT === "1") {
    // Hosted viewers block downloads: copy instead.
    navigator.clipboard?.writeText(text).catch(() => undefined);
    return;
  }
  const blob = new Blob([text], { type });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

/** Days between today (local) and an ISO date (positive = in the future). */
export function daysUntil(iso: string, now = new Date()): number {
  const d = new Date(iso + (iso.length === 10 ? "T23:59:00+05:30" : ""));
  return (d.getTime() - now.getTime()) / 86_400_000;
}

export const SYSTEM_ORDER = ["majority", "p2002_candidates", "class_blind", "class_aware", "final_agentic", "ablation_a", "long_context", "comparator"];
export const LLM5 = ["class_blind", "class_aware", "final_agentic", "ablation_a", "long_context"];
