---
name: doc-convert
description: "Convert documents between formats — Markdown to Word, Markdown to PDF, HTML to PDF, Word to PDF, or any combination. Use this skill whenever the user mentions converting, exporting, or generating documents in a different format. Trigger phrases include: '转成PDF', '转成Word', '导出', '生成PDF', '生成Word文档', 'convert to PDF', 'export as docx', 'make a PDF', 'save as Word'. Also trigger when the user has a Markdown file and asks for a downloadable PDF or Word version, even if they don't explicitly say 'convert'. If the user says something like '帮我生成一份PDF' or 'can I get a Word doc of this', use this skill. Handles chemical formulas, math equations, images, and technical diagrams. Do NOT trigger for creating documents from scratch (use docx/pptx skills instead) — this skill is specifically for FORMAT CONVERSION of existing content."
---

# Document Format Conversion

This skill exists because document conversion is a common, repetitive task that should take seconds, not minutes. The bundled scripts handle cross-platform font detection, engine fallback, formula rendering, and CJK support so you don't have to reinvent them every time.

## Quick Reference

| Conversion | Command |
|------------|---------|
| MD → Word (preferred) | Use tool `convert_markdown_to_docx(source_filepath, output_filename)` |
| MD → Word (fallback only) | `pandoc input.md -o output.docx` |
| MD → PDF | `python scripts/md2pdf.py input.md -o output.pdf` |
| MD → PDF (explicit override for CN patent drafts) | `python scripts/md2pdf.py input.md -o output.pdf --force-direct-pdf` |
| HTML → PDF | `python scripts/md2pdf.py input.html -o output.pdf` |
| Word → PDF | `python scripts/md2pdf.py input.docx -o output.pdf` |

The `scripts/` path is relative to this skill's directory.

## Recommended Strategy for Chinese Patent Docs

For Chinese-heavy patent content (chemistry/materials/mechanical/electrical), prefer:

1. `MD -> DOCX` (default deliverable)
2. If PDF is needed, ask user to export from local Word/WPS (`另存为 PDF`)

Reason: this path is faster for daily use and has the highest Chinese glyph compatibility on ordinary office computers.

When the input looks like a Chinese patent draft, `md2pdf.py` now blocks direct MD→PDF by default and prints a DOCX-first message. Only use `--force-direct-pdf` when the user explicitly insists on direct PDF generation.

## MD → Word

Default flow (no command line shown to users): call built-in tool first.

1. Use `convert_markdown_to_docx` tool.
2. If the tool is unavailable in current runtime, only then fallback to pandoc command.

Fallback command:

```bash
pandoc input.md -o output.docx
```

With a custom reference template for branded styling:
```bash
pandoc input.md -o output.docx --reference-doc=template.docx
```

pandoc is pre-installed. If missing: `brew install pandoc` (Mac), `winget install JohnMacFarlane.Pandoc` (Win), `apt install pandoc` (Linux).

## MD / HTML / DOCX → PDF

Use the bundled converter script. It auto-detects the best available engine:

```bash
python scripts/md2pdf.py input.md -o output.pdf
python scripts/md2pdf.py input.html -o output.pdf
python scripts/md2pdf.py input.docx -o output.pdf
```

Optional custom CSS:
```bash
python scripts/md2pdf.py input.md -o output.pdf --css custom.css
```

### Chemical Formulas & Math Equations

The script automatically detects LaTeX formulas ($...$, $$...$$) and uses KaTeX with Chromium (Playwright) to render them. Users can write:

- Inline: `$\text{H}_2\text{SO}_4$` or `$\ce{H2SO4}$` (mhchem syntax)
- Display: `$$\ce{2H2 + O2 -> 2H2O}$$`
- General math: `$E = mc^2$`

When formulas are detected, Playwright is automatically preferred over other engines because it's the only one that supports JavaScript-based rendering.

### Images

Images referenced in Markdown are automatically resolved. Use standard syntax:

```markdown
![图1 反应器结构](./images/reactor.png)
```

Relative paths are converted to absolute paths during conversion, so images work regardless of which engine is selected.

### How the script chooses an engine

The script tries engines in quality order and uses the first one that works:

**When formulas are present:**
1. Playwright (Chromium + KaTeX) → best for formulas
2. weasyprint → no formula support, but good CSS
3. pandoc+xelatex → native LaTeX formula support
4. fpdf2 → basic fallback

**When no formulas:**
1. weasyprint → best CSS-based print quality
2. Playwright → good quality, heavier
3. pandoc+weasyprint / pandoc+xelatex
4. fpdf2 → basic fallback

### Platform-specific engine recommendations

- **Mac**: `brew install weasyprint` (best quality)
- **Windows**: `pip install playwright && playwright install chromium` (best cross-platform)
- **Linux**: `apt install weasyprint` or `pip install playwright && playwright install chromium`

## Important

- Output files should always go to `/mnt/user-data/outputs/`
- Chinese/CJK PDF rendering depends on available fonts and engine path; if direct PDF has garbled Chinese, switch to `MD -> DOCX` and export PDF in local Word/WPS
- Do NOT write custom conversion code — always use the commands above
