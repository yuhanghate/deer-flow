"""Markdown → HTML preprocessing for Chinese patent DOCX generation.

Pipeline: Markdown → (headings) → Python-Markdown → HTML → <sub>/<sup> injection → DOCX.

HTML ``<sub>`` / ``<sup>`` tags are preserved by pandoc and become native Word
subscript / superscript formatting (``w:vertAlign``).

- Unicode subscript digits after letters (e.g. ``Nd₂``) → ``<sub>2</sub>``
- Unicode subscript letters (ₐᵦ) → ``<sub>ab</sub>``
- Underscore subscripts (``_X``, ``_{...}``) → ``<sub>...</sub>``
- Patent section headers get ``# `` / ``## `` before Markdown conversion
"""
from __future__ import annotations

import re

import markdown

# Unicode subscript digits → ASCII digits
_SUBSCRIPT_DIGIT_MAP = {
    "₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4",
    "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9",
}
# Only match subscript digits that follow a letter (chemical element context).
# This avoids converting digit-preceded subscripts like 5₂₀°C (LLM artifact).
_SUBSCRIPT_DIGITS_RE = re.compile(r"(?<=[a-zA-Z])[₀₁₂₃₄₅₆₇₈₉]+")

# Unicode subscript letters commonly used in chemical formulas
_SUBSCRIPT_LETTER_MAP = {
    "ₐ": "a", "ᵦ": "b", "꜀": "c", "ₑ": "e", "ₘ": "m",
    "ₒ": "o", "ₚ": "p", "ₛ": "s", "ₜ": "t", "ₓ": "x",
    "ᵧ": "y", "ₕ": "h", "ₖ": "k", "ₗ": "l", "ₙ": "n",
}

# Patterns that look like patent section headers (for heading injection)
_H1_PATTERNS = [
    r"^\d+[.．]\s*(?:技术领域|背景技术|发明内容|附图说明|具体实施方式)\s*$",
    r"^(?:6\.|2\.)?\s*权利要求书\s*$",
    r"^(?:说明书)?摘要\s*$",
    r"^(?:说明书)?摘要\s*[：:]\s*$",
    r"^(?:说明书)?\s*$",
    r"^(?:进一步)?改进建议\s*$",
    r"^待(?:审核|申请人确认事项|确认)\s*$",
    r"^合规自检清单\s*$",
    r"^待申请人确认事项\s*$",
    r"^关键信息缺失清单\s*$",
    r"^暂定假设表\s*$",
    r"^(?:一|二|三|四|五|六)?[、.．]?\s*(?:技术领域|背景技术|发明内容|附图说明|具体实施方式)\s*[:：]?\s*$",
    r"^(?:权利要求书|说明书摘要|摘要)\s*[:：]?\s*$",
]
_H2_PATTERNS = [
    r"^\d+\.\d+\s+.*",
    r"^(?:实施例|对比例)\s*\d+\s*[:：].*",
    r"^\d+\.\d+\.\d+\s+.*",
]
_TITLE_EXCLUDE_PREFIXES = (
    "【摘要】", "摘要", "说明书摘要", "说明书", "权利要求书",
    "1. 技术领域", "2. 背景技术", "3. 发明内容", "4. 附图说明",
    "5. 具体实施方式",
)


def auto_add_headings(content: str) -> str:
    """Add Markdown ``#`` / ``##`` prefix to recognised patent section headers.

    Runs *before* Markdown conversion so headings appear in the HTML output.
    """
    lines = content.split("\n")
    result: list[str] = []
    first_handled = False

    for line in lines:
        if not line.strip():
            result.append(line)
            continue

        # Skip Markdown pipe tables (lines starting with |)
        if stripped := line.strip():
            if stripped.startswith("|"):
                result.append(line)
                if not first_handled:
                    first_handled = True
                continue

        if not first_handled:
            stripped = line.strip()
            is_known = (
                stripped.startswith(_TITLE_EXCLUDE_PREFIXES)
                or any(re.match(pat, stripped) for pat in _H1_PATTERNS)
            )
            if stripped.lstrip().startswith("#"):
                result.append(line)
            elif is_known:
                result.append(f"# {stripped}")
            else:
                result.append(f"# {stripped}")
            first_handled = True
            continue

        matched = False
        for pat in _H1_PATTERNS:
            if re.match(pat, line.strip()):
                if not line.lstrip().startswith("#"):
                    result.append(f"# {line.strip()}")
                else:
                    result.append(line)
                matched = True
                break
        if matched:
            continue

        for pat in _H2_PATTERNS:
            if re.match(pat, line.strip()):
                if not line.lstrip().startswith("#"):
                    result.append(f"## {line.strip()}")
                else:
                    result.append(line)
                matched = True
                break
        if matched:
            continue

        result.append(line)

    return "\n".join(result)


def preprocess_markdown_to_html(content: str) -> str:
    """Convert patent Markdown to HTML with ``<sub>``/``<sup>`` tags for chemical formulas.

    Pipeline:
    1. Inject ``# `` / ``## `` heading prefixes for patent sections
    2. ``markdown.markdown()`` to get clean HTML
    3. Post-process HTML:
       - Unicode subscript digits (after letters only) → ``<sub>``
       - Unicode subscript letters → ``<sub>``
       - ``_{...}`` → ``<sub>``
       - ``_X`` → ``<sub>``
       - ``^{-N}`` / ``{-N}`` → ``<sup>``
    """
    # Step A: inject heading prefixes
    content = auto_add_headings(content)

    # Step B: markdown → HTML (Python-Markdown library)
    # - tables: pipe tables → <table> for Word output
    # - footnotes: [^1] references for prior art / data sources
    # - sane_lists: robust handling of mixed nested/numbered lists in claims
    # - def_list: definition lists for terminology glossaries
    html = markdown.markdown(content, extensions=["tables", "footnotes", "sane_lists", "def_list"])

    # Step C: inject <sub> / <sup> tags into the HTML

    # Unicode subscript digits → <sub>digits</sub> (only after letters)
    def _digit_sub(m: re.Match) -> str:
        return "<sub>" + "".join(_SUBSCRIPT_DIGIT_MAP[c] for c in m.group()) + "</sub>"
    html = _SUBSCRIPT_DIGITS_RE.sub(_digit_sub, html)

    # Unicode subscript letters → <sub>letter</sub>
    for uc, ascii in _SUBSCRIPT_LETTER_MAP.items():
        html = html.replace(uc, f"<sub>{ascii}</sub>")

    # _{...} → <sub>...</sub>
    html = re.sub(r"_\{([^}]+)\}", r"<sub>\1</sub>", html)

    # _X (single char after letter/digit) → <sub>X</sub>
    html = re.sub(r"(?<=[a-zA-Z0-9])_([a-zA-Z0-9])", r"<sub>\1</sub>", html)

    # ^{-N} or {-N} (superscript notation) → <sup>N</sup>
    html = re.sub(r"\^?\{([-+]?[0-9]+)\}", r"<sup>\1</sup>", html)

    # Insert ~ between adjacent numeric values that look like ranges.
    # E.g. "27.6wt%29.0wt%" → "27.6~29.0wt%", "400°C750°C" → "400~750°C"
    # Requires TWO number-unit sequences (lookahead finds second value after first unit).
    # Single values like 1800ppm are NOT matched (no second value follows).
    _RANGE_INSERT_RE = re.compile(
        r"(\d+(?:\.\d+)?)([%°℃&#a-zA-Z]+)(?=\d+(?:\.\d+)?[%°℃&#a-zA-Z]+)"
    )
    html = _RANGE_INSERT_RE.sub(r"\1~", html)

    return html
