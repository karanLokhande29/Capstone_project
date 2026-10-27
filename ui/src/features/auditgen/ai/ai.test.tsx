import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { readJson } from "@/test/files";
import type { ConfidenceModel, Snapshot } from "@/domain/types";
import { useData } from "@/data/store";
import { routes } from "@/App";
import { DISC, FIXTURE } from "../testFixture";
import type { AiStore, AskResult } from "./aiTypes";

const base = { created_utc: "2026-10-22T05:00:00+00:00", model: "qwen2.5:7b-instruct", seconds: 4.2, genai_version: "auditgen-genai-v1",
  verifier: "cross-encoder/nli-deberta-v3-xsmall@a15087641532", label: "AI draft", disclaimer: DISC };
const src = { label: "E1", row_id: "APP-1", paragraph_id: "md_00001::p00001", direction_title: "Fixture Direction", source_url: "https://rbidocs.rbi.org.in/fixture.pdf" };

const ASK: AskResult = {
  ...base, question: "When must fraud be reported?", answer: "The bank shall report fraud within seven days.", attempts: 1, abstained: false,
  sentences: [{ text: "The bank shall report fraud within seven days.", verified: true, citations: ["E1"], sources: [src] },
    { text: "Fraud must also be posted on social media.", verified: false, reason: "not entailed by the cited text", citations: ["E1"], sources: [src] }],
  evidence: [{ ...src, status: "in force", deadline: "", excerpt: "The bank shall report fraud within seven days.", score: 0.03 }],
};

const RECORDED: AiStore = { pack_id: "fixture_pack", ask: [ASK] };

function serve(live: boolean) {
  const calls: string[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const path = url.replace(/^https?:\/\/[^/]+/, "");
    calls.push(`${init?.method ?? "GET"} ${path}`);
    const j = (x: unknown) => new Response(JSON.stringify(x), { headers: { "content-type": "application/json" } });
    if (!live) {
      if (path.startsWith("/api/auditgen")) return new Response("backend not running", { status: 503 });
      if (path === "/auditgen/index.json") return j({ packs: [{ pack_id: "fixture_pack", profile: FIXTURE.profile, created_utc: FIXTURE.created_utc, summary: {}, file: "fixture_pack.json", kind: "sample" }] });
      if (path === "/auditgen/fixture_pack.json") return j(FIXTURE);
      if (path === "/auditgen/ai_fixture_pack.json") return j(RECORDED);
      return new Response("", { status: 404 });
    }
    if (path === "/api/auditgen/health") return j({ ok: true, remote_api_calls: false });
    if (path === "/api/auditgen/packs") return j([{ pack_id: "fixture_pack", profile: FIXTURE.profile, created_utc: FIXTURE.created_utc, summary: {}, kind: "sample" }]);
    if (path === "/api/auditgen/packs/fixture_pack") return j(FIXTURE);
    if (path === "/api/auditgen/ai/status") return j({ available: true, model: "qwen2.5:7b-instruct", pulled: ["qwen2.5:7b-instruct"], host: "http://127.0.0.1:11434", remote_api_calls: false });
    if (path === "/api/auditgen/ai/packs/fixture_pack") return j({ pack_id: "fixture_pack" });
    if (path === "/api/auditgen/ai/packs/fixture_pack/ask") return j(ASK);
    if (path === "/api/auditgen/ai/activity") return j([]);
    return new Response("", { status: 404 });
  }) as typeof fetch;
  return calls;
}

const realFetch = globalThis.fetch;
beforeAll(() => {
  useData.getState().setLoaded(readJson<Snapshot>("src/data/snapshot.json"), readJson<ConfidenceModel>("src/data/confidence_model_v1.json"), "repo");
});
afterEach(() => { globalThis.fetch = realFetch; });

const go = (path: string) => render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [path] })} />);

describe("AI assistant tab", () => {
  it("is a separate tab in the audit generator and replays recorded outputs offline", async () => {
    serve(false);
    go("/auditgen/ai");
    expect((await screen.findAllByRole("link", { name: /AI assistant/ }, { timeout: 4000 })).length).toBeGreaterThan(0);
    expect(await screen.findByText(/recorded AI outputs only/, {}, { timeout: 4000 })).toBeInTheDocument();
    expect(await screen.findByText("When must fraud be reported?", {}, { timeout: 4000 })).toBeInTheDocument();
    // The verified sentence is shown with its RBI citation; the unverified one is hidden until asked for.
    expect(screen.getAllByText("The bank shall report fraud within seven days.").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: /RBI source for md_00001::p00001/ })[0]).toHaveAttribute("href", src.source_url);
    expect(screen.queryByText("Fraud must also be posted on social media.")).toBeNull();
    fireEvent.click(screen.getByText(/Show 1 unverified sentence/));
    expect(screen.getByText("Fraud must also be posted on social media.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Ask$/ })).toBeDisabled();
    expect(document.body.textContent).toContain(DISC);
  });

  it.each([["obligations", /Pick an obligation/], ["changes", /Pick a change/], ["briefing", /Executive memo/], ["calendar", /AI check of the compliance calendar/],
    ["differential", /no cross-class differential/], ["activity", /How the AI features work/]])("/auditgen/ai/%s renders", async (tab, text) => {
    serve(false);
    go(`/auditgen/ai/${tab}`);
    expect((await screen.findAllByText(text, {}, { timeout: 4000 })).length).toBeGreaterThan(0);
  });

  it("asks the local backend in live mode and shows the cited answer", async () => {
    const calls = serve(true);
    go("/auditgen/ai");
    expect(await screen.findByText(/local model ready/, {}, { timeout: 4000 })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "When must fraud be reported?" } });
    await waitFor(() => expect(screen.getByRole("button", { name: /^Ask$/ })).not.toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: /^Ask$/ }));
    expect(await screen.findByText("When must fraud be reported?", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(calls).toContain("POST /api/auditgen/ai/packs/fixture_pack/ask");
    expect(calls.every((c) => !/https?:\/\/(?!127\.0\.0\.1|localhost)/.test(c))).toBe(true);
  });
});
