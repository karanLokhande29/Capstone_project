# RBI-ObliBench: UI demonstration script

Site: **https://rbioblibench5qbvp2.z29.web.core.windows.net** · ★ = the 4-minute exam path (A1 → A2 → A9 → C1 → C2 → C4 → C6 → D1 → D2). Everything else is the full tour. Inputs were tested on the live site on 30 Oct 2026.

## Before you start

- Open https://rbioblibench5qbvp2.z29.web.core.windows.net/auditgen 10 minutes before you present and wait for the green badge “live · hosted service” (the first visit can take about a minute while the server wakes up).
- Open /auditgen/ai and check “assistant ready · gemini-3.5-flash-lite”.
- Generate the demo pack once (Part C, step C1) so it is already in the Pack list as “(yours)”.
- Daily free limit for the whole site: 30 AI answers and 40 generated packs. The full tour below uses about 11 AI answers; do not rehearse the AI steps more than once on the day.
- Keep this tab order ready: Home · Cases case · Audit generator. Zoom the browser to 110–125% so the panel can read it.

## Part A · The benchmark (research site)

### ★ A1 · / (Home)

- **Do:** The quiz at the top shows two RBI rules side by side. Ask the panel to guess, then click the answer.
- **Input:** Click “Different requirement”.
- **Say:** “These two rules look the same. They aren't. None of the five AI systems we tested noticed. That is the problem.”
- **Proof it works:** The page shows the expert's answer and what the AI systems said.

### ★ A2 · /case/t1_md_13006::p00135%7CUrban%20Co-operative%20Banks

- **Do:** Open the Governance case (Audit Committee of the Board, Rural vs Urban co-operative banks).
- **Input:** Paste the URL, or Cases → filters: Gold = Different, Missed by every LLM = yes (56) → this case.
- **Say:** “Every LLM system says same. The expert says different. Only our structured comparator catches it, and you can see the 13 fields it compared.”
- **Proof it works:** Each system's verdict, the comparator's field table, the RBI paragraph ids and links to the official PDFs.

### A3 · /cases

- **Do:** Filter the 412 expert-labelled comparisons.
- **Input:** Gold label = Different; Missed by every LLM = yes (56); Topic = Fraud Risk Management.
- **Say:** “Every comparison is browsable and every filter is live.”
- **Proof it works:** The count updates; each card opens its case page.

### A4 · /cases/failures

- **Do:** Failure map of the 78 real differences.
- **Input:** Sort = Recovered → missed by all → others.
- **Say:** “56 differences no LLM caught; the comparator recovered 26; in 262 of 350 errors the right paragraph was already in context.”
- **Proof it works:** The three headline numbers at the top match slide 10.

### A5 · /cases/play

- **Do:** Interactive game: spot the difference.
- **Input:** Click “Curated hard cases”, then answer one case.
- **Say:** “A panel member can try it: same, different, or no matching rule.”
- **Proof it works:** After answering, the expert label and all system answers are shown.

### A6 · /cases/atlas

- **Do:** Which entity types have a Direction on which topic.
- **Input:** Pick two classes in the two lists, e.g. Commercial Banks and Small Finance Banks.
- **Say:** “11 entity types × 57 topics: where Directions exist, and where one class has none.”
- **Proof it works:** Filled cells = at least one Direction.

### A7 · /lab

- **Do:** The frozen comparator on a chosen pair (recorded run on the public site).
- **Input:** Choose a pair in the list, e.g. “Credit Information Companies → Commercial Banks · Managing Risks in Outsourcing”.
- **Say:** “Same frozen prompt and fixed rule as the sealed benchmark; the public site replays the recorded run, the key stays on the server.”
- **Proof it works:** The comparator's extracted fields and its verdict for the pair; the banner says it is a cached replay (honest by design).

### A8 · /triage

- **Do:** How much could a team let the system handle.
- **Input:** Drag the slider; click “High (≥ 0.85)”.
- **Say:** “When the comparator says high confidence it was right 96% of the time on the test set.”
- **Proof it works:** Coverage and accuracy update as the slider moves.

### ★ A9 · /results

- **Do:** Six results in plain language, each with a chart.
- **Input:** Toggle “Institution filter OFF/ON”; in the T4 list pick “T4Q01 · Does a CIC need to have a Board-approved IT outsourcing policy…”.
- **Say:** “The comparator finds 2× more real differences; copying the regulation fools the popular answer-quality score.”
- **Proof it works:** Charts change with the toggle and the question picker; numbers match slides 10–11.

### A10 · /method and /genai

- **Do:** How the benchmark was built; the ten generative-AI components.
- **Input:** Scroll.
- **Say:** “Every number on these pages is read from the published results file.”
- **Proof it works:** Hashes of the frozen prompt and rule are printed on /method.


## Part B · Research workspace (for questions on the results)

### B1 · /rq

- **Do:** Research questions → tasks → findings.
- **Input:** Click “trace →” under RQ2.
- **Say:** “Each answer traces back to its evidence.”
- **Proof it works:** The RQ text is verbatim; findings carry their caveats (e.g. single-expert gold).

### B2 · /workspace/results

- **Do:** Every metric with its 95% bootstrap interval.
- **Input:** Tabs: T1 → Paired differences → Ablations → T3 → T4.
- **Say:** “Every cell is a key in results_v2.json.”
- **Proof it works:** Hovering a cell shows its results key.

### B3 · /different

- **Do:** The ‘different’ failure explorer.
- **Input:** Tick “Only units missed by every LLM system”; click a row.
- **Say:** “For each miss: the 13-field comparator diff and its rule path.”
- **Proof it works:** The field heatmap shows which fields decide ‘different’.

### B4 · /construction and /reliability

- **Do:** From 381 Directions to 106 validated items; annotation agreement.
- **Input:** Scroll.
- **Say:** “Agreement is measured on a separate 30-item set with three raters; the gold itself is single-expert, and the site says so.”
- **Proof it works:** Counts 381 → 76,188 → 28,694 → 106.

### B5 · /atlas and /architecture

- **Do:** Corpus atlas; system map.
- **Input:** Click any filled cell; click “Structured comparator”.
- **Say:** “Click any component to see which systems use it and its measured effect.”
- **Proof it works:** Component → ablation → effect size.

### B6 · /explorer

- **Do:** Obligation Explorer (product view).
- **Input:** Your class = Commercial Banks; Topic = Fraud Risk Management; compare with = Small Finance Banks (or any class the list offers).
- **Say:** “What must my class do here, and what differs for another class.”
- **Proof it works:** Matched obligations with the comparator's verdict and evidence link.


## Part C · Audit generator (the product)

### ★ C1 · /auditgen

- **Do:** Generate an audit pack.
- **Input:** Name: Shubh Small Finance Bank · Entity class: Small Finance Banks · As of: today · Last review: 01/12/2025 · Activities: Deposits, Lending, KYC / AML, Outsourcing, IT / cyber · Group entities: click Non-Banking Financial Companies · click “Generate audit pack” (15–30 s).
- **Say:** “This is what a compliance team does on a Monday morning.”
- **Proof it works:** About 4,400 applicable obligations, ~150 flagged for human review, ~770 changes since 1 Dec 2025, ~250 calendar entries, ~6,700 differential rows vs NBFCs, 3 penalty releases. (Numbers move slightly with the date.)

### ★ C2 · Audit pack → Register

- **Do:** Applicability register.
- **Input:** Type “outsourcing” in the filter; tick “show hidden rows” once, then untick.
- **Say:** “Every obligation that applies, each citing its RBI paragraph, with its as-of status and deadline.”
- **Proof it works:** Click a source link: the official RBI PDF opens. Hidden rows are kept with their reason, never deleted.

### C3 · Changes · Calendar

- **Do:** What changed since the last review; due dates.
- **Input:** Calendar → Month view → use › to move a month.
- **Say:** “Amended or withdrawn since our last review; and what is due when.”
- **Proof it works:** Each change links to its amendment notification; entries marked “verify” are low-confidence by design.

### ★ C4 · Differential · Enforcement

- **Do:** Where we differ from the NBFC; past penalties.
- **Input:** Open both tabs.
- **Say:** “Where our duty differs from our NBFC sister company, and RBI penalties on banks like us: ₹65 lakh, ₹6.70 lakh and ₹1 crore.”
- **Proof it works:** Differential rows carry a caution note (the research result); enforcement rows link to the RBI press releases.

### C5 · Gaps · About

- **Do:** Policy gap analysis; provenance.
- **Input:** Switch Pack to “Sample Small Finance Bank” to show its gap run, then About.
- **Say:** “Gap analysis matches a policy against every obligation; on the public site it runs on a synthetic policy, uploads stay in the installed version.”
- **Proof it works:** About shows the corpus snapshot date and sha256 hash, tool and rules versions.

### ★ C6 · Review

- **Do:** Human review and sign-off.
- **Input:** Switch back to your pack · Reviewer name: Karan · set one row to “confirmed” · type a note · then “Sign off”.
- **Say:** “Nothing is settled until a named person confirms it; sign-off writes a new pack and keeps the original.”
- **Proof it works:** The progress bar moves; after a page reload the row is still confirmed (it is stored); the signed-off pack appears in the Pack list.

### C7 · Downloads

- **Do:** Five export formats.
- **Input:** Click “Compliance calendar (.ics)” (≈15 s). Excel (≈1 min), Word, PDF and JSON work the same way.
- **Say:** “Excel with filters and review columns, a Word and PDF report, a calendar file for Outlook / Google Calendar, and a JSON audit trail.”
- **Proof it works:** Open the .ics in Calendar and the .xlsx in Excel: the corpus hash and disclaimer are in every file.

### C8 · Corpus status

- **Do:** Snapshot age and refresh.
- **Input:** Open the page.
- **Say:** “Shows how fresh the RBI corpus is; the installed version can check rbi.org.in for updates.”
- **Proof it works:** Snapshot date and sha256 match the About tab.


## Part D · AI assistant (✦ AI assistant tab)

### ★ D1 · Ask · All RBI obligations

- **Do:** Ask any RBI question.
- **Input:** How often must KYC be updated for high-risk customers?
- **Say:** “Gemini answers only from the RBI paragraphs it retrieves, cites every sentence, and our NLI verifier checks each one.”
- **Proof it works:** Answer: at least once every two years. Each sentence has a source chip → official RBI PDF. “Show the 6 evidence paragraphs” lists what it read.

### ★ D2 · Ask · Small Finance Banks

- **Do:** Show the verifier holding sentences back.
- **Input:** What is the minimum capital a small finance bank must maintain?
- **Say:** “Look: it states 15% of risk-weighted assets, and the sentences it could not confirm are held back. That is the trust feature.”
- **Proof it works:** Verified and unverified sentences are labelled; unverified ones are hidden by default.

### D3 · Ask · Non-Banking Financial Companies

- **Do:** Meer's NBFC question.
- **Input:** What must an NBFC disclose to a borrower about the interest rate?
- **Say:** “Same assistant, scoped to one entity type.”
- **Proof it works:** The annualised rate, the risk gradation and the reasons, in the application and the sanction letter.

### D4 · Ask · All RBI obligations (spare)

- **Do:** Spare questions for the panel.
- **Input:** When must a fraud be reported to the RBI? · Who must approve the outsourcing policy? (scope: Small Finance Banks) · What must a bank do before outsourcing a financial service?
- **Proof it works:** All tested: verified, cited answers in 4–18 s.

### D5 · Obligation copilot

- **Do:** Explain one obligation; draft a policy clause; suggest a review status.
- **Input:** Search “outsourcing” → pick a row → Explain · Company name: Shubh Small Finance Bank → Draft clause · Suggest → Reviewer name: Karan → “I agree: mark …”.
- **Say:** “A plain-English explanation, a draft clause for our policy, and a review suggestion that changes nothing until a person accepts it.”
- **Proof it works:** Each output shows its verified sentences, the quoted evidence and a “check before deciding” note.

### D6 · Changes explained

- **Do:** Explain one change since the last review.
- **Input:** Pick the first change → Explain change.
- **Say:** “What the amendment changed, before and after, in plain words.”
- **Proof it works:** Before / after excerpts and the amendment link.

### D7 · Memo & action plan

- **Do:** Board memo and action plan from the pack's facts.
- **Input:** Draft memo → Download DOCX · Build action plan.
- **Say:** “A memo to the audit committee: every figure must appear in the pack's facts, or the sentence is flagged.”
- **Proof it works:** Tested: 5 sections, 16 of 16 sentences checked; action plan 20 of 20. “Show the facts given to the model” lists them.

### D8 · Calendar check · Differential 2nd opinion

- **Do:** Second checks on deadlines and on a difference.
- **Input:** Calendar check → “Check the N ‘verify’ entries” · Differential → pick a pair → Second opinion.
- **Say:** “The model re-reads uncertain deadlines and must quote the words it used; a second opinion on a flagged difference.”
- **Proof it works:** Agreement with the rule-based extractor is shown; quotes are checked against the paragraph.

### D9 · How it works & log

- **Do:** Transparency panel.
- **Input:** Open the tab.
- **Say:** “Which model, what goes in, how sentences are verified, and where outputs are stored.”
- **Proof it works:** Model id and verifier id are shown.

## How to prove to the panel that it works

- **Citations are real:** Click any source chip or source link: it opens the official RBI PDF on rbi.org.in / rbidocs.rbi.org.in.
- **The verifier works:** Ask D2 (minimum capital): some sentences are held back as unverified. Click “Show the evidence paragraphs”.
- **Answers are grounded, not memorised:** Invite the panel to type their own question. If the corpus does not cover it, the assistant abstains instead of guessing.
- **It is live, not a recording:** Generate with the panel's choice of entity class and date; the numbers change with the inputs.
- **State is saved:** Confirm a row in Review, reload the page: it is still confirmed. Sign-off creates a new, separate pack.
- **Exports are real files:** Download the .ics or .xlsx and open it on the laptop.
- **Provenance:** About tab and every export carry the corpus snapshot date and sha256, the tool and rules versions.
- **Research claims are checkable:** Every number on /results and /workspace/results is a key in reports/results_v2.json; /method prints the prompt and rule hashes.

## If something goes wrong

- **“connecting to the hosted service…” for over a minute:** Reload once. If it persists, switch the Pack list to a sample pack: everything except Generate and new AI answers keeps working.
- **“today's limit”:** The daily free quota is used up; show a sample pack's recorded AI answers (Pack → Sample Small Finance Bank → AI assistant).
- **An answer says it cannot answer reliably:** That is the verifier doing its job; say so and ask the next question.
- **No internet:** Run locally: python3 scripts/auditgen.py serve and cd ui && npm run dev, then open localhost:5181/auditgen (local Qwen model).
