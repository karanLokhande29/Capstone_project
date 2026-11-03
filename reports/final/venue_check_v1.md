# AISIGH–SD 2026 venue check v1 (gap G-15)

- **Checked:** 2026-10-03, between 16:27 and 16:32 IST (10:57–11:02 UTC), in the Claude desktop app's built-in browser.
- **Method:** read only. No form was submitted, and no CMT sign-in or account was created.
- **Site:** found via the hyperlink in `RBI-ObliBench_Conference_Targets.xlsx`. A web search for the acronym returned no result.
- **Pages read** (the site is a single-page app, so the sub-pages are `#/` routes):

| Id | URL |
|---|---|
| S1 | https://www.aisigh-sd.co.in/ (home, timeline) |
| S2 | https://www.aisigh-sd.co.in/#/callForPapers |
| S3 | https://www.aisigh-sd.co.in/#/publication-and-templates |
| S4 | https://www.aisigh-sd.co.in/#/camera-ready-paper-submission |
| S5 | https://www.aisigh-sd.co.in/#/registration |
| S6 | https://www.aisigh-sd.co.in/#/penalties (heading only, no content) |
| S7 | https://cmt3.research.microsoft.com/AISIGHSD2026 (CMT login page) |

## Findings

| Item | What the site says | Source | Accessed (IST) |
|---|---|---|---|
| Conference | AI-Enabled Smart Solutions for Industry, Governance, Healthcare and Sustainable Development. CUTM Bhubaneswar, with the IEEE Bhubaneswar Section; hybrid mode; 28–30 Dec 2026. | S1 | 16:27 |
| Submission deadline | 10/10/2026. The banner says this is the final extension; earlier dates 15/09 and 30/09 are struck through. | S1, S2 | 16:27 |
| Other dates | Notification 15/11/2026; camera-ready 30/11/2026; last date of registration 10/12/2026. | S1 | 16:27 |
| Camera-ready date (conflicting) | S4 says camera-ready is due "on or before 5th Jan 2026". This contradicts S1's 30/11/2026 and is probably a stale year. | S4 | 16:30 |
| Submission system | Microsoft CMT, https://cmt3.research.microsoft.com/AISIGHSD2026. The page is a login wall; nothing beyond the conference name was readable without signing in. | S2, S7 | 16:32 |
| Page limit at submission | "4–6 pages, following the IEEE Conference format guidelines". | S2 | 16:28 |
| Page limit and over-length charges | Six pages standard. Up to two extra pages: the 7th costs ₹1,000 and the 8th ₹2,000 for Indian authors (USD 50 / USD 100 for international authors). Absolute maximum 8 pages. | S5 | 16:31 |
| Template | IEEE conference templates, https://www.ieee.org/conferences/publishing/templates.html. PPT and A0 poster templates "will be updated soon". | S2, S3, S4 | 16:29 |
| File format | PDF only. | S2 | 16:28 |
| Anonymity / blind review | Not stated. | — | — |
| Similarity limit | Every submission is checked with anti-plagiarism software before review; desk rejection is possible. Camera-ready: similarity index < 25% including references (e.g. Turnitin). | S2, S4 | 16:30 |
| AI-content limit | Camera-ready: AI-generated content < 20%. Papers over either limit are excluded from IEEE Xplore and the fee is not refunded. No tool is named. | S4 | 16:30 |
| Author changes | Authors and author order cannot be changed after submission. | S2 | 16:28 |
| Registration | At least one author per accepted paper must register. Fees, excluding 18% GST: student ₹7,000 (IEEE) / ₹7,500 (non-IEEE); academia ₹8,000 / ₹9,000; industry ₹9,000 / ₹10,000. A second paper gets 50% off, except on student registrations. After paying, a Google Form must be filled. No refunds. | S5 | 16:31 |
| Presentation | Only registered **and presented** papers go to IEEE Xplore; IEEE's "No Show" policy is enforced. | S2 | 16:28 |
| PDF eXpress | Conference ID **70672X**. Create an account at https://ieee-pdf-express.org/account/Login, convert until "File has been converted successfully", then upload the downloaded PDF to CMT (camera-ready track) without renaming it. | S4 | 16:30 |
| Copyright notice | First page, footer, left: `979-8-3315-7088-0/26/$31.00 ©2026 IEEE` (other forms are for US-government, Crown or EU authors). | S4 | 16:30 |
| IEEE eCF | The corresponding author transfers copyright through the IEEE copyright link in CMT (steps 1–5), downloads the completed form as a PDF and uploads it to CMT. One transfer per paper. | S4 | 16:30 |
| Camera-ready supplementary file | A ZIP named after the paper ID (e.g. PID402) holding a response-to-reviewers sheet and a plagiarism report (Turnitin or iThenticate), uploaded as the supplementary file. | S4 | 16:30 |
| Penalties page | Heading only; no content. | S6 | 16:29 |
| Contact | aisighsd2026@cutm.ac.in (registration queries: aisighsd2026@gmail.com). | S2, S5 | 16:31 |

## Differences from `submission_checklist_v2.md` (authors to review)

The checklist was compared only for these differences. Nothing else from it is copied here.

1. **Page count at submission.**
   - The checklist plans a 6-page draft with a paid 7-page fallback and a hard maximum of 8.
   - The CFP (S2) says submissions are **4–6 pages**. Over-length charges for pages 7–8 appear only on the registration page (S5), where they read as camera-ready charges.
   - **Treat 6 pages as the limit for the 10 Oct submission.** The current draft estimate is 5.8 pages. Confirm with the organisers before relying on the 7th page at submission.
2. **The checklist is missing camera-ready steps.** It does not list:
   - PDF eXpress with conference ID 70672X;
   - the first-page copyright notice;
   - the IEEE eCF upload in CMT;
   - the supplementary ZIP (response sheet + plagiarism report);
   - the rule that authors and author order cannot be changed after submission;
   - the presentation / "No Show" rule.
3. **Plagiarism screening at submission.** The checklist applies the < 25% similarity rule to the camera-ready only. S2 says every submission is screened *before review* and can be desk-rejected. Run the similarity check before 10 Oct, not only for the camera-ready.
4. **"PDF only; no supplementary file".** This matches S2 for the initial submission. The camera-ready, however, *requires* a supplementary ZIP (S4).
5. **Camera-ready date conflict** on the site itself: 30/11/2026 (S1) vs "5th Jan 2026" (S4). Ask the organisers.
6. **Anonymity.** The checklist records "not anonymous" elsewhere in the project; the site does not state a review mode. Keep "Needs validation".
