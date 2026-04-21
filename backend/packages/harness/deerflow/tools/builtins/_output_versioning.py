"""Shared helpers for timestamped deliverable filenames (e.g. ``名称_vYYYYMMDDHHMMSS.docx``)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

# Strip leading ``v…_`` where … is a prior timestamp, semver, or plain integer version.
_LEADING_V_PREFIX = re.compile(
    r"^v(?:\d{14}|\d{12}|\d+(?:\.\d+)+|\d+)_",
    re.IGNORECASE,
)

# Strip trailing ``_v…`` where … is a prior timestamp, semver, or plain integer version.
_TRAILING_V_SUFFIX = re.compile(
    r"_v(?:\d{14}|\d{12}|\d+(?:\.\d+)+|\d+)$",
    re.IGNORECASE,
)

def strip_trailing_v_suffix(stem: str) -> str:
    """Remove a trailing ``_v…`` or leading ``v…_`` version segment from a file *stem* (no extension)."""
    s = _TRAILING_V_SUFFIX.sub("", stem).rstrip("_")
    s = _LEADING_V_PREFIX.sub("", s).lstrip("_")
    return s


def resolve_unique_versioned_filename(
    outputs_dir: Path,
    base_stem: str,
    extension: str,
    *,
    now_start: datetime | None = None,
    time_format: str = "%Y%m%d%H%M",
) -> str:
    """Return a unique filename ``v{time}_{base_stem}{extension}`` under ``outputs_dir``.

    Default ``time_format`` is ``%Y%m%d%H%M`` (年月日时分), e.g. ``v202604210933_``.
    Pass ``time_format="%Y%m%d%H%M%S"`` if filenames must include seconds.
    """
    ext = extension if extension.startswith(".") else f".{extension}"
    t = now_start or datetime.now()
    while True:
        version = t.strftime(time_format)
        name = f"v{version}_{base_stem}{ext}"
        if not (outputs_dir / name).exists():
            return name
        if "%S" in time_format or "%f" in time_format:
            t += timedelta(seconds=1)
        else:
            t += timedelta(minutes=1)
