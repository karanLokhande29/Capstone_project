import { Suspense, useEffect } from "react";
import { useLocation } from "react-router-dom";
import { useData } from "@/data/store";
import { EmptyState, LoadingPage } from "@/components/Page";

/** Workspace screens need the full research snapshot; it is loaded only when one of them is opened. */
export default function Gate({ children }: { children: React.ReactNode }) {
  const { status, error, snapshot, load } = useData();
  const loc = useLocation();
  useEffect(() => { if (status === "idle") void load(); }, [status, load]);
  if (status === "error") return <EmptyState title="The project snapshot could not be loaded." file={error?.file} command={error?.command}><p className="mt-2 text-ink-3">{error?.message}</p></EmptyState>;
  if (status !== "ready") return <LoadingPage />;
  if (snapshot?.meta.fixture && loc.pathname !== "/workspace") {
    return <EmptyState title="Synthetic fixture mode: this screen needs the real snapshot." file="ui/src/data/snapshot.json" command="cd ui && npm run ingest" />;
  }
  return <Suspense fallback={<LoadingPage />}>{children}</Suspense>;
}
