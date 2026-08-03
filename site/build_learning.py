#!/usr/bin/env python3
"""Generate the learning pages of the site from docs/learning/*.md.

The markdown files stay the single source of truth: edit those, re-run this, commit the
generated HTML. Nothing here is hand-maintained.

Maths is rendered without KaTeX/MathJax on purpose — the published artifact's CSP blocks
external hosts, and bundling a full TeX renderer for a few dozen formulas is not worth the
weight. `_render_math` handles the constructs these notes actually use (fractions, powers,
subscripts, Greek letters, common operators) and falls back to the literal TeX otherwise,
which stays readable rather than turning into mojibake.

Usage:  uv run python3 site/build_learning.py
"""

from __future__ import annotations

import html
import re
from pathlib import Path

import markdown

REPO = Path(__file__).resolve().parent.parent
LEARNING = REPO / "docs" / "learning"
SITE = REPO / "site"

PAGES = [
    {
        "src": LEARNING / "track-a" / "a1-probability-foundations.md",
        "out": SITE / "learning-a1.html",
        "title": "A1 — Probability Foundations",
        "track": "Track A — Probability &amp; Inference",
        "blurb": "Is my edge real, and how much do I bet?",
    },
    {
        "src": LEARNING / "track-b" / "b1-what-a-model-is.md",
        "out": SITE / "learning-b1.html",
        "title": "B1 — What a Model Is",
        "track": "Track B — Modelling Foundations",
        "blurb": "Where does a probability actually come from?",
    },
]

# TeX command -> unicode. Only what these notes use.
SYMBOLS = {
    r"\times": "×", r"\cdot": "·", r"\pm": "±", r"\mp": "∓",
    r"\leq": "≤", r"\le": "≤", r"\geq": "≥", r"\ge": "≥",
    r"\neq": "≠", r"\approx": "≈", r"\equiv": "≡", r"\sim": "∼",
    r"\to": "→", r"\rightarrow": "→", r"\leftarrow": "←",
    r"\Rightarrow": "⇒", r"\iff": "⇔", r"\mapsto": "↦",
    r"\infty": "∞", r"\partial": "∂", r"\nabla": "∇",
    r"\sum": "∑", r"\prod": "∏", r"\int": "∫",
    r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ",
    r"\epsilon": "ε", r"\varepsilon": "ε", r"\theta": "θ", r"\lambda": "λ",
    r"\mu": "μ", r"\pi": "π", r"\rho": "ρ", r"\sigma": "σ", r"\tau": "τ",
    r"\phi": "φ", r"\chi": "χ", r"\psi": "ψ", r"\omega": "ω",
    r"\Delta": "Δ", r"\Sigma": "Σ", r"\Omega": "Ω", r"\Phi": "Φ",
    r"\in": "∈", r"\notin": "∉", r"\subset": "⊂", r"\cup": "∪", r"\cap": "∩",
    r"\forall": "∀", r"\exists": "∃", r"\mid": "|", r"\perp": "⊥",
    r"\neg": "¬", r"\lnot": "¬", r"\land": "∧", r"\lor": "∨", r"\propto": "∝",
    r"\ldots": "…", r"\dots": "…", r"\cdots": "⋯",
    r"\%": "%", r"\&": "&", r"\_": "_", r"\{": "{", r"\}": "}",
    r"\,": " ", r"\;": " ", r"\:": " ", r"\!": "",
    r"\quad": "  ", r"\qquad": "   ",
    # Function names stay upright in TeX; here they are just words.
    r"\log": "log", r"\ln": "ln", r"\exp": "exp", r"\min": "min", r"\max": "max",
    r"\arg": "arg", r"\sin": "sin", r"\cos": "cos", r"\Pr": "Pr", r"\Var": "Var",
    r"\mathrm": "",
}

SUPERSCRIPT = str.maketrans("0123456789+-=()n2i", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ²ⁱ")
SUBSCRIPT = str.maketrans("0123456789+-=()aeioxjmnt", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑᵢₒₓⱼₘₙₜ")


def _match_brace(text: str, start: int) -> int:
    """Index just past the `}` closing the `{` at `start`, or -1 if unbalanced."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return -1


def _expand_fracs(s: str) -> str:
    """Rewrite every \\frac{a}{b} as a/b, brace-aware so nested groups survive.

    A regex cannot do this: `\\frac{1}{1 + e^{-z}}` has braces inside the denominator, and
    any `[^{}]*` pattern skips it silently — which is how five formulas reached the page
    unrendered before the validator caught them.
    """
    for _ in range(12):  # bounded: each pass removes at least one \frac
        match = re.search(r"\\[dt]?frac\s*\{", s)
        if not match:
            return s
        num_open = s.index("{", match.start())
        num_end = _match_brace(s, num_open)
        if num_end < 0:
            return s
        rest = s[num_end:]
        den_rel = rest.find("{")
        if den_rel < 0 or rest[:den_rel].strip():
            return s
        den_open = num_end + den_rel
        den_end = _match_brace(s, den_open)
        if den_end < 0:
            return s

        numerator = _expand_fracs(s[num_open + 1 : num_end - 1])
        denominator = _expand_fracs(s[den_open + 1 : den_end - 1])
        if re.search(r"[+\-\s]", numerator.strip()):
            numerator = f"({numerator})"
        if re.search(r"[+\-\s]", denominator.strip()):
            denominator = f"({denominator})"
        s = s[: match.start()] + f"{numerator}/{denominator}" + s[den_end:]
    return s


def _render_math(tex: str) -> str:
    """Turn a TeX fragment into readable HTML. Best-effort, never lossy-to-garbage."""
    s = tex.strip()

    # Resolve text/styling wrappers FIRST: \frac{\text{a}}{\text{b}} has nested braces that
    # the fraction pattern would otherwise skip over.
    for _ in range(4):
        new = re.sub(r"\\(?:text(?:rm|bf|it|sf)?|mathrm|mathbb|mathcal)\{([^{}]*)\}", r"\1", s)
        new = re.sub(r"\\underbrace\{([^{}]*)\}", r"\1", new)
        if new == s:
            break
        s = new

    # \frac{a}{b} -> a/b, with parens when either side is compound.
    def frac(m: re.Match[str]) -> str:
        num, den = m.group(1), m.group(2)
        num = f"({num})" if re.search(r"[+\-\s]", num.strip()) else num
        den = f"({den})" if re.search(r"[+\-\s]", den.strip()) else den
        return f"{num}/{den}"

    s = _expand_fracs(s)
    # \frac followed by single tokens rather than braces: \frac12 or \frac odds 1+odds
    s = re.sub(r"\\[dt]?frac\s*(\w+)\s*(\w+)", r"\1/\2", s)

    s = re.sub(r"\\sqrt\{([^{}]*)\}", r"√(\1)", s)
    s = re.sub(r"\\text(?:rm|bf|it|sf)?\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\mathbf\{([^{}]*)\}", r"<strong>\1</strong>", s)
    s = re.sub(r"\\mathbb\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\mathcal\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\operatorname\{([^{}]*)\}", r"\1", s)
    # Accents: \hat{p} -> p̂, \bar{x} -> x̄  (combining marks, so they follow the letter)
    s = re.sub(r"\\hat\{([^{}]*)\}", lambda m: m.group(1) + "\u0302", s)
    s = re.sub(r"\\bar\{([^{}]*)\}", lambda m: m.group(1) + "\u0304", s)
    s = re.sub(r"\\tilde\{([^{}]*)\}", lambda m: m.group(1) + "\u0303", s)
    s = re.sub(r"\\hat\s+(\w)", lambda m: m.group(1) + "\u0302", s)
    # Sizing and grouping commands carry no meaning once rendered as text.
    s = re.sub(r"\\(bigg?|Bigg?|left|right)([()\[\]|.]?)", r"\2", s)
    s = re.sub(r"\\underbrace\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"_\{\\text\{[^{}]*\}\}", "", s)

    for cmd, char in sorted(SYMBOLS.items(), key=lambda kv: -len(kv[0])):
        s = s.replace(cmd, char)

    # ^{...} and _{...}
    def sup(m: re.Match[str]) -> str:
        body = m.group(1)
        if all(c in "0123456789+-=()n2i" for c in body):
            return body.translate(SUPERSCRIPT)
        return f"<sup>{body}</sup>"

    def sub(m: re.Match[str]) -> str:
        body = m.group(1)
        if all(c in "0123456789+-=()aeioxjmnt" for c in body):
            return body.translate(SUBSCRIPT)
        return f"<sub>{body}</sub>"

    s = re.sub(r"\^\{([^{}]*)\}", sup, s)
    s = re.sub(r"_\{([^{}]*)\}", sub, s)
    s = re.sub(r"\^(\w)", lambda m: sup(m), s)
    s = re.sub(r"_(\w)", lambda m: sub(m), s)

    s = s.replace("\\\\", " ")
    # Any styling command that survived (braces already stripped elsewhere) is noise.
    s = re.sub(r"\\(mathbf|mathrm|mathbb|mathcal|boldsymbol|displaystyle)\b", "", s)
    s = re.sub(r"\{|\}", "", s)

    # Escape HTML metacharacters LAST — "a > 0" must not be parsed as a tag. <strong> is
    # the only markup _render_math emits, so it is restored afterwards.
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = s.replace("&lt;strong&gt;", "<strong>").replace("&lt;/strong&gt;", "</strong>")
    s = s.replace("&lt;sup&gt;", "<sup>").replace("&lt;/sup&gt;", "</sup>")
    s = s.replace("&lt;sub&gt;", "<sub>").replace("&lt;/sub&gt;", "</sub>")
    return s


def _protect_math(text: str) -> tuple[str, dict[str, str]]:
    """Swap $...$ / $$...$$ for placeholders so markdown can't mangle them."""
    store: dict[str, str] = {}

    def stash(rendered: str, block: bool) -> str:
        key = f"MATHPLACEHOLDER{len(store)}X"
        tag = "div" if block else "span"
        cls = "math-block" if block else "math-inline"
        store[key] = f'<{tag} class="{cls}">{rendered}</{tag}>'
        return key

    text = re.sub(
        r"\$\$(.+?)\$\$",
        lambda m: stash(_render_math(m.group(1)), True),
        text,
        flags=re.DOTALL,
    )
    # Inline math must not swallow prose currency ("$1 thirty times per hundred ... $5").
    # A real formula has no unescaped space immediately after the opening $, and does not
    # open with a digit followed by a space — which is what "$1 per bet" looks like.
    def maybe_inline(m: re.Match[str]) -> str:
        body = m.group(1)
        if body.startswith(" ") or body.endswith(" "):
            return m.group(0)
        if re.match(r"^\d[\d,.]*\s", body):  # "$1 thirty times..." — currency, not maths
            return m.group(0)
        if len(body) > 90 and not re.search(r"[\\^_=+]", body):  # long prose, no operators
            return m.group(0)
        return stash(_render_math(body), False)

    text = re.sub(r"(?<!\$)\$([^$\n]+?)\$(?!\$)", maybe_inline, text)
    return text, store


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def build_page(spec: dict) -> str:
    raw = spec["src"].read_text(encoding="utf-8")
    protected, math = _protect_math(raw)

    # Convert the <details> wrapper to placeholders and render its body as ordinary
    # markdown. Leaving the raw tags inline makes markdown emit unbalanced <p> around the
    # block, which no amount of post-hoc regex reliably repairs.
    details_blocks: list[str] = []

    def stash_details(match: re.Match[str]) -> str:
        summary, inner = match.group(1), match.group(2)
        rendered = markdown.markdown(inner, extensions=["tables", "fenced_code"])
        details_blocks.append(
            f"<details><summary>{summary}</summary>\n{rendered}\n</details>"
        )
        return f"\n\nDETAILSPLACEHOLDER{len(details_blocks) - 1}X\n\n"

    protected = re.sub(
        r"<details>\s*<summary>(.*?)</summary>\s*(.*?)</details>",
        stash_details,
        protected,
        flags=re.DOTALL,
    )

    body = markdown.markdown(
        protected,
        extensions=["tables", "fenced_code", "toc", "attr_list"],
    )

    for index, block in enumerate(details_blocks):
        body = re.sub(
            rf"<p>\s*DETAILSPLACEHOLDER{index}X\s*</p>|DETAILSPLACEHOLDER{index}X",
            lambda _, b=block: b,
            body,
        )
    for key, rendered in math.items():
        body = body.replace(key, rendered)

    # <div> is not phrasing content, so a block formula inside <p> is invalid nesting.
    # markdown wraps them either alone (<p><div>…</div></p>) or after text
    # (<p>lead-in:<div>…</div></p>). Close the paragraph before the div and reopen after,
    # dropping any empty fragments that leaves behind.
    body = re.sub(
        r"(<div class=\"math-block\">.*?</div>)", r"</p>\1<p>", body, flags=re.DOTALL
    )
    body = re.sub(r"<p>\s*</p>", "", body)
    body = re.sub(r"</p>\s*</p>", "</p>", body)
    body = re.sub(r"<p>\s*<p>", "<p>", body)
    # markdown opens a <p> before a raw <details> block and closes it after, so the
    # rewriting above can strand tags around the boundary. <details> is flow content and
    # never belongs inside <p> anyway — lift it out.
    body = re.sub(r"<p>\s*(<details>)", r"\1", body)
    body = re.sub(r"(</details>)\s*</p>", r"\1", body)
    body = re.sub(r"<p>\s*</p>", "", body)

    # Wide tables scroll inside their own container, never the page body.
    body = body.replace("<table>", '<div class="table-wrap"><table>').replace(
        "</table>", "</table></div>"
    )

    # Build a contents list from the h2s.
    headings = re.findall(r"<h2[^>]*>(.*?)</h2>", body)
    toc_items = ""
    for heading in headings:
        clean = re.sub(r"<[^>]+>", "", heading)
        anchor = _slug(clean)
        body = body.replace(f"<h2>{heading}</h2>", f'<h2 id="{anchor}">{heading}</h2>', 1)
        toc_items += f'    <li><a href="#{anchor}">{html.escape(clean)}</a></li>\n'

    toc = f'<nav class="toc"><p><strong>On this page</strong></p>\n<ol>\n{toc_items}</ol></nav>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{spec['title']} — EdgeLedger</title>
<meta name="description" content="{html.escape(spec['blurb'])} EdgeLedger learning notes.">
<link rel="stylesheet" href="style.css">
</head>
<body>

<header>
  <h1>{spec['title']}</h1>
  <p class="tagline">{spec['track']} — <em>{spec['blurb']}</em></p>
  <nav>
    <a href="index.html">Overview</a>
    <a href="methodology.html">Methodology</a>
    <a href="results.html">Results</a>
    <a href="learning.html" aria-current="page">Learning</a>
  </nav>
</header>

<main class="prose">
{toc}
{body}
</main>

<footer>
  <p><a href="learning.html">&larr; Back to the learning index</a> — generated from
  <code>{spec['src'].relative_to(REPO)}</code>, the source of truth.</p>
</footer>

</body>
</html>
"""


def main() -> None:
    for spec in PAGES:
        spec["out"].write_text(build_page(spec), encoding="utf-8")
        print(f"wrote {spec['out'].relative_to(REPO)}  ({spec['src'].name})")


if __name__ == "__main__":
    main()
