#!/usr/bin/env python3
"""Validate every page in site/ as HTML5, and check the maths actually rendered.

Run via `make site-check`. Exits non-zero on the first problem, so it works as a gate
before pushing anything the GitHub Pages workflow will publish.
"""

from __future__ import annotations

import pathlib
import re
import sys

import html5lib

SITE = pathlib.Path(__file__).resolve().parent

# A rendered formula must not still contain a TeX command, and no placeholder from the
# build script may survive into the published page.
STRAY_TEX = re.compile(r'class="math-[a-z]+">[^<]*\\[a-zA-Z]+')
PLACEHOLDER = re.compile(r"(MATH|DETAILS)PLACEHOLDER\d+X")


def main() -> int:
    failures: list[str] = []

    for path in sorted(SITE.glob("*.html")):
        text = path.read_text(encoding="utf-8")

        parser = html5lib.HTMLParser()
        parser.parse(text)
        if parser.errors:
            line, code, data = parser.errors[0]
            failures.append(f"{path.name}: {len(parser.errors)} HTML5 error(s); first: {code} {data} at {line}")

        if stray := STRAY_TEX.findall(text):
            failures.append(f"{path.name}: {len(stray)} unrendered TeX command(s), e.g. {stray[0][:60]}")

        if left := PLACEHOLDER.findall(text):
            failures.append(f"{path.name}: {len(left)} build placeholder(s) leaked into output")

    if failures:
        for failure in failures:
            print(f"FAIL  {failure}", file=sys.stderr)
        return 1

    print(f"site: {len(list(SITE.glob('*.html')))} pages valid HTML5, no stray TeX")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
