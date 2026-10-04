import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Menu, MessageSquare, Moon, Search, Settings, Sun, X } from "lucide-react";
import * as Dialog from "@radix-ui/react-dialog";
import { useData, useSettings } from "@/data/store";
import { NodeDrawer } from "@/components/NodeDrawer";
import { useDrawer } from "@/components/drawerState";
import { Badge, Button, Kbd, Tip, TooltipProvider } from "@/components/ui/primitives";
import { AssistantPanel } from "@/features/assistant/Assistant";
import { CommandPalette, useCommandPalette } from "./CommandPalette";
import { NAV } from "./nav";
import { cn } from "@/lib/utils";
import { NO_PROXY } from "@/lib/env";
import { Countdown } from "./Countdown";

function SideNav({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav aria-label="Main" className="space-y-4 px-2 py-3">
      {NAV.map((g) => (
        <div key={g.label}>
          <p className={cn("px-2 pb-1 text-[10.5px] font-semibold uppercase tracking-wider", g.label === "Product" ? "text-product" : "text-ink-3")}>{g.label}</p>
          <ul className="space-y-px">
            {g.items.map((it) => (
              <li key={it.to}>
                <NavLink to={it.to} end={it.to === "/" || it.to === "/workspace"} onClick={onNavigate}
                  className={({ isActive }) => cn("flex items-center gap-2 rounded-md px-2 py-1.5 text-[13px] text-ink-2 hover:bg-panel-2 hover:text-ink",
                    isActive && "bg-panel-2 font-medium text-ink")}>
                  <it.icon size={15} className={it.product ? "text-product" : "text-ink-3"} />{it.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function SettingsMenu() {
  const st = useSettings();
  return (
    <Dialog.Root>
      <Dialog.Trigger asChild><Button variant="ghost" size="icon" aria-label="Settings"><Settings size={16} /></Button></Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[70] bg-black/30" />
        <Dialog.Content aria-describedby={undefined} className="fixed left-1/2 top-[12vh] z-[71] w-[calc(100%-32px)] max-w-md -translate-x-1/2 rounded-xl border border-line bg-panel p-4 shadow-2xl">
          <Dialog.Title className="text-[15px] font-semibold">Settings</Dialog.Title>
          <div className="mt-3 space-y-3 text-sm">
            <fieldset>
              <legend className="mb-1 text-ink-3">Theme</legend>
              <div className="flex gap-1">{(["light", "dark", "system"] as const).map((t) => (
                <Button key={t} size="sm" variant={st.theme === t ? "default" : "outline"} onClick={() => st.setTheme(t)} className="capitalize">{t}</Button>))}</div>
            </fieldset>
            {NO_PROXY ? <p className="rounded-md bg-panel-2 p-2 text-[12.5px]">This is the hosted, read-only version. The grounded-LLM assistant and the live Obligation Explorer need the local proxy and their own key, so they run only locally (<code>ui/README.md</code>).</p> : <>
            <label className="flex items-start gap-2">
              <input type="checkbox" checked={st.assistantEnabled} onChange={(e) => st.setAssistantEnabled(e.target.checked)} className="mt-1" />
              <span><b>Grounded-LLM assistant route</b> (off by default). Needs the local proxy (<code>npm run server</code>) and its own
                <code> ASSISTANT_GEMINI_API_KEY</code> in a separate Google Cloud project. Daily cap and cache apply. The palette route works without it.</span>
            </label>
            <label className="flex items-start gap-2">
              <input type="checkbox" checked={st.liveEnabled} onChange={(e) => st.setLiveEnabled(e.target.checked)} className="mt-1" />
              <span><b>Live Obligation Explorer</b> (off by default). Runs real class-aware retrieval and the frozen comparator on a new query through the same proxy and key.</span>
            </label></>}
            <p className="text-[12px] text-ink-3">The Research Command Center makes zero LLM calls. Keys are read server-side only and never reach the browser.</p>
          </div>
          <Dialog.Close asChild><Button className="mt-4" variant="outline">Done</Button></Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function Layout() {
  const { open, setOpen } = useCommandPalette();
  const [mobileNav, setMobileNav] = useState(false);
  const loc = useLocation();
  const sync = useDrawer((s) => s.syncFromUrl);
  const st = useSettings();
  const fixture = useData((s) => s.snapshot?.meta.fixture);
  const isProduct = ["/product", "/explorer", "/assistant"].some((p) => loc.pathname.startsWith(p));
  useEffect(() => { sync(loc.search); }, [loc.search, sync]);
  useEffect(() => { window.scrollTo?.(0, 0); }, [loc.pathname]);
  const dark = typeof document !== "undefined" && document.documentElement.classList.contains("dark");
  return (
    <TooltipProvider>
      <div className={cn("min-h-full", fixture && "watermark")}>
        <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-[90] focus:rounded focus:bg-panel focus:px-2 focus:py-1">Skip to content</a>
        <aside className="fixed inset-y-0 left-0 z-30 hidden w-56 overflow-y-auto border-r border-line bg-panel lg:block">
          <div className="flex items-center gap-2 border-b border-line px-4 py-3">
            <span className="grid h-6 w-6 place-items-center rounded-md bg-accent text-[11px] font-bold text-white dark:text-black">RO</span>
            <div className="leading-tight"><p className="text-[13px] font-semibold">RBI-ObliBench</p><p className="text-[11px] text-ink-3">Command Center</p></div>
          </div>
          <SideNav />
        </aside>
        <div className="lg:pl-56">
          <header className="sticky top-0 z-20 flex items-center gap-2 border-b border-line bg-bg/90 px-4 py-2 backdrop-blur">
            <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open navigation" onClick={() => setMobileNav(true)}><Menu size={18} /></Button>
            <button type="button" onClick={() => setOpen(true)}
              className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 rounded-md border border-line bg-panel px-2.5 py-1.5 text-left text-[13px] text-ink-3 hover:border-ink-3 sm:max-w-md">
              <Search size={14} /><span className="truncate">Ask or search…</span><span className="ml-auto hidden sm:inline"><Kbd>⌘K</Kbd></span>
            </button>
            <div className="ml-auto flex items-center gap-1">
              <Countdown />
              {fixture && <Badge tone="neg">synthetic fixture</Badge>}
              <Tip content="Assistant panel"><Button variant="ghost" size="icon" aria-label="Toggle assistant" onClick={() => st.setAssistantOpen(!st.assistantOpen)}><MessageSquare size={16} /></Button></Tip>
              <Tip content="Toggle theme"><Button variant="ghost" size="icon" aria-label="Toggle theme" onClick={() => st.setTheme(dark ? "light" : "dark")}>{dark ? <Sun size={16} /> : <Moon size={16} />}</Button></Tip>
              <SettingsMenu />
            </div>
          </header>
          <main id="main" className={cn("mx-auto max-w-[1400px] px-4 pb-16 pt-4 sm:px-6", st.assistantOpen && "xl:mr-[400px]")}>
            <Outlet />
          </main>
          {isProduct && (
            <footer className="fixed inset-x-0 bottom-0 z-20 border-t border-line bg-panel/95 px-4 py-1.5 text-center text-[12px] text-ink-2 lg:pl-60">
              Research system. Not legal or compliance advice.
            </footer>
          )}
        </div>
        <Dialog.Root open={mobileNav} onOpenChange={setMobileNav}>
          <Dialog.Portal>
            <Dialog.Overlay className="fixed inset-0 z-40 bg-black/30" />
            <Dialog.Content aria-describedby={undefined} className="fixed inset-y-0 left-0 z-50 w-64 overflow-y-auto border-r border-line bg-panel">
              <div className="flex items-center justify-between border-b border-line px-4 py-3">
                <Dialog.Title className="text-[13px] font-semibold">RBI-ObliBench</Dialog.Title>
                <Dialog.Close asChild><Button variant="ghost" size="icon" aria-label="Close navigation"><X size={16} /></Button></Dialog.Close>
              </div>
              <SideNav onNavigate={() => setMobileNav(false)} />
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
        <CommandPalette open={open} setOpen={setOpen} />
        <NodeDrawer />
        {st.assistantOpen && <AssistantPanel onClose={() => st.setAssistantOpen(false)} />}
      </div>
    </TooltipProvider>
  );
}
