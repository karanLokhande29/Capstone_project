import {
  Activity, AlertTriangle, BookOpenCheck, Boxes, Building2, ClipboardCheck, Compass, FlaskConical, GitCompare, GitFork, Grid3x3, Home,
  Inbox, Lightbulb, ListChecks, MessageSquare, Network, PenTool, Rocket, Search, ShieldCheck, Sparkles, Users,
} from "lucide-react";

export interface NavItem { to: string; label: string; icon: typeof Home; tier: "MUST" | "SHOULD" | "COULD"; product?: boolean }
export interface NavGroup { label: string; items: NavItem[] }

export const NAV: NavGroup[] = [
  { label: "Home", items: [{ to: "/workspace", label: "Command Center", icon: Home, tier: "MUST" }, { to: "/", label: "Public site (pitch)", icon: Rocket, tier: "COULD", product: true }] },
  { label: "Research", items: [
    { to: "/rq", label: "Research questions", icon: Compass, tier: "MUST" },
    { to: "/results", label: "Results Lab", icon: FlaskConical, tier: "MUST" },
    { to: "/different", label: "`different` Explorer", icon: GitCompare, tier: "MUST" },
    { to: "/construction", label: "Construction", icon: Boxes, tier: "SHOULD" },
    { to: "/reliability", label: "Reliability", icon: Users, tier: "MUST" },
    { to: "/atlas", label: "Corpus Atlas", icon: Grid3x3, tier: "SHOULD" },
    { to: "/architecture", label: "Architecture", icon: Network, tier: "SHOULD" },
  ] },
  { label: "Audit", items: [
    { to: "/claims", label: "Claims ↔ Evidence", icon: BookOpenCheck, tier: "SHOULD" },
    { to: "/gaps", label: "Gap Analysis", icon: AlertTriangle, tier: "MUST" },
    { to: "/provenance", label: "Provenance & Freeze", icon: ShieldCheck, tier: "SHOULD" },
    { to: "/diff", label: "Snapshot diff", icon: GitFork, tier: "COULD" },
  ] },
  { label: "Plan", items: [
    { to: "/readiness", label: "Submission Readiness", icon: ClipboardCheck, tier: "MUST" },
    { to: "/next", label: "Build next", icon: Lightbulb, tier: "MUST" },
    { to: "/review-queue", label: "Review queue", icon: Inbox, tier: "COULD" },
    { to: "/workbench", label: "Annotation workbench", icon: PenTool, tier: "COULD" },
    { to: "/tour", label: "Reviewer tour", icon: ListChecks, tier: "COULD" },
  ] },
  { label: "Product", items: [
    { to: "/product", label: "Showcase", icon: Rocket, tier: "COULD", product: true },
    { to: "/explorer", label: "Obligation Explorer", icon: Search, tier: "COULD", product: true },
    { to: "/assistant", label: "Ask RBI-ObliBench", icon: MessageSquare, tier: "COULD", product: true },
  ] },
];

export const ALL_ROUTES = NAV.flatMap((g) => g.items);
export { Activity, Building2, Sparkles };
