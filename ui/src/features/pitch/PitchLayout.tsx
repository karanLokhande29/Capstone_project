import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { Menu, Moon, Sun, X } from "lucide-react";
import { useData, useSettings } from "@/data/store";
import { Button, TooltipProvider } from "@/components/ui/primitives";
import { NO_PROXY } from "@/lib/env";
import { cn } from "@/lib/utils";

export const PITCH_NAV = [
  { to: "/", label: "Overview" },
  { to: "/findings", label: "Results" },
  { to: "/demo", label: "Try it" },
  { to: "/how-it-works", label: "How it works" },
  { to: "/trust", label: "Trust & limits" },
];

export function PitchLayout() {
  const loc = useLocation();
  const st = useSettings();
  const [open, setOpen] = useState(false);
  const fixture = useData((s) => s.snapshot?.meta.fixture);
  useEffect(() => { window.scrollTo?.(0, 0); setOpen(false); }, [loc.pathname]);
  const dark = typeof document !== "undefined" && document.documentElement.classList.contains("dark");
  return (
    <TooltipProvider>
      <div className={cn("min-h-full bg-bg", fixture && "watermark")}>
        <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-[90] focus:rounded focus:bg-panel focus:px-2 focus:py-1">Skip to content</a>
        <header className="sticky top-0 z-30 border-b border-line bg-bg/90 backdrop-blur" style={{ top: "env(safe-area-inset-top, 0px)" }}>
          <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3 sm:px-6">
            <Link to="/" className="flex items-center gap-2">
              <span className="grid h-7 w-7 place-items-center rounded-md bg-accent text-[12px] font-bold text-white dark:text-black">RO</span>
              <span className="text-[15px] font-semibold tracking-tight">RBI-ObliBench</span>
            </Link>
            <nav aria-label="Main" className="ml-6 hidden items-center gap-1 md:flex">
              {PITCH_NAV.map((n) => (
                <NavLink key={n.to} to={n.to} end={n.to === "/"}
                  className={({ isActive }) => cn("rounded-md px-3 py-1.5 text-[14px] text-ink-2 hover:text-ink", isActive && "bg-panel-2 font-medium text-ink")}>{n.label}</NavLink>
              ))}
            </nav>
            <div className="ml-auto flex items-center gap-1">
              {!NO_PROXY && <Link to="/workspace" className="hidden rounded-md px-2 py-1 text-[12px] text-ink-3 hover:text-ink sm:inline">Research workspace →</Link>}
              <Button variant="ghost" size="icon" aria-label="Toggle theme" onClick={() => st.setTheme(dark ? "light" : "dark")}>{dark ? <Sun size={16} /> : <Moon size={16} />}</Button>
              <Button variant="ghost" size="icon" className="md:hidden" aria-label={open ? "Close menu" : "Open menu"} onClick={() => setOpen(!open)}>{open ? <X size={18} /> : <Menu size={18} />}</Button>
            </div>
          </div>
          {open && (
            <nav aria-label="Main" className="border-t border-line px-4 py-2 md:hidden">
              {PITCH_NAV.map((n) => (
                <NavLink key={n.to} to={n.to} end={n.to === "/"} className={({ isActive }) => cn("block rounded-md px-2 py-2 text-[15px]", isActive ? "bg-panel-2 font-medium" : "text-ink-2")}>{n.label}</NavLink>
              ))}
            </nav>
          )}
        </header>
        <main id="main" className="mx-auto max-w-6xl px-4 pb-20 sm:px-6"><Outlet /></main>
        <footer className="border-t border-line">
          <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-6 text-[12.5px] text-ink-3 sm:flex-row sm:justify-between sm:px-6">
            <p>RBI-ObliBench · research project, NMIMS MPSTME, Mumbai · Research system. Not legal or compliance advice.</p>
            <p>Source documents: Reserve Bank of India Master Directions (rbi.org.in). Quotes are short and linked to the official PDF.</p>
          </div>
        </footer>
      </div>
    </TooltipProvider>
  );
}
