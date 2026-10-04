import { lazy, Suspense } from "react";
import { createBrowserRouter, createHashRouter, Navigate, RouterProvider, useRouteError } from "react-router-dom";
import { ARTIFACT, NO_PROXY } from "./lib/env";
import { DemoLayout, Loading } from "./features/demo/DemoLayout";
import { EmptyState, LoadingPage } from "./components/Page";

// Public demo (Demo Build Spec §13): reads small per-route JSON shards from public/data, never the research snapshot.
const Home = lazy(() => import("./features/demo/Home"));
const Cases = lazy(() => import("./features/demo/cases/Cases"));
const FailureMap = lazy(() => import("./features/demo/cases/FailureMap"));
const Play = lazy(() => import("./features/demo/play/Play"));
const Atlas = lazy(() => import("./features/demo/cases/Atlas"));
const CaseView = lazy(() => import("./features/demo/case/CaseView"));
const Lab = lazy(() => import("./features/demo/lab/Lab"));
const Triage = lazy(() => import("./features/demo/Triage"));
const Results = lazy(() => import("./features/demo/Results"));
const Method = lazy(() => import("./features/demo/Method"));
const Present = lazy(() => import("./features/demo/present/Present"));

function RouteError() {
  const e = useRouteError() as Error;
  return <EmptyState title="This screen failed to render."><p className="mt-2 text-ink-3">{e?.message ?? String(e)}</p></EmptyState>;
}

const s = (el: React.ReactNode) => <Suspense fallback={<Loading />}>{el}</Suspense>;

const demoRoutes = {
  element: <DemoLayout />, errorElement: <RouteError />,
  children: [
    { index: true, element: s(<Home />) },
    { path: "cases", element: s(<Cases />) },
    { path: "cases/failures", element: s(<FailureMap />) },
    { path: "cases/play", element: s(<Play />) },
    { path: "cases/atlas", element: s(<Atlas />) },
    { path: "case/:unitId", element: s(<CaseView />) },
    { path: "lab", element: s(<Lab />) },
    { path: "lab/paste", element: s(<Lab />) },
    { path: "lab/edit", element: s(<Lab />) },
    { path: "triage", element: s(<Triage />) },
    { path: "results", element: s(<Results />) },
    { path: "method", element: s(<Method />) },
    // Old pitch-site URLs keep working.
    { path: "findings", element: <Navigate to="/results" replace /> },
    { path: "how-it-works", element: <Navigate to="/method" replace /> },
    { path: "trust", element: <Navigate to="/method#limits" replace /> },
    { path: "demo", element: <Navigate to="/cases" replace /> },
  ],
};

/** The research workspace for the authors (local builds only). Defined inside a function so the public build drops it entirely. */
function workspaceRoutes() {
  const Layout = lazy(() => import("./app/Layout").then((m) => ({ default: m.Layout })));
  const Gate = lazy(() => import("./app/Gate"));
  const g = (el: React.ReactNode) => <Suspense fallback={<LoadingPage />}><Gate>{el}</Gate></Suspense>;
  const CommandCenter = lazy(() => import("./features/home/CommandCenter").then((m) => ({ default: m.CommandCenter })));
  const RQExplorer = lazy(() => import("./features/rq/RQExplorer"));
  const ResultsLab = lazy(() => import("./features/results/ResultsLab"));
  const DifferentExplorer = lazy(() => import("./features/different/DifferentExplorer"));
  const Construction = lazy(() => import("./features/construction/Construction"));
  const Reliability = lazy(() => import("./features/reliability/Reliability"));
  const WsAtlas = lazy(() => import("./features/atlas/Atlas"));
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
    element: <Suspense fallback={<LoadingPage />}><Layout /></Suspense>, errorElement: <RouteError />,
    children: [
      { path: "workspace", element: g(<CommandCenter />) },
      { path: "rq/:id?", element: g(<RQExplorer />) },
      { path: "workspace/results/:tab?", element: g(<ResultsLab />) },
      { path: "different", element: g(<DifferentExplorer />) },
      { path: "construction", element: g(<Construction />) },
      { path: "reliability", element: g(<Reliability />) },
      { path: "atlas", element: g(<WsAtlas />) },
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
  demoRoutes,
  { path: "present", element: s(<Present />), errorElement: <RouteError /> },
  ...(PUBLIC_SITE ? [] : [workspaceRoutes()]),
  { element: <DemoLayout />, children: [{ path: "*", element: <EmptyState title="Page not found."><p className="mt-2"><a className="text-accent" href={ARTIFACT ? "#/" : "/"}>Go to the home page</a></p></EmptyState> }] },
];

const router = ARTIFACT ? createHashRouter(routes) : createBrowserRouter(routes);

export default function App() {
  return <RouterProvider router={router} />;
}
