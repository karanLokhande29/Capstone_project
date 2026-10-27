import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { readJson } from "@/test/files";
import type { ConfidenceModel, Snapshot } from "@/domain/types";
import { useData } from "@/data/store";
import { routes } from "@/App";
import { DISC, FIXTURE } from "./testFixture";

const realFetch = globalThis.fetch;
beforeAll(() => {
  useData.getState().setLoaded(readJson<Snapshot>("src/data/snapshot.json"), readJson<ConfidenceModel>("src/data/confidence_model_v1.json"), "repo");
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const path = url.replace(/^https?:\/\/[^/]+/, "");
    if (path.startsWith("/api/auditgen")) return new Response("backend not running", { status: 503 });
    if (path === "/auditgen/index.json") {
      return new Response(JSON.stringify({ packs: [{ pack_id: "fixture_pack", profile: FIXTURE.profile, created_utc: FIXTURE.created_utc, summary: {}, file: "fixture_pack.json", kind: "sample" }] }));
    }
    if (path === "/auditgen/fixture_pack.json") return new Response(JSON.stringify(FIXTURE));
    return realFetch(input);
  }) as typeof fetch;
});
afterAll(() => { globalThis.fetch = realFetch; });

const PAGES: [string, RegExp][] = [
  ["/auditgen", /Audit pack/], ["/auditgen/gaps", /Policy gaps/], ["/auditgen/review", /Confirm or dispute rows/],
  ["/auditgen/downloads", /JSON audit trail/], ["/auditgen/corpus", /Snapshot age and a safe refresh/],
];

describe("audit generator pages (offline replay)", () => {
  it.each(PAGES)("%s renders with the disclaimer", async (path, text) => {
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [path] })} />);
    expect((await screen.findAllByText(text, {}, { timeout: 4000 })).length).toBeGreaterThan(0);
    expect((await screen.findAllByText(/offline replay/, {}, { timeout: 4000 })).length).toBeGreaterThan(0);
    expect(document.body.textContent).toContain(DISC);
  });

  it("the register shows the RBI source link and a needs-human-review badge", async () => {
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ["/auditgen"] })} />);
    const link = await screen.findByRole("link", { name: /RBI source for md_00001::p00001/ }, { timeout: 4000 });
    expect(link).toHaveAttribute("href", "https://rbidocs.rbi.org.in/fixture.pdf");
    expect(screen.getAllByText("needs human review").length).toBeGreaterThan(0);
    expect(screen.getByText(/Generating needs the local backend/)).toBeInTheDocument();
  });
});
