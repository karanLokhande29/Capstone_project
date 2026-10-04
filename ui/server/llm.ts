// LLM clients for the opt-in routes. The real client reads ASSISTANT_GEMINI_API_KEY server-side only; it is never logged,
// never sent to the browser, and is distinct from the experiments' GEMINI_API_KEY (separate Google Cloud project).
export interface ChatMessage { role: "system" | "user"; content: string }
export interface LlmClient { readonly name: string; generate(messages: ChatMessage[], opts?: { json?: boolean; maxOutputTokens?: number }): Promise<string> }

export class GeminiClient implements LlmClient {
  readonly name: string;
  constructor(private readonly apiKey: string, private readonly model = "gemini-3.5-flash-lite", private readonly fetchImpl: typeof fetch = fetch) {
    this.name = `gemini:${model}`;
  }
  async generate(messages: ChatMessage[], opts: { json?: boolean; maxOutputTokens?: number } = {}): Promise<string> {
    const system = messages.filter((m) => m.role === "system").map((m) => m.content).join("\n\n");
    const user = messages.filter((m) => m.role === "user").map((m) => m.content).join("\n\n");
    const body = {
      systemInstruction: system ? { parts: [{ text: system }] } : undefined,
      contents: [{ role: "user", parts: [{ text: user }] }],
      generationConfig: { temperature: 0, maxOutputTokens: opts.maxOutputTokens ?? 2048, ...(opts.json ? { responseMimeType: "application/json" } : {}),
        thinkingConfig: { thinkingLevel: "minimal" } },
    };
    const r = await this.fetchImpl(`https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(this.model)}:generateContent`, {
      method: "POST", headers: { "content-type": "application/json", "x-goog-api-key": this.apiKey }, body: JSON.stringify(body),
    });
    if (r.status === 429) throw new LlmError("quota", "provider quota reached");
    if (!r.ok) throw new LlmError("upstream", `provider error ${r.status}`);
    const j = (await r.json()) as { candidates?: { content?: { parts?: { text?: string }[] } }[] };
    return j.candidates?.[0]?.content?.parts?.map((p) => p.text ?? "").join("") ?? "";
  }
}

export class LlmError extends Error {
  constructor(readonly kind: "quota" | "upstream" | "offline", message: string) { super(message); }
}

/** Test double: returns scripted replies and records the prompts it saw. */
export class MockLlm implements LlmClient {
  readonly name = "mock";
  calls: ChatMessage[][] = [];
  constructor(private readonly reply: (messages: ChatMessage[]) => string) {}
  async generate(messages: ChatMessage[]): Promise<string> {
    this.calls.push(messages);
    return this.reply(messages);
  }
}
