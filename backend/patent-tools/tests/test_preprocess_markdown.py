"""Tests for Markdown preprocessing in patent-tools.

Tests the two-pass pipeline: Markdown -> HTML -> <sub>/<sup> injection.
"""

from patent_tools.markdown_processor import (
    auto_add_headings,
    preprocess_markdown_to_html,
)


# ── Unicode subscript digits → <sub> ───────────────────────────────────────


def test_unicode_subscript_single():
    result = preprocess_markdown_to_html("CO₂")
    assert "<sub>2</sub>" in result


def test_unicode_subscript_multi():
    result = preprocess_markdown_to_html("Nd₂Fe₁₄B")
    assert "<sub>2</sub>" in result
    assert "<sub>14</sub>" in result


def test_unicode_subscript_multiple_in_text():
    result = preprocess_markdown_to_html("Nd₂Fe₁₄B 与 Nd₂O₃ 的混合物")
    assert "<sub>2</sub>" in result
    assert "<sub>14</sub>" in result
    assert "<sub>3</sub>" in result


def test_unicode_subscript_digit_9():
    """Ensure ₉ (U+2089) is covered."""
    result = preprocess_markdown_to_html("C₉H₈O₄")
    assert "<sub>9</sub>" in result
    assert "<sub>8</sub>" in result
    assert "<sub>4</sub>" in result


def test_unicode_subscript_no_subscripts():
    result = preprocess_markdown_to_html("正常文本无下标")
    assert "<sub>" not in result


# ── Digit-preceded subscripts NOT converted (LLM artifact) ─────────────────
# These look like subscripts but appear after digits, not letters.
# They should remain as Unicode characters, NOT become <sub>.


def test_digit_preceded_subscript_not_converted():
    """5₂₀°C should NOT become 5<sub>20</sub>°C (LLM artifact)."""
    result = preprocess_markdown_to_html("5₂₀°C")
    assert "<sub>" not in result


def test_digit_preceded_subscript_in_mixed_text():
    """20₅₀ppm should NOT become 20<sub>50</sub>ppm."""
    result = preprocess_markdown_to_html("20₅₀ppm")
    assert "<sub>" not in result


def test_letter_preceded_subscript_still_converts():
    """Nd₂ should convert even when digit-preceded subscripts exist nearby."""
    result = preprocess_markdown_to_html("Nd₂Fe₁₄B and 5₂₀°C")
    assert "<sub>2</sub>" in result
    assert "<sub>14</sub>" in result
    # 5₂₀ should NOT be converted
    assert "<sub>20</sub>" not in result


def test_subscript_at_start_of_text_not_converted():
    """₂₀ at start of text has no preceding letter, should not convert."""
    result = preprocess_markdown_to_html("₂₀ items")
    assert "<sub>" not in result


# ── Unicode subscript letters → <sub> ──────────────────────────────────────


def test_subscript_letters():
    result = preprocess_markdown_to_html("REₐBᵦMFe")
    assert "<sub>a</sub>" in result
    assert "<sub>b</sub>" in result


def test_subscript_letters_no_change():
    result = preprocess_markdown_to_html("正常文本")
    assert "<sub>" not in result


# ── Underscore subscript notation → <sub> ──────────────────────────────────


def test_underscore_brace_subscript():
    result = preprocess_markdown_to_html("Fe_{14}")
    assert "<sub>14</sub>" in result


def test_underscore_multiple_brace():
    result = preprocess_markdown_to_html("Nd_{2}Fe_{14}B")
    assert "<sub>2</sub>" in result
    assert "<sub>14</sub>" in result


def test_underscore_single_char():
    result = preprocess_markdown_to_html("RE_aB_bM")
    assert "<sub>a</sub>" in result
    assert "<sub>b</sub>" in result


def test_underscore_complex_formula():
    result = preprocess_markdown_to_html("RE_aB_bM_cFe_{100-(a+b+c)}")
    assert "<sub>a</sub>" in result
    assert "<sub>b</sub>" in result
    assert "<sub>c</sub>" in result
    assert "<sub>100-(a+b+c)</sub>" in result


def test_underscore_does_not_affect_emphasis():
    """_Fe_ (markdown emphasis) should not become <sub>."""
    result = preprocess_markdown_to_html("_Fe_ is italic")
    # Emphasis stays as emphasis, not <sub>
    assert "Fe" in result


# ── Caret superscript notation → <sup> ─────────────────────────────────────


def test_caret_superscript():
    result = preprocess_markdown_to_html("10^{-3}")
    assert "<sup>-3</sup>" in result


def test_caret_superscript_in_context():
    result = preprocess_markdown_to_html("5×10^{-2}Pa")
    assert "<sup>-2</sup>" in result


def test_caret_superscript_positive():
    result = preprocess_markdown_to_html("10^{+3}")
    assert "<sup>+3</sup>" in result


# ── Range tilde preservation ───────────────────────────────────────────────


def test_range_tilde_preserved():
    """500~1400ppm should keep the tilde, NOT become subscript."""
    result = preprocess_markdown_to_html("500~1400ppm")
    assert "~" in result
    assert "<sub>" not in result


def test_range_tilde_with_superscripts():
    """10^{-3}~5×10^{-2}Pa: superscripts converted, tilde preserved."""
    result = preprocess_markdown_to_html("10^{-3}~5×10^{-2}Pa")
    assert "<sup>-3</sup>" in result
    assert "<sup>-2</sup>" in result
    assert "~" in result


# ── Heading injection ──────────────────────────────────────────────────────


def test_heading_adds_h1_to_sections():
    content = """一种测试方法

1. 技术领域
本发明涉及...

2. 背景技术
背景内容。"""
    result = auto_add_headings(content)
    assert "# 1. 技术领域" in result
    assert "# 2. 背景技术" in result
    assert "# 一种测试方法" in result


def test_heading_adds_h2_to_examples():
    content = """1. 技术领域
测试。

实施例1：
具体步骤。

对比例2：
对照实验。"""
    result = auto_add_headings(content)
    assert "## 实施例1：" in result
    assert "## 对比例2：" in result


def test_heading_preserves_existing():
    content = """# 已有标题

## 3.1 技术方案
内容。"""
    result = auto_add_headings(content)
    assert "# 已有标题" in result
    assert "## 3.1 技术方案" in result


def test_heading_claims_section():
    content = """摘要
测试摘要。

6. 权利要求书
1. 一种..."""
    result = auto_add_headings(content)
    assert "# 6. 权利要求书" in result


def test_heading_claims_without_number():
    content = """摘要
测试。

权利要求书
1. 一种..."""
    result = auto_add_headings(content)
    assert "# 权利要求书" in result


# ── Full pipeline integration ─────────────────────────────────────────────


def test_full_pipeline():
    """End-to-end: mixed Unicode, underscore, caret, headings, range tilde."""
    content = """一种基于 Nd₂Fe₁₄B 的磁体

1. 技术领域
涉及 Nd₂O₃ 材料和 RE_aB_bM_cFe_{100-(a+b+c)}。

实施例1：
CO₂ 测试。真空度 10^{-3}~5×10^{-2}Pa。范围 500~1400ppm。"""
    result = preprocess_markdown_to_html(content)

    # Subscripts from Unicode
    assert "<sub>2</sub>" in result
    assert "<sub>14</sub>" in result
    assert "<sub>3</sub>" in result

    # Subscripts from underscore notation
    assert "<sub>a</sub>" in result
    assert "<sub>100-(a+b+c)</sub>" in result

    # Superscripts from caret notation
    assert "<sup>-3</sup>" in result
    assert "<sup>-2</sup>" in result

    # Headings
    assert "1. 技术领域" in result
    assert "<h1" in result

    # Range tilde preserved
    assert "~" in result


def test_full_pipeline_with_false_positives():
    """Correct conversions alongside non-conversions in same text."""
    content = "真空度 10^{-3}~5×10^{-2}Pa。范围 500~1400ppm。Nd₂Fe₁₄B。5₂₀°C。"
    result = preprocess_markdown_to_html(content)

    # Superscripts from caret notation
    assert "<sup>-3</sup>" in result
    assert "<sup>-2</sup>" in result

    # Subscripts from Unicode (after letters)
    assert "<sub>2</sub>" in result
    assert "<sub>14</sub>" in result

    # Non-subscripts (digit-preceded) should NOT have <sub>
    assert "<sub>20</sub>" not in result

    # Tilde preserved
    assert "~" in result


def test_preprocess_latex_math():
    """LLM output with LaTeX-style math."""
    result = preprocess_markdown_to_html("真空度为 1 × 10^{-3}~5×10^{-2}Pa。")
    assert "<sup>-3</sup>" in result
    assert "<sup>-2</sup>" in result
    assert "~" in result


def test_preprocess_subscript_letters_in_pipeline():
    """Unicode subscript letters → <sub>."""
    result = preprocess_markdown_to_html("化学式 REₐBᵦM꜀Fe")
    assert "<sub>a</sub>" in result
    assert "<sub>b</sub>" in result
    assert "<sub>c</sub>" in result


def test_mixed_unicode_and_underscore():
    """Both Unicode subscripts and underscore notation in same formula."""
    result = preprocess_markdown_to_html("Nd₂Fe_{14}B")
    # Unicode ₂ → <sub>2</sub>, underscore _{14} → <sub>14</sub>
    assert result.count("<sub>2</sub>") >= 1
    assert result.count("<sub>14</sub>") >= 1


# ── Markdown tables → HTML <table> ─────────────────────────────────────────


def test_pipe_table_rendered_as_html_table():
    """Markdown pipe tables should become <table> elements, not plain text."""
    content = """| 组别 | 参数 | 结果 |
|------|------|------|
| A | 100 | 99.0 |
| B | 200 | 98.5 |"""
    result = preprocess_markdown_to_html(content)
    assert "<table>" in result
    assert "<thead>" in result
    assert "<tbody>" in result
    assert "| 组别 |" not in result


def test_table_with_subscript_content():
    """Tables containing chemical formulas should preserve both table and subscripts."""
    content = """| 材料 | 化学式 |
|------|--------|
| 磁体 | Nd₂Fe₁₄B |
| 氧化物 | CO₂ |"""
    result = preprocess_markdown_to_html(content)
    assert "<table>" in result
    assert "<sub>2</sub>" in result
    assert "<sub>14</sub>" in result

