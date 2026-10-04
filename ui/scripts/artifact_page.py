#!/usr/bin/env python3
"""Turn the hosted build (ui/dist-artifact/index.html) into an Artifact page: the host wraps the page in its own
<!doctype html><head><body> skeleton, so the page file carries only <title>, meta, links, scripts and the root element.

    npm run build:hosted   ->   ui/dist-artifact/page.html  (+ the files it references under assets/)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

UI = Path(__file__).resolve().parents[1]
OUT = UI / "dist-artifact"


def main() -> int:
    html = (OUT / "index.html").read_text(encoding="utf-8")
    head = re.search(r"<head>(.*?)</head>", html, re.S).group(1)
    body = re.search(r"<body>(.*?)</body>", html, re.S).group(1)
    head = re.sub(r'\s*<meta charset="UTF-8" />|\s*<meta name="viewport"[^>]*/>|\s*<link rel="icon" href="[^"]*" />', "", head)
    title = re.search(r"<title>.*?</title>", head).group(0)
    head = title + "\n" + head.replace(title, "").strip()  # the host scans the first 8KB for <title>
    page = "\n".join(x.rstrip() for x in (head.strip(), body.strip())) + "\n"
    (OUT / "page.html").write_text(page, encoding="utf-8")
    assets = sorted(str(p.relative_to(OUT)) for p in (OUT / "assets").rglob("*") if p.is_file())
    referenced = set(re.findall(r'(?:src|href)="\./(assets/[^"]+)"', page))
    missing = referenced - set(assets)
    if missing:
        raise SystemExit(f"page references missing files: {missing}")
    (OUT / "files.json").write_text(json.dumps({a: f"ui/dist-artifact/{a}" for a in assets}, indent=1))
    size = sum((OUT / a).stat().st_size for a in assets) + len(page.encode())
    print(f"page.html written; {len(assets)} asset files; total {size / 1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
