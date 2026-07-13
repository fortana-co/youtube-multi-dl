"""
Network integration tests exercising the real CLI against tiny uploaded fixtures. Skipped unless `fixtures.json` is
populated (see conftest). These drive the CLI as a subprocess and assert the JSON stdout contract + exit codes.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import HAS_FFMPEG, load_youtube_fixtures
from youtube_music_dl import schema

FIXTURES = load_youtube_fixtures()
pytestmark = [
    pytest.mark.youtube,
    pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not installed"),
    pytest.mark.skipif(not FIXTURES, reason="fixtures.json not populated; see tests/conftest and fixtures README"),
]


def run_cli(*args: str, cwd: Path) -> tuple[int, dict]:
    """Run the CLI, returning (exit_code, parsed stdout JSON). Logs go to stderr."""
    proc = subprocess.run(
        [sys.executable, "-m", "youtube_music_dl.command_line", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    return proc.returncode, json.loads(proc.stdout)


def _need(key: str) -> str:
    value = FIXTURES.get(key)
    if not value:
        pytest.skip(f"fixtures.json missing {key}")
    assert value  # skip() is NoReturn at runtime; this narrows the type
    return value


def test_probe_detects_modes(tmp_path: Path):
    struct = _need("structured_chapters_video_id")
    code, r = run_cli("--probe", struct, cwd=tmp_path)
    schema.validate_probe(r)
    assert code == 0 and r["mode"] == "chapters" and len(r["chapters"]) == 3

    unstruct = _need("unstructured_tracklist_video_id")
    code, r = run_cli("--probe", unstruct, cwd=tmp_path)
    schema.validate_probe(r)
    assert code == 0 and r["mode"] == "single_songs" and r["chapters"] == [] and r["description"]

    playlist = _need("playlist_url")
    code, r = run_cli("--probe", playlist, cwd=tmp_path)
    schema.validate_probe(r)
    assert code == 0 and r["mode"] == "playlist" and len(r["entries"]) == 2


def test_playlist(tmp_path: Path):
    url = _need("playlist_url")
    code, result = run_cli(url, "-a", "Test Artist", "--album", "ymd playlist", "-o", str(tmp_path), cwd=tmp_path)
    schema.validate_result(result)
    assert code == 0
    assert result["mode"] == "playlist"
    assert len(result["tracks"]) == 2
    assert all(t["status"] == "downloaded" for t in result["tracks"])
    for t in result["tracks"]:
        assert Path(t["file"]).exists()
        assert t["youtube_video_id"]

    # re-run is idempotent: everything skipped
    code2, result2 = run_cli(url, "-a", "Test Artist", "--album", "ymd playlist", "-o", str(tmp_path), cwd=tmp_path)
    assert code2 == 0
    assert all(t["status"] == "skipped" for t in result2["tracks"])


def test_structured_chapters_autosplit(tmp_path: Path):
    vid = _need("structured_chapters_video_id")
    code, result = run_cli(vid, "-a", "Test Artist", "--album", "ymd structured", "-o", str(tmp_path), cwd=tmp_path)
    schema.validate_result(result)
    assert code == 0
    assert result["mode"] == "chapters"
    assert len(result["tracks"]) == 3  # Alpha / Bravo / Charlie
    assert [t["title"] for t in result["tracks"]] == ["Alpha", "Bravo", "Charlie"]


def test_m4a_end_to_end(tmp_path: Path):
    """Guard the full m4a pipeline that offline tests can't: real AAC-stream selection,
    ffmpeg copy-splitting into `.m4a`, EasyMP4 tagging a real file, schema, and idempotency."""
    from mutagen import File as MutagenFile

    from youtube_music_dl.tagging import read_provenance

    vid = _need("structured_chapters_video_id")
    args = (vid, "-a", "Test Artist", "--album", "ymd m4a", "-f", "m4a", "-o", str(tmp_path))
    code, result = run_cli(*args, cwd=tmp_path)
    schema.validate_result(result)
    assert code == 0
    assert result["format"] == "m4a"
    assert len(result["tracks"]) == 3 and all(t["status"] == "downloaded" for t in result["tracks"])
    for t in result["tracks"]:
        f = Path(t["file"])
        assert f.suffix == ".m4a" and f.exists()
        assert read_provenance(f) == t["youtube_video_id"]  # provenance readable from the real .m4a
        tags = MutagenFile(str(f), easy=True)
        assert tags is not None and tags["album"] == ["ymd m4a"]

    # idempotent re-run: the existing .m4a files are recognized (by provenance) and skipped
    code2, result2 = run_cli(*args, cwd=tmp_path)
    assert code2 == 0 and all(t["status"] == "skipped" for t in result2["tracks"])


def test_unstructured_via_chapters_file(tmp_path: Path):
    vid = _need("unstructured_tracklist_video_id")
    # agent-style: hand the tool a chapters file derived from the description
    chapters = [
        {"title": "Alpha", "start_time": 0, "end_time": 12},
        {"title": "Bravo", "start_time": 12, "end_time": 24},
        {"title": "Charlie", "start_time": 24, "end_time": 36},
    ]
    cf = tmp_path / "chapters.json"
    cf.write_text(json.dumps(chapters))
    code, result = run_cli(
        vid,
        "-a",
        "Test Artist",
        "--album",
        "ymd unstructured",
        "--chapters-file",
        str(cf),
        "-o",
        str(tmp_path),
        cwd=tmp_path,
    )
    schema.validate_result(result)
    assert code == 0
    assert result["mode"] == "chapters"
    assert len(result["tracks"]) == 3
    assert result["chapters_file"]  # normalized file path reported for inspection
