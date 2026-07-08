"""
Shared pytest fixtures.

Offline tests generate tiny local media with ffmpeg; they skip if ffmpeg is absent. Network tests are marked `youtube`
and skip unless a populated `fixtures.json` is available (see `~/Desktop/test/fixtures/README.md`), so the default
`pytest` run is fully offline.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

HAS_FFMPEG = bool(shutil.which("ffmpeg")) and bool(shutil.which("ffprobe"))
requires_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not installed")

# fixtures.json lives in the repo (tests/fixtures/); override with YMD_FIXTURES.
FIXTURES_JSON = Path(__file__).parent / "fixtures" / "fixtures.json"


def load_youtube_fixtures() -> dict[str, str]:
    """Return only the populated string values from fixtures.json (or {})."""
    if not FIXTURES_JSON.exists():
        return {}
    data = json.loads(FIXTURES_JSON.read_text())
    return {k: v for k, v in data.items() if isinstance(v, str) and v and not k.startswith("_")}


@pytest.fixture
def make_audio(tmp_path: Path):
    """Generate a single-tone audio file (opus or mp3) of a given duration."""

    def _make(name: str, *, freq: int = 440, seconds: float = 2.0, fmt: str = "opus") -> Path:
        ext, codec = (".opus", "libopus") if fmt == "opus" else (".mp3", "libmp3lame")
        out = tmp_path / f"{name}{ext}"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency={freq}",
                "-t",
                str(seconds),
                "-c:a",
                codec,
                str(out),
            ],
            check=True,
        )
        return out

    return _make
