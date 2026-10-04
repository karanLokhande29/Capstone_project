import { NavLink } from "react-router-dom";
import { cn } from "@/lib/utils";

export const CASES_TABS = [
  { to: "/cases", label: "Explore", end: true },
  { to: "/cases/failures", label: "Failure Map" },
  { to: "/cases/play", label: "Play" },
  { to: "/cases/atlas", label: "Atlas" },
];

export function CasesNav() {
  return (
    <nav aria-label="Cases" className="mt-4 flex flex-wrap gap-1 border-b border-line">
      {CASES_TABS.map((t) => (
        <NavLink key={t.to} to={t.to} end={t.end}
          className={({ isActive }) => cn("-mb-px border-b-2 px-3 py-2 text-[14px]", isActive ? "border-accent font-medium text-ink" : "border-transparent text-ink-3 hover:text-ink")}>{t.label}</NavLink>
      ))}
    </nav>
  );
}
