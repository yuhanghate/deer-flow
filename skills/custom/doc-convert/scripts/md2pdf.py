#!/usr/bin/env python3
"""Cross-platform document-to-PDF converter.

Supports: Markdown → PDF, HTML → PDF, DOCX → PDF.
Automatically selects the best rendering engine, with special handling
for chemical formulas and math equations (KaTeX via Chromium).

Engine priority (tries in order, uses first available):
  With formulas ($...$ or $$...$$):
    playwright → weasyprint → pandoc+weasyprint → pandoc+xelatex → fpdf2
  Without formulas:
    weasyprint → playwright → pandoc+weasyprint → pandoc+xelatex → fpdf2

Usage:
    python md2pdf.py input.md -o output.pdf
    python md2pdf.py input.md -o output.pdf --css style.css
    python md2pdf.py input.html -o output.pdf
    python md2pdf.py input.docx -o output.pdf
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_CSS = """\
body {
    font-family: -apple-system, "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC",
                 "Source Han Sans SC", "Hiragino Sans GB", "WenQuanYi Micro Hei",
                 sans-serif;
    max-width: 800px;
    margin: 40px auto;
    padding: 0 20px;
    line-height: 1.8;
    color: #333;
    font-size: 14px;
}
h1 { font-size: 24px; border-bottom: 2px solid #333; padding-bottom: 8px; }
h2 { font-size: 20px; border-bottom: 1px solid #ccc; padding-bottom: 6px; margin-top: 32px; }
h3 { font-size: 16px; margin-top: 24px; }
h4 { font-size: 14px; margin-top: 20px; }
table { border-collapse: collapse; width: 100%; margin: 16px 0; }
th, td { border: 1px solid #ddd; padding: 8px 12px; text-align: left; }
th { background: #f5f5f5; font-weight: bold; }
code { background: #f4f4f4; padding: 2px 6px; border-radius: 3px; font-size: 13px; }
pre { background: #f4f4f4; padding: 16px; border-radius: 4px; overflow-x: auto; }
pre code { background: none; padding: 0; }
blockquote { border-left: 4px solid #ddd; margin: 16px 0; padding: 8px 16px; color: #666; }
ul, ol { padding-left: 24px; }
li { margin: 4px 0; }
img { max-width: 100%; height: auto; display: block; margin: 16px auto; }
figure { margin: 16px 0; text-align: center; }
figcaption, .img-caption { text-align: center; font-size: 12px; color: #666; margin-top: 4px; }
@page { margin: 2cm; }
"""

# KaTeX CDN for rendering LaTeX math/chemistry in Chromium-based engines
KATEX_HEAD = """\
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css"
      crossorigin="anonymous">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"
        crossorigin="anonymous"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"
        crossorigin="anonymous"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/mhchem.min.js"
        crossorigin="anonymous"></script>
"""

KATEX_BODY_SCRIPT = """\
<script>
document.addEventListener("DOMContentLoaded", function() {
    renderMathInElement(document.body, {
        delimiters: [
            {left: "$$", right: "$$", display: true},
            {left: "$", right: "$", display: false},
            {left: "\\\\(", right: "\\\\)", display: false},
            {left: "\\\\[", right: "\\\\]", display: true}
        ],
        throwOnError: false,
        trust: true
    });
});
</script>
"""

# Regex to detect LaTeX math/formula content
_FORMULA_RE = re.compile(
    r"\$\$.+?\$\$"       # display math $$...$$
    r"|\$[^$\n]+?\$"     # inline math $...$
    r"|\\ce\{.+?\}"      # mhchem \ce{...}
    r"|\\\(.+?\\\)"      # \(...\)
    r"|\\\[.+?\\\]",     # \[...\]
    re.DOTALL,
)

_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_CN_PATENT_HINTS = (
    "权利要求书",
    "说明书摘要",
    "技术领域",
    "背景技术",
    "发明内容",
    "具体实施方式",
    "附图说明",
    "本发明",
)


def _has_formulas(text: str) -> bool:
    return bool(_FORMULA_RE.search(text))


def _find_command(name: str) -> str | None:
    return shutil.which(name)


def _looks_like_cn_patent_markdown(md_text: str, input_path: str) -> bool:
    """Heuristic detection for Chinese patent-style Markdown drafts."""
    cjk_chars = len(_CJK_RE.findall(md_text))
    keyword_hits = sum(1 for kw in _CN_PATENT_HINTS if kw in md_text)
    file_name = Path(input_path).name
    has_patent_name_hint = any(token in file_name for token in ("专利", "权利要求", "说明书"))
    return (cjk_chars >= 80 and keyword_hits >= 2) or (has_patent_name_hint and cjk_chars >= 80)


def _enforce_cn_patent_pdf_policy(md_text: str, input_path: str, force_direct_pdf: bool) -> None:
    """Prefer DOCX-first workflow for Chinese patent content unless explicitly overridden."""
    if force_direct_pdf:
        return
    if not _looks_like_cn_patent_markdown(md_text, input_path):
        return

    raise RuntimeError(
        "Direct MD->PDF is disabled by default for Chinese patent drafts to reduce garbled text risk. "
        "Please convert to DOCX first and export PDF in local Word/WPS. "
        "If the user explicitly confirms direct PDF generation, rerun with --force-direct-pdf."
    )


def _read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _resolve_image_paths(html: str, base_dir: str) -> str:
    """Convert relative image paths to absolute, so temp HTML files can find them."""
    base = Path(base_dir).resolve()

    def _replace(m: re.Match) -> str:
        attr = m.group(1)
        src = m.group(2)
        if src.startswith(("http://", "https://", "data:", "file://")):
            return m.group(0)
        abs_path = (base / src).resolve()
        if abs_path.exists():
            return f'{attr}="file://{abs_path}"'
        return m.group(0)

    return re.sub(r'(src)=["\']([^"\']+)["\']', _replace, html)


def _md_to_html(md_text: str, title: str = "Document",
                css: str | None = None, include_katex: bool = False,
                base_dir: str | None = None) -> str:
    """Convert Markdown to a full HTML document with optional KaTeX support."""
    try:
        import markdown as md_lib
        body = md_lib.markdown(
            md_text,
            extensions=["tables", "fenced_code", "toc", "attr_list"],
        )
    except ImportError:
        pandoc = _find_command("pandoc")
        if pandoc:
            r = subprocess.run([pandoc, "-f", "markdown", "-t", "html"],
                               input=md_text, capture_output=True, text=True)
            body = r.stdout if r.returncode == 0 else md_text
        else:
            raise RuntimeError("Install 'markdown' (pip) or 'pandoc' for MD→HTML")

    style = css if css else DEFAULT_CSS
    katex_head = KATEX_HEAD if include_katex else ""
    katex_script = KATEX_BODY_SCRIPT if include_katex else ""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>{style}</style>
{katex_head}
</head>
<body>
{body}
{katex_script}
</body>
</html>"""

    if base_dir:
        html = _resolve_image_paths(html, base_dir)

    return html


# ---------------------------------------------------------------------------
# Engine 1: weasyprint (Python library) — no JS, no formula rendering
# ---------------------------------------------------------------------------
def _try_weasyprint(html: str, output: str, css_file: str | None = None) -> bool:
    try:
        from weasyprint import HTML
        kwargs = {}
        if css_file:
            from weasyprint import CSS
            kwargs["stylesheets"] = [CSS(filename=css_file)]
        HTML(string=html).write_pdf(output, **kwargs)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Engine 2: Playwright (Chromium) — JS support, KaTeX renders perfectly
# ---------------------------------------------------------------------------
def _try_playwright(html: str, output: str) -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False

    tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".html", mode="w",
                                         encoding="utf-8", delete=False) as f:
            f.write(html)
            tmp = f.name

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"file://{os.path.abspath(tmp)}", wait_until="networkidle")
            # Wait for KaTeX rendering if present
            page.wait_for_timeout(1000)
            page.pdf(path=output, format="A4",
                     margin={"top": "2cm", "bottom": "2cm",
                             "left": "2cm", "right": "2cm"},
                     print_background=True)
            browser.close()
        return os.path.exists(output)
    except Exception:
        return False
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


# ---------------------------------------------------------------------------
# Engine 3: pandoc + weasyprint CLI
# ---------------------------------------------------------------------------
def _try_pandoc_weasyprint(input_path: str, output: str) -> bool:
    pandoc = _find_command("pandoc")
    weasyprint_cmd = _find_command("weasyprint")
    if not pandoc or not weasyprint_cmd:
        return False
    try:
        r = subprocess.run([pandoc, input_path, "-o", output,
                            f"--pdf-engine={weasyprint_cmd}"],
                           capture_output=True, text=True)
        return r.returncode == 0 and os.path.exists(output)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Engine 4: pandoc + xelatex (best for formulas if LaTeX is installed)
# ---------------------------------------------------------------------------
def _try_pandoc_latex(input_path: str, output: str) -> bool:
    pandoc = _find_command("pandoc")
    xelatex = _find_command("xelatex")
    if not pandoc or not xelatex:
        return False
    try:
        r = subprocess.run(
            [pandoc, input_path, "-o", output,
             "--pdf-engine=xelatex",
             "-V", "CJKmainfont=PingFang SC",
             "-V", "geometry:margin=2.5cm"],
            capture_output=True, text=True)
        return r.returncode == 0 and os.path.exists(output)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Engine 5: fpdf2 — pure Python fallback (no formula/image support)
# ---------------------------------------------------------------------------
def _try_fpdf2(md_text: str, output: str) -> bool:
    try:
        from fpdf import FPDF
    except ImportError:
        return False

    font_path = _find_cjk_font()
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)

    if font_path:
        pdf.add_font("CJK", "", font_path)
        pdf.add_font("CJK", "B", font_path)
        fname = "CJK"
    else:
        fname = "Helvetica"

    pdf.add_page()
    pdf.set_font(fname, "", 10)

    for line in md_text.split("\n"):
        s = line.strip()
        if not s:
            pdf.ln(4)
        elif s.startswith("# "):
            pdf.set_font(fname, "B", 18); pdf.ln(6)
            pdf.multi_cell(0, 8, s[2:]); pdf.ln(4)
            pdf.set_font(fname, "", 10)
        elif s.startswith("## "):
            pdf.set_font(fname, "B", 14); pdf.ln(5)
            pdf.multi_cell(0, 7, s[3:]); pdf.ln(3)
            pdf.set_font(fname, "", 10)
        elif s.startswith("### "):
            pdf.set_font(fname, "B", 12); pdf.ln(4)
            pdf.multi_cell(0, 6, s[4:]); pdf.ln(2)
            pdf.set_font(fname, "", 10)
        elif s.startswith(("- ", "* ")):
            pdf.cell(5); pdf.multi_cell(0, 5, f"• {s[2:]}"); pdf.ln(1)
        elif s.startswith("---"):
            pdf.ln(4)
        else:
            pdf.multi_cell(0, 5, s); pdf.ln(1)

    pdf.output(output)
    return True


def _find_cjk_font() -> str | None:
    import platform
    system = platform.system()
    candidates = {
        "Darwin": [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
        ],
        "Windows": [
            os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", f)
            for f in ("msyh.ttc", "simhei.ttf", "simsun.ttc")
        ],
    }.get(system, [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    ])
    return next((p for p in candidates if os.path.exists(p)), None)


# ---------------------------------------------------------------------------
# Main conversion logic
# ---------------------------------------------------------------------------
def convert(input_path: str, output_path: str, css: str | None = None, force_direct_pdf: bool = False) -> str:
    """Convert input_path to PDF at output_path. Returns the engine name used."""
    suffix = Path(input_path).suffix.lower()
    base_dir = str(Path(input_path).parent.resolve())

    # DOCX → PDF
    if suffix == ".docx":
        if _try_pandoc_weasyprint(input_path, output_path):
            return "pandoc+weasyprint"
        if _try_pandoc_latex(input_path, output_path):
            return "pandoc+xelatex"
        soffice = _find_command("soffice") or _find_command("libreoffice")
        if soffice:
            out_dir = str(Path(output_path).parent)
            subprocess.run([soffice, "--headless", "--convert-to", "pdf",
                            "--outdir", out_dir, input_path], check=True)
            gen = Path(input_path).with_suffix(".pdf")
            if gen.exists() and str(gen) != output_path:
                shutil.move(str(gen), output_path)
            return "libreoffice"
        raise RuntimeError("No DOCX→PDF engine. Install pandoc+weasyprint or LibreOffice.")

    # HTML → PDF
    if suffix in (".html", ".htm"):
        html = _read_file(input_path)
        html = _resolve_image_paths(html, base_dir)
        if _has_formulas(html):
            if _try_playwright(html, output_path):
                return "playwright"
        if _try_weasyprint(html, output_path, css):
            return "weasyprint"
        if _try_playwright(html, output_path):
            return "playwright"
        if _try_pandoc_weasyprint(input_path, output_path):
            return "pandoc+weasyprint"
        raise RuntimeError("No HTML→PDF engine. Install weasyprint or playwright.")

    # MD → PDF
    md_text = _read_file(input_path)
    _enforce_cn_patent_pdf_policy(md_text, input_path, force_direct_pdf)
    has_math = _has_formulas(md_text)
    custom_css = _read_file(css) if css else None

    # When formulas are present, Playwright is preferred (KaTeX needs JS).
    # When no formulas, weasyprint gives better CSS-based print output.

    if has_math:
        html_katex = _md_to_html(md_text, title=Path(input_path).stem,
                                 css=custom_css, include_katex=True,
                                 base_dir=base_dir)
        if _try_playwright(html_katex, output_path):
            return "playwright"

    html_plain = _md_to_html(md_text, title=Path(input_path).stem,
                             css=custom_css, include_katex=False,
                             base_dir=base_dir)

    if _try_weasyprint(html_plain, output_path, css):
        return "weasyprint"

    if not has_math:
        if _try_playwright(html_plain, output_path):
            return "playwright"

    with tempfile.NamedTemporaryFile(suffix=".html", mode="w",
                                     encoding="utf-8", delete=False) as f:
        f.write(html_plain)
        tmp = f.name
    try:
        if _try_pandoc_weasyprint(tmp, output_path):
            return "pandoc+weasyprint"
    finally:
        os.unlink(tmp)

    if _try_pandoc_latex(input_path, output_path):
        return "pandoc+xelatex"

    if _try_fpdf2(md_text, output_path):
        print("Note: used fpdf2 fallback. For better quality, install weasyprint or playwright.",
              file=sys.stderr)
        return "fpdf2"

    raise RuntimeError(
        "No PDF engine available. Install one of:\n"
        "  pip install weasyprint   (Mac/Linux: brew install weasyprint)\n"
        "  pip install playwright && playwright install chromium   (Win recommended)\n"
        "  pip install fpdf2        (basic fallback)"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Cross-platform document to PDF converter")
    parser.add_argument("input", help="Input file (.md, .html, .docx)")
    parser.add_argument("-o", "--output", help="Output PDF path")
    parser.add_argument("--css", help="Custom CSS stylesheet path")
    parser.add_argument(
        "--force-direct-pdf",
        action="store_true",
        help="Bypass the Chinese patent DOCX-first safeguard and force direct MD->PDF.",
    )
    args = parser.parse_args()

    if not args.output:
        args.output = str(Path(args.input).with_suffix(".pdf"))

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    engine = convert(args.input, args.output, css=args.css, force_direct_pdf=args.force_direct_pdf)
    size = os.path.getsize(args.output)
    print(f"PDF generated: {args.output} ({size:,} bytes) [engine: {engine}]")


if __name__ == "__main__":
    main()
