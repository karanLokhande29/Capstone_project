import { useEffect, useState } from "react";
import { Badge, Button, Card, CardBody } from "@/components/ui/primitives";
import { PageHeader } from "@/components/Page";
import { live } from "./api";
import { useAudit } from "./state";

type Fresh = Awaited<ReturnType<typeof live.freshness>>;

export default function CorpusStatus() {
  const { mode, pack } = useAudit();
  const [fresh, setFresh] = useState<Fresh | null>(null);
  const [dry, setDry] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (mode === "live") void live.freshness().then(setFresh).catch((e) => setErr((e as Error).message)); }, [mode]);
  const c = pack?.about.corpus;
  const age = fresh?.age_days ?? pack?.about.freshness.age_days ?? null;
  const warn = fresh?.warn ?? pack?.about.freshness.warn ?? false;
  const list = (k: string) => (Array.isArray(dry?.[k]) ? (dry![k] as { document_id: string; title: string; update_date?: string }[]) : []);
  return (
    <div>
      <PageHeader title="Corpus status" subtitle="Snapshot age and a safe refresh. A refresh writes only to data/auditgen_corpus/; the research corpus and every research result stay tied to the original snapshot." />
      <Card><CardBody className="space-y-1.5 text-[13px]">
        <p>Snapshot: <b>{fresh?.snapshot_date ?? c?.snapshot_date ?? "?"}</b> ({fresh?.kind ?? c?.kind ?? "?"}) · age <span className="num">{age ?? "?"}</span> days{" "}
          {warn ? <Badge tone="warn">older than 30 days: run a refresh dry run</Badge> : <Badge tone="pos">fresh</Badge>}</p>
        <p className="break-all text-[12px] text-ink-3">sha256 {fresh?.sha256 ?? c?.sha256}</p>
        {fresh && <p className="text-[12px] text-ink-3">{fresh.directions} Directions · {fresh.paragraphs.toLocaleString()} paragraphs</p>}
        {mode === "live" ? (
          <div className="pt-1">
            <Button disabled={busy} onClick={async () => { setBusy(true); setErr(null); try { setDry(await live.dryRun()); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); } }}>
              {busy ? "Checking rbi.org.in (≤ 4 requests, 1.5 s apart)…" : "Refresh dry run"}</Button>
            <p className="mt-1 text-[12px] text-ink-3">The dry run reads the RBI listings only and writes nothing. To apply: <code>python3 scripts/auditgen.py refresh --apply</code>.</p>
          </div>
        ) : <p className="text-[12px] text-ink-3">The dry run needs the local backend: <code>python3 scripts/auditgen.py serve</code>, or run <code>python3 scripts/auditgen.py refresh --dry-run</code>.</p>}
        {err && <p className="text-neg">{err}</p>}
      </CardBody></Card>
      {dry && (
        <Card className="mt-3"><CardBody className="space-y-2 text-[12.5px]" aria-label="Dry run result">
          <p>{String(dry.requests)} requests · listing {String(dry.listing_count)} · unchanged {String(dry.unchanged)} · would fetch <b>{String(dry.would_fetch)}</b> · writes: {String(dry.writes)}</p>
          {(["new_directions", "updated_directions"] as const).map((k) => (
            <div key={k}><p className="font-medium">{k.replace("_", " ")} ({list(k).length})</p>
              <ul className="list-disc pl-5">{list(k).slice(0, 30).map((d) => <li key={d.document_id}>{d.document_id} · {d.title} {d.update_date ? `(${d.update_date})` : ""}</li>)}</ul></div>
          ))}
          <p>No longer listed: {(dry.removed_from_listing as string[] | undefined)?.join(", ") || "none"}</p>
          <p>New Amendment Directions: {String(((dry.amendment_directions as { new?: unknown[] }) ?? {}).new?.length ?? "not checked")} · new withdrawn circulars: {String(((dry.withdrawn_circulars as { new?: unknown[] }) ?? {}).new?.length ?? "not checked")}</p>
        </CardBody></Card>
      )}
    </div>
  );
}
