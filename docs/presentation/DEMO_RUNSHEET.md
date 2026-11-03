# Live demo run-sheet (about 5 minutes)

Site: **https://rbioblibench5qbvp2.z29.web.core.windows.net** · audit generator: **/auditgen**

## 10 minutes before you present

1. Open **/auditgen** in the browser you will present from. The first visit wakes the server and can take about a
   minute. Wait for the green badge **"live · hosted service"**.
2. Open **/auditgen/ai** and check the badge **"assistant ready · gemini-3.5-flash-lite"**.
3. Generate your demo pack now (selections in step 4 below), so it is ready in the **Pack** list as "(yours)". During
   the demo you can generate again live, or simply pick it from the list if time is short.
4. Do not over-rehearse on the day: the free service allows **30 AI answers and 40 generated packs per day** for the
   whole site. Each question you ask uses one.
5. Backup if the internet fails: the **sample packs** and their recorded AI answers are part of the site and work without
   the server; the local version (`python3 scripts/auditgen.py serve` + `cd ui && npm run dev`) runs everything offline.

## The flow

| # | Page (URL) | What to do | What to say | Time |
|---|---|---|---|---|
| 1 | **/** Home | Scroll once | "381 Master Directions, 11 entity classes, one question: same duty or different?" | 15 s |
| 2 | **/case/t1_md_13006::p00135%7CUrban%20Co-operative%20Banks** | Point at the system verdicts | "Audit Committee of the Board, Rural vs Urban co-operative banks. Every LLM system says *same*. The expert label is *different*. Only our structured comparator catches it." | 40 s |
| 3 | **/results** | Show the headline chart | "56 of 78 real differences missed by every LLM system; the comparator lifts ‘different’ F1 from 0.154 to 0.409." | 20 s |
| 4 | **/auditgen** → Generate | Fill the form exactly as below, click **Generate audit pack** | "This is what a compliance team uses on a Monday morning." | 40 s |
| 5 | Audit pack tabs | Register (type *outsourcing* in the filter) → Changes → Calendar (Month view) → Differential → Enforcement | "Every row cites its RBI paragraph. What changed since our last review. Due dates. Where we differ from our NBFC sister company. Past penalties on banks like us." | 60 s |
| 6 | **Review** | Reviewer name: *Karan* (the bank's compliance head in the role-play); set one row to **confirmed** | "Nothing is settled until a named person confirms it, then signs off." | 20 s |
| 7 | **Downloads** | Click **Compliance calendar (.ics)** (about 15 s). Mention Excel takes up to a minute | "Excel, Word, PDF, calendar and a JSON audit trail, all with the corpus hash." | 20 s |
| 8 | **✦ AI assistant** → Ask | Ask the questions below | "Gemini answers only from the retrieved RBI text; the NLI verifier checks every sentence; unsupported ones are held back." | 60 s |
| 9 | Obligation copilot / Memo | Pick one register row → **Explain**; or **Memo & action plan** → Draft | "Plain-English drafts for the compliance memo, each sentence cited." | 30 s |

### Step 4: Generate form selections

| Field | Enter / select |
|---|---|
| Name | **Shubh Small Finance Bank** (fictional) |
| Entity class | **Small Finance Banks** |
| As of | today (leave the default) |
| Last review | **01/12/2025** |
| Activities | tick **Deposits, Lending, KYC / AML, Outsourcing, IT / cyber** |
| Group entities | click **Non-Banking Financial Companies** (one class keeps the pack quick to load; Cmd / Ctrl-click adds more) |

Expect **4,409 applicable obligations** (154 flagged for human review), **766 changes** since 1 Dec 2025, **259 calendar
entries**, **6,733 differential rows** against NBFCs, and **3 RBI penalty releases** on small finance banks in the
Enforcement tab (₹65 lakh, ₹6.70 lakh, ₹1.00 crore). Generating takes about 15–30 seconds.

### Step 8: questions to ask

All six were tested on the live site on 30 Oct 2026 and returned verified, cited answers in 4–18 seconds. Pick the scope
in the **"Answer from"** list to the left of the question box.

| # | "Answer from" | Type this question | What you should see |
|---|---|---|---|
| 1 | All RBI obligations | **How often must KYC be updated for high-risk customers?** | At least once every two years (Karan's question from the role-play) |
| 2 | All RBI obligations | **When must a fraud be reported to the RBI?** | Classification within 180 days of first flagging on CRILC, cited to the Fraud Risk Management Directions |
| 3 | Small Finance Banks | **Who must approve the outsourcing policy?** | The Board of the bank |
| 4 | Small Finance Banks | **What is the minimum capital a small finance bank must maintain?** | 15% of risk-weighted assets, **and the verifier holds back the sentences it cannot confirm**: point this out, it is the trust feature |
| 5 | Non-Banking Financial Companies | **What must an NBFC disclose to a borrower about the interest rate?** | The annualised rate, the risk gradation and the reasons, in the application and the sanction letter (Meer's NBFC) |
| 6 | All RBI obligations | **What must a bank do before outsourcing a financial service?** | A Board-approved framework; core management functions (internal audit, compliance, KYC, loan sanction) cannot be outsourced |

Under each answer, click **"Show the 6 evidence paragraphs retrieved"** to show the RBI paragraphs it came from; every
sentence has a source chip that opens the official RBI PDF.

Suggested order for the 60 seconds: 1 → 4 → 5. Keep 2, 3 and 6 for questions from the examiners.

### If something goes wrong

- **"connecting to the hosted service…" for more than a minute**: reload once. If it still hangs, switch the Pack list to a
  *sample* pack; everything except Generate and new AI answers keeps working.
- **"today's limit"**: the daily free quota is used up. Show a sample pack's recorded AI answers instead
  (Pack list → Sample Small Finance Bank → AI assistant).
- **An AI answer says it cannot answer reliably**: that is the verifier doing its job; say so, then ask the next question.
- **Policy gaps page**: uploads are only in the installed version (company documents never leave the network). Show the
  sample pack's gap run on a synthetic policy instead (Pack list → Sample Small Finance Bank → Policy gaps).
