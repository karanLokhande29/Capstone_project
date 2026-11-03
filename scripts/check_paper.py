#!/usr/bin/env python3
"""Static build check for paper/aisigh (no TeX needed). Fails (exit 1) while any \\placeholder{} remains, or on a
structural problem:
- an \\input or \\includegraphics target that is missing;
- unbalanced braces;
- shell-escape use;
- a \\cite key that is not in the bibliography named by \\bibliography{};
- a `[verify]` or `<TODO>` marker left in that bibliography.
It also lists bib entries that nothing cites.

    python3 scripts/check_paper.py [--allow-placeholders]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper/aisigh"


def tex_files(main: Path) -> list[Path]:
    seen, todo = [], [main]
    while todo:
        f = todo.pop()
        if f in seen or not f.exists():
            continue
        seen.append(f)
        for m in re.finditer(r"\\input\{([^}]+)\}", f.read_text(encoding="utf-8")):
            p = PAPER / m.group(1)
            todo.append(p if p.suffix else p.with_suffix(".tex"))
    return seen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-placeholders", action="store_true")
    a = ap.parse_args()
    main_tex = PAPER / "main.tex"
    problems, placeholders = [], []
    files = tex_files(main_tex)
    m_bib = re.search(r"\\bibliography\{([^}]+)\}", main_tex.read_text(encoding="utf-8"))
    bib_file = PAPER / f"{m_bib.group(1)}.bib" if m_bib else PAPER / "refs.bib"
    bib = bib_file.read_text(encoding="utf-8") if bib_file.exists() else ""
    if not bib:
        problems.append(f"bibliography {bib_file.name} missing")
    keys = set(re.findall(r"@\w+\{([^,]+),", bib))
    cited: set[str] = set()
    for f in files:
        text = f.read_text(encoding="utf-8")
        body = re.sub(r"(?<!\\)%.*", "", text)
        rel = f.relative_to(PAPER)
        for m in re.finditer(r"\\input\{([^}]+)\}", body):
            p = PAPER / m.group(1)
            if not (p.exists() or p.with_suffix(".tex").exists()):
                problems.append(f"{rel}: missing \\input {m.group(1)}")
        for m in re.finditer(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", body):
            if not (PAPER / m.group(1)).exists():
                problems.append(f"{rel}: missing figure {m.group(1)}")
        if body.count("{") - body.count("\\{") != body.count("}") - body.count("\\}"):
            problems.append(f"{rel}: unbalanced braces")
        if re.search(r"\\write18|shell-escape|minted|\\immediate\\write", body):
            problems.append(f"{rel}: shell-escape construct")
        for m in re.finditer(r"\\cite\{([^}]+)\}", body):
            for k in m.group(1).split(","):
                cited.add(k.strip())
                if k.strip() not in keys:
                    problems.append(f"{rel}: \\cite key {k.strip()} not in {bib_file.name}")
        placeholders += [f"{rel}: {m.group(1)}" for m in re.finditer(r"\\placeholder\{([^}]*)\}", body)
                         if "newcommand" not in body[max(0, m.start() - 40):m.start()]]
    verify = len(re.findall(r"\[verify\]|<[A-Z ]+>", bib))
    unused = sorted(keys - cited)
    print(f"files checked: {len(files)}; structural problems: {len(problems)}; placeholders: {len(placeholders)}; "
          f"[verify]/<TODO> in {bib_file.name}: {verify}; bib entries {len(keys)}, cited {len(cited & keys)}, unused {len(unused)}")
    if unused:
        print("  unused bib entries:", ", ".join(unused))
    for p in problems:
        print("  PROBLEM", p)
    if placeholders:
        print("  placeholders (first 15):", "; ".join(placeholders[:15]))
    ok = not problems and (a.allow_placeholders or (not placeholders and verify == 0))
    print("BUILD CHECK:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
