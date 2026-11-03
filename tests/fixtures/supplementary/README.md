# P2-003 test fixtures

Hand-written pages that reproduce the **markup** of the live RBI pages seen on 2026-09-26
(the same containers, classes, table layouts and markup variants), with **invented text**.
No RBI page is copied here (R6: raw pages are stored locally and on private Kaggle Datasets only).

| File | Mirrors |
|---|---|
| `faq_index.html` | `FAQDisplay.aspx`: one `table.tablebg` per category, `a.link2` with `<b>date</b> title` |
| `faq_901.html` | topic with a table of contents, `Q 1.` questions, `Ans.` answers, a trailing disclaimer |
| `faq_902.html` | topic in "Sr. No. / Query N: / Clarification:" table rows, section headings, Master Direction links |
| `faq_903.html` | topic with a leading disclaimer and one answer shared by two questions ("A.(1 to 2)") |
| `pr_listing.html`, `pr_2026.html` | `BS_PressReleaseDisplay.aspx` GET page (ASP.NET form) and a year listing (POST) |
| `pen_801.html` - `pen_803.html` | penalty releases: quoted titles; unquoted subject with (i)/(ii) charges; statute-only |
| `captcha.html` | a CAPTCHA challenge page served in place of `pen_804` |
| `notif_listing.html`, `notif_2026.html` | `NotificationUser.aspx` GET page and a year listing |
| `amd_701.html`, `amd_702.html` | Amendment Directions notifications |
| `withdrawn_list.html` | `NotificationUserWithdrawnCircular.aspx`, including an `@` row |
