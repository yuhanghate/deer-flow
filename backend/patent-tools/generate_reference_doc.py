#!/usr/bin/env python3
"""Generate a CJK-friendly pandoc reference.docx for Chinese patent documents.

Usage:
    python generate_reference_doc.py
    # Outputs: patent-reference.docx in the same directory as this script.

Creates a Word template with CJK font fallbacks (SimSun, PingFang SC,
Microsoft YaHei) so pandoc produces properly styled Chinese documents.
"""
from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PANDOC_DEFAULT = Path("/tmp/default-reference.docx")
OUTPUT = SCRIPT_DIR / "patent_tools" / "resources" / "patent-reference.docx"

# CJK font fallback chain — tried in order, first installed font wins
CJK_FONT = "SimSun, PingFang SC, Microsoft YaHei, Noto Sans CJK SC, sans-serif"
CJK_HEADING = "SimHei, PingFang SC, Microsoft YaHei, Noto Sans CJK SC, sans-serif"


def _add_font_fallback(xml: str, font_family: str, font_heading: str) -> str:
    """Inject ``w:eastAsia`` font attributes into key Word styles."""
    # We use a targeted replacement approach on the styles XML.
    # For the Normal style, add rFonts with eastAsia fallback.
    # For heading styles, add heading-specific font settings.

    # Add a w:style for CJK fonts at the document level
    # We'll inject <w:rFonts w:ascii="..." w:hAnsi="..." w:eastAsia="..."/>
    # into the run properties of key styles.

    import re

    # Find <w:style w:type="paragraph" w:styleId="Normal"> block
    # and inject <w:rFonts> into its <w:rPr>

    def _inject_rfonts(match: re.Match, fonts: str) -> str:
        full = match.group(0)
        if '<w:rFonts' in full:
            return full  # already has rFonts
        # Insert before closing </w:rPr>
        closing = '</w:rPr>'
        rfonts = (
            f'<w:rFonts w:ascii="{fonts}" '
            f'w:hAnsi="{fonts}" '
            f'w:cs="{fonts}" '
            f'w:eastAsia="{fonts}"/>'
        )
        return full.replace(closing, rfonts + '\n        ' + closing)

    # Inject into Normal style's rPr
    xml = re.sub(
        r'(<w:style w:type="paragraph" w:styleId="Normal".*?<w:rPr>.*?</w:rPr>)',
        lambda m: _inject_rfonts(m, font_family),
        xml, flags=re.DOTALL,
    )

    # Inject into heading styles (Heading1, Heading2, Heading3)
    for heading_id in ("Heading1", "Heading2", "Heading3"):
        xml = re.sub(
            rf'(<w:style w:type="paragraph" w:styleId="{heading_id}".*?<w:rPr>.*?</w:rPr>)',
            lambda m: _inject_rfonts(m, font_heading),
            xml, flags=re.DOTALL,
        )

    return xml


def main() -> None:
    if not PANDOC_DEFAULT.exists():
        print(f"Pandoc default reference.docx not found at {PANDOC_DEFAULT}")
        print("Run: pandoc -o /tmp/default-reference.docx --print-default-data-file reference.docx")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Extract pandoc's default reference.docx
        with zipfile.ZipFile(PANDOC_DEFAULT, 'r') as zf:
            zf.extractall(tmp)

        # Modify styles.xml
        styles_path = tmp / "word" / "styles.xml"
        if styles_path.exists():
            xml = styles_path.read_text(encoding="utf-8")
            xml = _add_font_fallback(xml, CJK_FONT, CJK_HEADING)
            styles_path.write_text(xml, encoding="utf-8")

        # Repack as .docx
        with zipfile.ZipFile(OUTPUT, 'w', zipfile.ZIP_DEFLATED) as zf:
            for f in tmp.rglob("*"):
                if f.is_file():
                    arcname = f.relative_to(tmp)
                    zf.write(f, arcname)

    print(f"Created: {OUTPUT}")
    print(f"  CJK body font: {CJK_FONT}")
    print(f"  CJK heading font: {CJK_HEADING}")


if __name__ == "__main__":
    main()
