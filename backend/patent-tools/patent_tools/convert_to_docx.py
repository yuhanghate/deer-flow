from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Annotated

from langchain.tools import InjectedToolCallId, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.config import get_config
from langgraph.types import Command
from langgraph.typing import ContextT

from deerflow.agents.thread_state import ThreadState
from deerflow.config.paths import VIRTUAL_PATH_PREFIX, get_paths

from .markdown_processor import preprocess_markdown_to_html
from .output_versioning import resolve_unique_versioned_filename, strip_trailing_v_suffix

_INVALID_CHARS = re.compile(r'[\\/:*?"<>|]+')
_ALLOWED_MARKDOWN_EXTS = {".md", ".markdown"}
_MAX_ERROR_CHARS = 1200

# Location of the patent reference template for pandoc styling
_RESOURCES_DIR = Path(__file__).parent / "resources"
_PATENT_REFERENCE_DOC = _RESOURCES_DIR / "patent-reference.docx"


def _sanitize_filename(filename: str) -> str:
    cleaned = _INVALID_CHARS.sub("_", filename).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned


def _get_thread_id(runtime: ToolRuntime[ContextT, ThreadState]) -> str | None:
    thread_id = runtime.context.get("thread_id") if runtime.context else None
    if thread_id:
        return thread_id

    runtime_config = getattr(runtime, "config", None) or {}
    thread_id = runtime_config.get("configurable", {}).get("thread_id")
    if thread_id:
        return thread_id

    try:
        return get_config().get("configurable", {}).get("thread_id")
    except RuntimeError:
        return None


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _resolve_source_path(runtime: ToolRuntime[ContextT, ThreadState], source_filepath: str) -> Path:
    if runtime.state is None:
        raise ValueError("Thread runtime state is not available")

    thread_data = runtime.state.get("thread_data") or {}
    workspace_path = thread_data.get("workspace_path")
    uploads_path = thread_data.get("uploads_path")
    outputs_path = thread_data.get("outputs_path")
    if not outputs_path:
        raise ValueError("Thread outputs path is not available in runtime state")

    thread_id = _get_thread_id(runtime)
    if not thread_id:
        raise ValueError("Thread ID is not available in runtime context or runtime config")

    stripped = source_filepath.lstrip("/")
    virtual_prefix = VIRTUAL_PATH_PREFIX.lstrip("/")
    if stripped == virtual_prefix or stripped.startswith(virtual_prefix + "/"):
        source_path = get_paths().resolve_virtual_path(thread_id, source_filepath)
    else:
        source_path = Path(source_filepath).expanduser().resolve()

    source_path = source_path.resolve()
    allowed_roots = [Path(p).resolve() for p in (workspace_path, uploads_path, outputs_path) if p]
    if not allowed_roots:
        raise ValueError("Thread directories are not available in runtime state")

    if not any(_is_relative_to(source_path, root) for root in allowed_roots):
        raise ValueError(f"Only files in {VIRTUAL_PATH_PREFIX} can be converted: {source_filepath}")
    if not source_path.exists() or not source_path.is_file():
        raise ValueError(f"Source file not found: {source_filepath}")
    if source_path.suffix.lower() not in _ALLOWED_MARKDOWN_EXTS:
        allowed = ", ".join(sorted(_ALLOWED_MARKDOWN_EXTS))
        raise ValueError(f"Source must be a Markdown file ({allowed}): {source_filepath}")
    return source_path


def _docx_base_stem(output_filename: str, source_path: Path) -> str:
    """Derive a safe base stem; strip prior ``_v2.0`` / ``_v20260420…`` style suffixes."""
    if output_filename.strip():
        raw = _sanitize_filename(output_filename.strip())
        if not raw:
            raise ValueError("output_filename is invalid after sanitization")
        stem = Path(raw).stem if raw.lower().endswith(".docx") else raw
    else:
        stem = source_path.stem
    stem = strip_trailing_v_suffix(stem) or stem
    stem = _sanitize_filename(stem)
    if not stem:
        stem = _sanitize_filename(source_path.stem) or "output"
    return stem


def _convert_html_to_docx(
    html_content: str, target_path: Path, reference_doc: Path | None = None
) -> tuple[bool, str]:
    """Convert HTML content to DOCX via pandoc."""
    tmp_path = Path(tempfile.mktemp(suffix=".html"))
    tmp_path.write_text(html_content, encoding="utf-8")
    try:
        cmd = ["pandoc", "-f", "html", "-t", "docx", str(tmp_path), "-o", str(target_path)]
        if reference_doc:
            cmd.extend(["--reference-doc", str(reference_doc)])
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            return True, ""
        message = (result.stderr or result.stdout or "pandoc failed with unknown error").strip()
        return False, message[:_MAX_ERROR_CHARS]
    finally:
        tmp_path.unlink(missing_ok=True)


@tool("convert_markdown_to_docx", parse_docstring=True)
def convert_markdown_to_docx_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    source_filepath: str,
    output_filename: str = "",
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> Command:
    """Convert a Markdown draft into a DOCX file in `/mnt/user-data/outputs`.

    Use this tool instead of manually running ``pandoc`` in bash when you need a
    Word deliverable from a Markdown draft.

    Chemical formulas (e.g. ``Nd₂Fe₁₄B``, ``10^{-3}``) are converted to native
    Word subscript / superscript formatting via an HTML intermediate.

    Args:
        source_filepath: Absolute path of the Markdown source file.
        output_filename: Optional logical name (with or without ``.docx``); the saved
            file is always ``vYYYYMMDDHHMM_{name}.docx`` under outputs.
    """
    try:
        if runtime.state is None:
            raise ValueError("Thread runtime state is not available")

        thread_data = runtime.state.get("thread_data") or {}
        outputs_path = thread_data.get("outputs_path")
        if not outputs_path:
            raise ValueError("Thread outputs path is not available in runtime state")

        source_path = _resolve_source_path(runtime, source_filepath)
        outputs_dir = Path(outputs_path).resolve()
        outputs_dir.mkdir(parents=True, exist_ok=True)
        base_stem = _docx_base_stem(output_filename, source_path)
        target_name = resolve_unique_versioned_filename(outputs_dir, base_stem, ".docx")
        target_path = outputs_dir / target_name

        # Pre-process: Markdown → HTML with <sub>/<sup> for chemical formulas
        content = source_path.read_text(encoding="utf-8")
        html = preprocess_markdown_to_html(content)

        # Convert HTML → DOCX with reference template
        reference_doc = _PATENT_REFERENCE_DOC if _PATENT_REFERENCE_DOC.exists() else None
        ok, error_message = _convert_html_to_docx(html, target_path, reference_doc=reference_doc)
        if not ok:
            raise ValueError(
                "Failed to convert Markdown to DOCX via pandoc. "
                f"source={source_path.name}, target={target_path.name}, error={error_message}"
            )

        artifact_path = f"{VIRTUAL_PATH_PREFIX}/outputs/{target_path.name}"
        return Command(
            update={
                "artifacts": [artifact_path],
                "messages": [
                    ToolMessage(
                        f"Converted Markdown to DOCX: {artifact_path}",
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )
    except ValueError as exc:
        return Command(
            update={
                "messages": [ToolMessage(f"Error: {exc}", tool_call_id=tool_call_id)],
            }
        )
