import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { ExternalLink } from "lucide-react";
import { useData } from "@/data/store";
import { PageHeader, Section } from "@/components/Page";
import { Badge, Card, CardBody, Tip } from "@/components/ui/primitives";
import { Num } from "@/components/Provenance";
import { resolveKey } from "@/lib/keys";
import { cn } from "@/lib/utils";

export default function Atlas() {
  const s = useData((st) => st.snapshot)!;
  const [sp, setSp] = useSearchParams();
  const sel = sp.get("cell");
  const cls = sp.get("class");
  const md = sp.get("md");
  const classes = s.entityClasses;
  const fams = s.subjectFamilies;
  const cell = useMemo(() => new Map(s.matrix.map((c) => [`${c.classId}||${c.familyId}`, c])), [s.matrix]);
  const selected = sel ? cell.get(sel) : null;
  const dirById = new Map(s.directions.map((d) => [d.id, d]));
  const list = selected ? selected.directionIds.map((i) => dirById.get(i)).filter(Boolean)
    : cls ? s.directions.filter((d) => d.classIds.includes(cls)) : md ? [dirById.get(md)].filter(Boolean) : [];
  const R = s.results;
  const pick = (v: string) => { const n = new URLSearchParams(sp); n.set("cell", v); n.delete("class"); n.delete("md"); setSp(n, { replace: true }); };
  return (
    <div>
      <PageHeader title="Corpus Atlas" tier="SHOULD" subtitle={<>{classes.length} entity-class headings × {fams.length} subject families. Matrix:{" "}
        <Num value={resolveKey(R, "tables.01_corpus.matrix.total_cells") as number} sourceKey="tables.01_corpus.matrix.total_cells" /> cells,{" "}
        <Num value={resolveKey(R, "tables.01_corpus.matrix.populated_cells") as number} sourceKey="tables.01_corpus.matrix.populated_cells" /> populated,{" "}
        <Num value={resolveKey(R, "tables.01_corpus.matrix.ambiguous_cells") as number} sourceKey="tables.01_corpus.matrix.ambiguous_cells" /> ambiguous. Click a cell to list its Directions.</>} />
      <Card><CardBody className="overflow-x-auto p-2">
        <table className="border-separate border-spacing-[2px] text-[10px]">
          <thead><tr><th />{fams.map((f) => (
            <th key={f.id} className="h-36 w-4 align-bottom font-normal text-ink-3"><div className="w-4 origin-bottom-left translate-x-3 -rotate-60 whitespace-nowrap">{f.label.slice(0, 34)}</div></th>
          ))}</tr></thead>
          <tbody>
            {classes.map((c) => (
              <tr key={c.id}>
                <th className="whitespace-nowrap pr-2 text-right font-normal text-ink-2">{c.label} {c.kind === "rbi_function" && <span className="text-ink-3">(fn)</span>}</th>
                {fams.map((f) => {
                  const k = `${c.id}||${f.id}`;
                  const m = cell.get(k);
                  return (
                    <td key={f.id}>
                      <Tip content={`${c.label} × ${f.label}: ${m?.populated ? `${m.directionIds.length} Direction(s)` : "not populated"}${m?.ambiguous ? " · ambiguous" : ""}`}>
                        <button type="button" aria-label={`${c.label} × ${f.label}`} onClick={() => pick(k)}
                          className={cn("block h-4 w-4 cursor-pointer rounded-[3px]", m?.populated ? "bg-accent" : "bg-panel-2", m?.ambiguous && "ring-2 ring-warn", sel === k && "outline outline-2 outline-ink")}
                          style={m?.populated ? { opacity: 0.35 + Math.min(1, m.directionIds.length / 3) * 0.65 } : undefined} />
                      </Tip>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 px-1 text-[11.5px] text-ink-3">Filled = populated; ring = ambiguous (more than one source Direction); (fn) = RBI function heading.</p>
      </CardBody></Card>
      {list.length > 0 && (
        <Section title={selected ? `${selected.classId} × ${selected.familyId}` : cls ? `Directions of ${cls}` : `Direction ${md}`}>
          <Card><CardBody>
            {selected?.ambiguous && <p className="mb-2 text-[12px] text-warn">Ambiguous cell: {selected.ambiguityReason}</p>}
            <ul className="space-y-1.5 text-[12.5px]">{list.map((d) => d && (
              <li key={d.id}><code>{d.id}</code> {d.title || <i className="text-ink-3">(empty title: defect D2)</i>}
                {d.updatedAsOn && <Badge tone="warn" className="ml-1">updated as on {d.updatedAsOn}</Badge>}
                {d.url && <a href={d.url} target="_blank" rel="noreferrer" className="ml-1 inline-flex text-ink-3 hover:text-accent" aria-label="RBI source"><ExternalLink size={11} /></a>}</li>))}</ul>
          </CardBody></Card>
        </Section>
      )}
      <Section title="Defects and the amended-text-only limitation">
        <Card><CardBody className="space-y-1 text-[12.5px]">
          <p><b>D2:</b> {(resolveKey(R, "tables.01_corpus.empty_title_directions") as string[]).length} Directions have empty titles and no subject family: {(resolveKey(R, "tables.01_corpus.empty_title_directions") as string[]).join(", ")}.</p>
          <p><Num value={resolveKey(R, "tables.01_corpus.updated_as_on_titles") as number} sourceKey="tables.01_corpus.updated_as_on_titles" /> titles carry an "Updated as on" stamp. RBI consolidates amendments in place, so the corpus holds only current text: the system can flag a later amendment but cannot show the pre-amendment wording.</p>
        </CardBody></Card>
      </Section>
    </div>
  );
}
