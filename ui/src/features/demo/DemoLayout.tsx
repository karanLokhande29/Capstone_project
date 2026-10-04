import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { Menu, Moon, Sun, X } from "lucide-react";
import { useSettings } from "@/data/settings";
import { Button, TooltipProvider } from "@/components/ui/primitives";
import { NO_PROXY } from "@/lib/env";
import { cn } from "@/lib/utils";

export const DEMO_NAV = [
  { to: "/", label: "Home" },
  { to: "/cases", label: "Cases" },
  { to: "/lab", label: "Lab" },
  { to: "/triage", label: "Triage" },
  { to: "/results", label: "Results" },
  { to: "/method", label: "Method & Trust" },
];

/** The one sentence every page reinforces (Demo Build Spec). */
export const POSITIONING = "This is not a chatbot over RBI documents. It is a benchmark and inspection environment for finding, explaining and stress-testing differences between regulatory obligations.";

export function DemoLayout() {
  const loc = useLocation();
  const st = useSettings();
  const [open, setOpen] = useState(false);
  useEffect(() => { if (!loc.hash) window.scrollTo?.(0, 0); setOpen(false); }, [loc.pathname, loc.hash]);
  const dark = typeof document !== "undefined" && document.documentElement.classList.contains("dark");
  return (
    <TooltipProvider>
      <div className="min-h-full bg-bg">
        <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-[90] focus:rounded focus:bg-panel focus:px-2 focus:py-1">Skip to content</a>
        <header className="sticky top-0 z-30 border-b border-line bg-bg/90 backdrop-blur" style={{ top: "env(safe-area-inset-top, 0px)" }}>
          <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3 sm:px-6">
            <Link to="/" className="flex items-center gap-2">
              <span className="grid h-7 w-7 place-items-center rounded-md bg-accent text-[12px] font-bold text-white dark:text-black" aria-hidden>RO</span>
              <span className="text-[15px] font-semibold tracking-tight">RBI-ObliBench</span>
            </Link>
            <nav aria-label="Main" className="ml-4 hidden items-center gap-0.5 lg:flex">
              {DEMO_NAV.map((n) => (
                <NavLink key={n.to} to={n.to} end={n.to === "/"}
                  className={({ isActive }) => cn("rounded-md px-2.5 py-1.5 text-[14px] text-ink-2 hover:text-ink", isActive && "bg-panel-2 font-medium text-ink")}>{n.label}</NavLink>
              ))}
            </nav>
            <div className="ml-auto flex items-center gap-1">
              {!NO_PROXY && <Link to="/workspace" className="hidden rounded-md px-2 py-1 text-[12px] text-ink-3 hover:text-ink xl:inline">Research workspace →</Link>}
              <Button variant="ghost" size="icon" aria-label="Toggle theme" onClick={() => st.setTheme(dark ? "light" : "dark")}>{dark ? <Sun size={16} /> : <Moon size={16} />}</Button>
              <Button variant="ghost" size="icon" className="lg:hidden" aria-label={open ? "Close menu" : "Open menu"} aria-expanded={open} onClick={() => setOpen(!open)}>{open ? <X size={18} /> : <Menu size={18} />}</Button>
            </div>
          </div>
          {open && (
            <nav aria-label="Main" className="border-t border-line px-4 py-2 lg:hidden">
              {DEMO_NAV.map((n) => (
                <NavLink key={n.to} to={n.to} end={n.to === "/"} className={({ isActive }) => cn("block rounded-md px-2 py-2 text-[15px]", isActive ? "bg-panel-2 font-medium" : "text-ink-2")}>{n.label}</NavLink>
              ))}
            </nav>
          )}
        </header>
        <main id="main" className="mx-auto max-w-6xl px-4 pb-20 sm:px-6"><Outlet /></main>
        <footer className="border-t border-line">
          <div className="mx-auto max-w-6xl space-y-2 px-4 py-6 text-[12.5px] text-ink-3 sm:px-6">
            <p className="text-ink-2">{POSITIONING}</p>
            <div className="flex flex-col gap-2 sm:flex-row sm:justify-between">
              <p>RBI-ObliBench · research project, NMIMS MPSTME, Mumbai · Not legal or compliance advice.</p>
              <p>Source documents: Reserve Bank of India Master Directions (rbi.org.in). Quotes are at most 12 words and link to the official PDF.</p>
            </div>
          </div>
        </footer>
      </div>
    </TooltipProvider>
  );
}

/** Shared page header. */
export function PageHead({ eyebrow, title, children }: { eyebrow: string; title: React.ReactNode; children?: React.ReactNode }) {
  return (
    <header className="pb-2 pt-8 sm:pt-12">
      <p className="mb-2 text-[12px] font-semibold uppercase tracking-[0.12em] text-accent">{eyebrow}</p>
      <h1 className="max-w-3xl text-[28px] font-semibold leading-tight tracking-tight [text-wrap:balance] sm:text-[36px]">{title}</h1>
      {children && <div className="mt-3 max-w-3xl text-[15px] leading-relaxed text-ink-2">{children}</div>}
    </header>
  );
}

export function Loading({ what }: { what?: string }) {
  return <p className="py-16 text-center text-[14px] text-ink-3" role="status">Loading{what ? ` ${what}` : ""}…</p>;
}

export function LoadError({ error }: { error: string }) {
  return <p className="py-10 text-[14px] text-neg" role="alert">Could not load the data for this page ({error}).</p>;
}
