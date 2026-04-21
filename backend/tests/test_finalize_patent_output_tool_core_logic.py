"""Core behavior tests for finalize_patent_output tool filename versioning."""

import importlib
import re
from datetime import datetime
from types import SimpleNamespace

finalize_patent_output_tool_module = importlib.import_module("deerflow.tools.builtins.finalize_patent_output_tool")
_output_versioning_module = importlib.import_module("deerflow.tools.builtins._output_versioning")


def _make_runtime(workspace_path: str, uploads_path: str, outputs_path: str) -> SimpleNamespace:
    return SimpleNamespace(
        state={
            "thread_data": {
                "workspace_path": workspace_path,
                "uploads_path": uploads_path,
                "outputs_path": outputs_path,
            }
        },
        context={"thread_id": "thread-1"},
        config={},
    )


def test_finalize_patent_output_uses_timestamp_version(tmp_path, monkeypatch):
    workspace_dir = tmp_path / "workspace"
    uploads_dir = tmp_path / "uploads"
    outputs_dir = tmp_path / "outputs"
    workspace_dir.mkdir(parents=True)
    uploads_dir.mkdir(parents=True)
    outputs_dir.mkdir(parents=True)

    source_path = workspace_dir / "draft.docx"
    source_path.write_text("专利草稿")

    fixed_now = datetime(2026, 4, 20, 14, 46, 30)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    monkeypatch.setattr(_output_versioning_module, "datetime", FixedDateTime)

    result = finalize_patent_output_tool_module.finalize_patent_output_tool.func(
        runtime=_make_runtime(str(workspace_dir), str(uploads_dir), str(outputs_dir)),
        patent_title="一种 新型 装置",
        source_filepath=str(source_path),
        tool_call_id="tc-1",
    )

    artifact_path = result.update["artifacts"][0]
    assert re.fullmatch(r"/mnt/user-data/outputs/一种_新型_装置_v202604201446\.docx", artifact_path)
    assert (outputs_dir / "一种_新型_装置_v202604201446.docx").read_text() == "专利草稿"


def test_finalize_patent_output_bumps_minute_when_same_timestamp_exists(tmp_path, monkeypatch):
    workspace_dir = tmp_path / "workspace"
    uploads_dir = tmp_path / "uploads"
    outputs_dir = tmp_path / "outputs"
    workspace_dir.mkdir(parents=True)
    uploads_dir.mkdir(parents=True)
    outputs_dir.mkdir(parents=True)

    source_path = workspace_dir / "draft.docx"
    source_path.write_text("内容A")

    fixed_now = datetime(2026, 4, 20, 14, 46, 30)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    monkeypatch.setattr(_output_versioning_module, "datetime", FixedDateTime)
    (outputs_dir / "标题_v202604201446.docx").write_text("旧版本")

    result = finalize_patent_output_tool_module.finalize_patent_output_tool.func(
        runtime=_make_runtime(str(workspace_dir), str(uploads_dir), str(outputs_dir)),
        patent_title="标题",
        source_filepath=str(source_path),
        tool_call_id="tc-2",
    )

    assert result.update["artifacts"] == ["/mnt/user-data/outputs/标题_v202604201447.docx"]
    assert (outputs_dir / "标题_v202604201447.docx").read_text() == "内容A"
