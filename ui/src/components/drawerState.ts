import { create } from "zustand";

// The drawer is URL-addressable: ?node=<kind>:<id>&tab=<tab>&trail=<a,b,…>. This store mirrors the URL.
export type DrawerTab = "overview" | "evidence" | "upstream" | "downstream" | "caveats" | "source";

interface DrawerState {
  node: string | null;
  tab: DrawerTab;
  trail: string[];
  open: (node: string, tab?: DrawerTab) => void;
  close: () => void;
  setTab: (t: DrawerTab) => void;
  syncFromUrl: (search: string) => void;
}

export const useDrawer = create<DrawerState>((set, get) => ({
  node: null,
  tab: "overview",
  trail: [],
  open(node, tab = "overview") {
    const cur = get().node;
    const trail = cur && cur !== node ? [...get().trail.filter((t) => t !== node), cur].slice(-6) : get().trail;
    set({ node, tab, trail });
    writeUrl(node, tab, trail);
  },
  close() {
    set({ node: null, trail: [] });
    writeUrl(null, "overview", []);
  },
  setTab(tab) {
    set({ tab });
    writeUrl(get().node, tab, get().trail);
  },
  syncFromUrl(search) {
    const p = new URLSearchParams(search);
    const node = p.get("node");
    set({ node, tab: (p.get("tab") as DrawerTab) || "overview", trail: (p.get("trail") || "").split("~").filter(Boolean) });
  },
}));

function setParams(p: URLSearchParams, node: string | null, tab: DrawerTab, trail: string[]) {
  if (node) {
    p.set("node", node);
    p.set("tab", tab);
    if (trail.length) p.set("trail", trail.join("~"));
    else p.delete("trail");
  } else {
    p.delete("node");
    p.delete("tab");
    p.delete("trail");
  }
}

function writeUrl(node: string | null, tab: DrawerTab, trail: string[]) {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  if (url.hash.startsWith("#/")) {
    // Hash routing (hosted build): the drawer state lives in the hash's own query string.
    const [path, query = ""] = url.hash.slice(1).split("?");
    const p = new URLSearchParams(query);
    setParams(p, node, tab, trail);
    const qs = p.toString();
    url.hash = qs ? `${path}?${qs}` : path;
  } else {
    setParams(url.searchParams, node, tab, trail);
  }
  window.history.replaceState(window.history.state, "", url.toString());
}
