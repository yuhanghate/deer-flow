"""Middleware to inject uploaded files information into agent context."""

import logging
from pathlib import Path
from typing import NotRequired, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime

from deerflow.config.paths import Paths, get_paths
from deerflow.utils.file_conversion import CONVERTIBLE_EXTENSIONS, extract_outline

logger = logging.getLogger(__name__)


_OUTLINE_PREVIEW_LINES = 5


def _extract_outline_for_file(file_path: Path) -> tuple[list[dict], list[str]]:
    """Return the document outline and fallback preview for *file_path*.

    Looks for a sibling ``<stem>.md`` file produced by the upload conversion
    pipeline.

    Returns:
        (outline, preview) where:
        - outline: list of ``{title, line}`` dicts (plus optional sentinel).
          Empty when no headings are found or no .md exists.
        - preview: first few non-empty lines of the .md, used as a content
          anchor when outline is empty so the agent has some context.
          Empty when outline is non-empty (no fallback needed).
    """
    md_path = file_path.with_suffix(".md")
    if not md_path.is_file():
        return [], []

    outline = extract_outline(md_path)
    if outline:
        logger.debug("Extracted %d outline entries from %s", len(outline), file_path.name)
        return outline, []

    # outline is empty — read the first few non-empty lines as a content preview
    preview: list[str] = []
    try:
        with md_path.open(encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    preview.append(stripped)
                if len(preview) >= _OUTLINE_PREVIEW_LINES:
                    break
    except Exception:
        logger.debug("Failed to read preview lines from %s", md_path, exc_info=True)
    return [], preview


class UploadsMiddlewareState(AgentState):
    """State schema for uploads middleware."""

    uploaded_files: NotRequired[list[dict] | None]


class UploadsMiddleware(AgentMiddleware[UploadsMiddlewareState]):
    """Middleware to inject uploaded files information into the agent context.

    Reads file metadata from the current message's additional_kwargs.files
    (set by the frontend after upload) and prepends an <uploaded_files> block
    to the last human message so the model knows which files are available.
    """

    state_schema = UploadsMiddlewareState

    def __init__(self, base_dir: str | None = None):
        """Initialize the middleware.

        Args:
            base_dir: Base directory for thread data. Defaults to Paths resolution.
        """
        super().__init__()
        self._paths = Paths(base_dir) if base_dir else get_paths()

    def _format_file_entry(self, file: dict, lines: list[str], uploads_dir: Path | None = None) -> None:
        """Append a single file entry (name, size, path, optional outline) to lines."""
        size_kb = file["size"] / 1024
        size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb / 1024:.1f} MB"
        lines.append(f"- {file['filename']} ({size_str})")
        lines.append(f"  Path: {file['path']}")
        if uploads_dir is not None:
            md_sibling = uploads_dir / Path(file["filename"]).with_suffix(".md").name
            if md_sibling.is_file() and md_sibling.name != file["filename"]:
                lines.append(
                    f"  Converted Markdown (prefer read_file on this path): "
                    f"Path: /mnt/user-data/uploads/{md_sibling.name}"
                )
            elif Path(file["filename"]).suffix.lower() in CONVERTIBLE_EXTENSIONS:
                ext = Path(file["filename"]).suffix.lower()
                if ext == ".doc":
                    lines.append(
                        "  【给用户的说明（请原样转告或展示）】本文件为旧版 Word 二进制格式（.doc），"
                        "服务端未能生成可读的 Markdown（.md）。请勿安装 antiword/LibreOffice 等在对话里硬解析。"
                        "请在本机用 Microsoft Word 或 WPS 打开该文件，使用「另存为」保存为 **.docx**；"
                        "或导出为 **.txt** / **.md** 后，在本对话中重新上传。上传后若已开启 "
                        "`uploads.auto_convert_documents`，应出现同名 `.md` 再让助手阅读。"
                    )
                    lines.append(
                        "  【助手行为】不得使用 bash 调用 antiword/catdoc/soffice/olefile/strings 解析该 .doc；"
                        "直接向用户说明上一段方案。若用户已重新上传 .docx，优先 read_file 其同名 .md。"
                    )
                else:
                    lines.append(
                        "  【给用户的说明（请原样转告或展示）】未检测到本 Office 文件对应的自动转换结果（.md）。"
                        "请确认部署已在 config.yaml 中开启 `uploads.auto_convert_documents: true` 并已重启服务，"
                        "然后删除旧附件、重新上传；若仍无 .md，可将内容另存为 .docx 或导出 .txt 再传，"
                        "或缩小文件体积后重试，并请管理员查看网关日志中 `Failed to convert` 相关 ERROR。"
                    )
                    lines.append(
                        "  【助手行为】不得用 bash 自行安装解析库或调用 LibreOffice 解析二进制原件；"
                        "先向用户说明上一段，再等待用户重新上传可转换格式。"
                    )
        outline = file.get("outline") or []
        if outline:
            truncated = outline[-1].get("truncated", False)
            visible = [e for e in outline if not e.get("truncated")]
            lines.append("  Document outline (use `read_file` with line ranges to read sections):")
            for entry in visible:
                lines.append(f"    L{entry['line']}: {entry['title']}")
            if truncated:
                lines.append(f"    ... (showing first {len(visible)} headings; use `read_file` to explore further)")
        else:
            preview = file.get("outline_preview") or []
            if preview:
                lines.append("  No structural headings detected. Document begins with:")
                for text in preview:
                    lines.append(f"    > {text}")
            lines.append("  Use `grep` to search for keywords (e.g. `grep(pattern='keyword', path='/mnt/user-data/uploads/')`).")
        lines.append("")

    def _create_files_message(
        self, new_files: list[dict], historical_files: list[dict], uploads_dir: Path | None
    ) -> str:
        """Create a formatted message listing uploaded files.

        Args:
            new_files: Files uploaded in the current message.
            historical_files: Files uploaded in previous messages.
                Each file dict may contain an optional ``outline`` key — a list of
                ``{title, line}`` dicts extracted from the converted Markdown file.

        Returns:
            Formatted string inside <uploaded_files> tags.
        """
        lines = ["<uploaded_files>"]

        lines.append("The following files were uploaded in this message:")
        lines.append("")
        if new_files:
            for file in new_files:
                self._format_file_entry(file, lines, uploads_dir)
        else:
            lines.append("(empty)")
            lines.append("")

        if historical_files:
            lines.append("The following files were uploaded in previous messages and are still available:")
            lines.append("")
            for file in historical_files:
                self._format_file_entry(file, lines, uploads_dir)

        lines.append("To work with these files:")
        lines.append(
            "- For Office uploads, if a \"Converted Markdown\" path is shown above, use `read_file` on that `.md` "
            "first — do not use bash, antiword, LibreOffice, or ad-hoc Python to parse the binary original."
        )
        lines.append("- Otherwise read from the file first — use the outline line numbers and `read_file` to locate relevant sections.")
        lines.append("- Use `grep` to search for keywords when you are not sure which section to look at")
        lines.append("  (e.g. `grep(pattern='revenue', path='/mnt/user-data/uploads/')`).")
        lines.append("- Use `glob` to find files by name pattern")
        lines.append("  (e.g. `glob(pattern='**/*.md', path='/mnt/user-data/uploads/')`).")
        lines.append("- Only fall back to web search if the file content is clearly insufficient to answer the question.")
        lines.append("</uploaded_files>")

        return "\n".join(lines)

    def _files_from_kwargs(self, message: HumanMessage, uploads_dir: Path | None = None) -> list[dict] | None:
        """Extract file info from message additional_kwargs.files.

        The frontend sends uploaded file metadata in additional_kwargs.files
        after a successful upload. Each entry has: filename, size (bytes),
        path (virtual path), status.

        Args:
            message: The human message to inspect.
            uploads_dir: Physical uploads directory used to verify file existence.
                         When provided, entries whose files no longer exist are skipped.

        Returns:
            List of file dicts with virtual paths, or None if the field is absent or empty.
        """
        kwargs_files = (message.additional_kwargs or {}).get("files")
        if not isinstance(kwargs_files, list) or not kwargs_files:
            return None

        files = []
        for f in kwargs_files:
            if not isinstance(f, dict):
                continue
            filename = f.get("filename") or ""
            if not filename or Path(filename).name != filename:
                continue
            if uploads_dir is not None and not (uploads_dir / filename).is_file():
                continue
            files.append(
                {
                    "filename": filename,
                    "size": int(f.get("size") or 0),
                    "path": f"/mnt/user-data/uploads/{filename}",
                    "extension": Path(filename).suffix,
                }
            )
        return files if files else None

    @override
    def before_agent(self, state: UploadsMiddlewareState, runtime: Runtime) -> dict | None:
        """Inject uploaded files information before agent execution.

        New files come from the current message's additional_kwargs.files.
        Historical files are scanned from the thread's uploads directory,
        excluding the new ones.

        Prepends <uploaded_files> context to the last human message content.
        The original additional_kwargs (including files metadata) is preserved
        on the updated message so the frontend can read it from the stream.

        Args:
            state: Current agent state.
            runtime: Runtime context containing thread_id.

        Returns:
            State updates including uploaded files list.
        """
        messages = list(state.get("messages", []))
        if not messages:
            return None

        last_message_index = len(messages) - 1
        last_message = messages[last_message_index]

        if not isinstance(last_message, HumanMessage):
            return None

        # Resolve uploads directory for existence checks
        thread_id = (runtime.context or {}).get("thread_id")
        if thread_id is None:
            try:
                from langgraph.config import get_config

                thread_id = get_config().get("configurable", {}).get("thread_id")
            except RuntimeError:
                pass  # get_config() raises outside a runnable context (e.g. unit tests)
        uploads_dir = self._paths.sandbox_uploads_dir(thread_id) if thread_id else None

        # Get newly uploaded files from the current message's additional_kwargs.files
        new_files = self._files_from_kwargs(last_message, uploads_dir) or []

        # Collect historical files from the uploads directory (all except the new ones)
        new_filenames = {f["filename"] for f in new_files}
        historical_files: list[dict] = []
        if uploads_dir and uploads_dir.exists():
            for file_path in sorted(uploads_dir.iterdir()):
                if file_path.is_file() and file_path.name not in new_filenames:
                    stat = file_path.stat()
                    outline, preview = _extract_outline_for_file(file_path)
                    historical_files.append(
                        {
                            "filename": file_path.name,
                            "size": stat.st_size,
                            "path": f"/mnt/user-data/uploads/{file_path.name}",
                            "extension": file_path.suffix,
                            "outline": outline,
                            "outline_preview": preview,
                        }
                    )

        # Attach outlines to new files as well
        if uploads_dir:
            for file in new_files:
                phys_path = uploads_dir / file["filename"]
                outline, preview = _extract_outline_for_file(phys_path)
                file["outline"] = outline
                file["outline_preview"] = preview

        if not new_files and not historical_files:
            return None

        logger.debug(f"New files: {[f['filename'] for f in new_files]}, historical: {[f['filename'] for f in historical_files]}")

        # Create files message and prepend to the last human message content
        files_message = self._create_files_message(new_files, historical_files, uploads_dir)

        # Extract original content - handle both string and list formats
        original_content = last_message.content
        if isinstance(original_content, str):
            # Simple case: string content, just prepend files message
            updated_content = f"{files_message}\n\n{original_content}"
        elif isinstance(original_content, list):
            # Complex case: list content (multimodal), preserve all blocks
            # Prepend files message as the first text block
            files_block = {"type": "text", "text": f"{files_message}\n\n"}
            # Keep all original blocks (including images)
            updated_content = [files_block, *original_content]
        else:
            # Other types, preserve as-is
            updated_content = original_content

        # Create new message with combined content.
        # Preserve additional_kwargs (including files metadata) so the frontend
        # can read structured file info from the streamed message.
        updated_message = HumanMessage(
            content=updated_content,
            id=last_message.id,
            additional_kwargs=last_message.additional_kwargs,
        )

        messages[last_message_index] = updated_message

        return {
            "uploaded_files": new_files,
            "messages": messages,
        }
