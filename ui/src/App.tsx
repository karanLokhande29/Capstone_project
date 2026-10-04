import { lazy, Suspense, useEffect } from "react";
import { createBrowserRouter, createHashRouter, RouterProvider, useLocation, useRouteError } from "react-router-dom";
import { ARTIFACT, NO_PROXY } from "./lib/env";
import { PitchLayout } from "./features/pitch/PitchLayout";
import { useData } from "@/data/store";
import { Layout } from "./app/Layout";
import { EmptyState, LoadingPage } from "./components/Page";
import { CommandCenter } from "./features/home/CommandCenter";

const PitchHome = lazy(() => import("./features/pitch/Home"));
const Findings = lazy(() => import("./features/pitch/Findings"));
const Demo = lazy(() => import("./features/pitch/Demo"));
const HowItWorks = lazy(() => import("./features/pitch/HowItWorks"));
const Trust = lazy(() => import("./features/pitch/Trust"));

function Gate({ children }: { children: React.ReactNode }) {
  const { status, error, snapshot } = useData();
  const loc = useLocation();
  if (status === "error") return <EmptyState title="The project snapshot could not be loaded." file={error?.file} command={error?.command}><p className="mt-2 text-ink-3">{error?.message}</p></EmptyState>;
  if (status !== "ready") return <LoadingPage />;
  if (snapshot?.meta.fixture && loc.pathname !== "/workspace") {
    return <EmptyState title="Synthetic fixture mode: this screen needs the real snapshot." file="ui/src/data/snapshot.json" command="cd ui && npm run ingest" />;
  }
  return <Suspense fallback={<LoadingPage />}>{children}</Suspense>;
}

function RouteError() {
  const e = useRouteError() as Error;
  return <EmptyState title="This screen failed to render."><p className="mt-2 text-ink-3">{e?.message ?? String(e)}</p></EmptyState>;
}

const g = (el: React.ReactNode) => <Gate>{el}</Gate>;

/** The public pitch site (what new visitors see). */
const pitchRoutes = {
  element: <PitchLayout />, errorElement: <RouteError />,
  children: [
    { index: true, element: g(<PitchHome />) },
    { path: "findings", element: g(<Findings />) },
    { path: "demo", element: g(<Demo />) },
    { path: "how-it-works", element: g(<HowItWorks />) },
    { path: "trust", element: g(<Trust />) },
  ],
};

/** The research workspace for the authors (local builds only). Defined inside a function so the public build drops it entirely. */
function workspaceRoutes() {
  const RQExplorer = lazy(() => import("./features/rq/RQExplorer"));
  const ResultsLab = lazy(() => import("./features/results/ResultsLab"));
  const DifferentExplorer = lazy(() => import("./features/different/DifferentExplorer"));
  const Construction = lazy(() => import("./features/construction/Construction"));
  const Reliability = lazy(() => import("./features/reliability/Reliability"));
  const Atlas = lazy(() => import("./features/atlas/Atlas"));
  const Architecture = lazy(() => import("./features/architecture/Architecture"));
  const ClaimsAuditor = lazy(() => import("./features/claims/ClaimsAuditor"));
  const Gaps = lazy(() => import("./features/gaps/Gaps"));
  const Provenance = lazy(() => import("./features/provenance/Provenance"));
  const SnapshotDiff = lazy(() => import("./features/diff/SnapshotDiff"));
  const Readiness = lazy(() => import("./features/readiness/Readiness"));
  const BuildNext = lazy(() => import("./features/next/BuildNext"));
  const ReviewQueue = lazy(() => import("./features/review/ReviewQueue"));
  const Workbench = lazy(() => import("./features/workbench/Workbench"));
  const Tour = lazy(() => import("./features/tour/Tour"));
  const Showcase = lazy(() => import("./features/product/Showcase"));
  const ObligationExplorer = lazy(() => import("./features/explorer/ObligationExplorer"));
  const AssistantPage = lazy(() => import("./features/assistant/AssistantPage"));
  return {
    element: <Layout />, errorElement: <RouteError />,
    children: [
      { path: "workspace", element: g(<CommandCenter />) },
      { path: "rq/:id?", element: g(<RQExplorer />) },
      { path: "results/:tab?", element: g(<ResultsLab />) },
      { path: "different", element: g(<DifferentExplorer />) },
      { path: "construction", element: g(<Construction />) },
      { path: "reliability", element: g(<Reliability />) },
      { path: "atlas", element: g(<Atlas />) },
      { path: "architecture", element: g(<Architecture />) },
      { path: "claims", element: g(<ClaimsAuditor />) },
      { path: "gaps", element: g(<Gaps />) },
      { path: "provenance", element: g(<Provenance />) },
      { path: "diff", element: g(<SnapshotDiff />) },
      { path: "readiness", element: g(<Readiness />) },
      { path: "next", element: g(<BuildNext />) },
      { path: "review-queue", element: g(<ReviewQueue />) },
      { path: "workbench", element: g(<Workbench />) },
      { path: "tour/:step?", element: g(<Tour />) },
      { path: "product", element: g(<Showcase />) },
      { path: "explorer", element: g(<ObligationExplorer />) },
      { path: "assistant", element: g(<AssistantPage />) },
    ],
  };
}

export const PUBLIC_SITE = NO_PROXY;

export const routes = [
  pitchRoutes,
  ...(PUBLIC_SITE ? [] : [workspaceRoutes()]),
  { element: <PitchLayout />, children: [{ path: "*", element: <EmptyState title="Page not found."><p className="mt-2"><a className="text-accent" href={ARTIFACT ? "#/" : "/"}>Go to the overview</a></p></EmptyState> }] },
];

const router = ARTIFACT ? createHashRouter(routes) : createBrowserRouter(routes);

export default function App() {
  const load = useData((s) => s.load);
  useEffect(() => { void load(); }, [load]);
  return <RouterProvider router={router} />;
}
