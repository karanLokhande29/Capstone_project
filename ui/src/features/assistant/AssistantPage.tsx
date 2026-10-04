import { useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/Page";
import { Card, CardBody } from "@/components/ui/primitives";
import { AssistantChat } from "./Assistant";

export default function AssistantPage() {
  const [sp] = useSearchParams();
  const q = sp.get("q");
  return (
    <div>
      <PageHeader title="Ask RBI-ObliBench" tier="COULD" product
        subtitle="Palette route (default, free): deterministic queries answered from the snapshot with exact citations. Grounded-LLM route (opt-in): answers only from retrieved project chunks, every number post-checked; otherwise it says “Not in the project record”." />
      <Card className="h-[70vh]" key={q ?? "none"}><CardBody className="h-full"><AssistantChat initial={q} /></CardBody></Card>
    </div>
  );
}
