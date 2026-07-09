"""
Offline tests: pure logic, local tagging/idempotency, local chapter-splitting, and JSON-schema validation. No network
access.
"""

import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

from tests.conftest import requires_ffmpeg
from youtube_multi_dl import schema
from youtube_multi_dl.downloader import (
    UserError,
    clean_filename,
    detect_mode,
    downloader,
    ffmpeg_extract_segment,
    media_duration_s,
    normalize_chapters,
    parse_chapters_file,
    parse_track_numbers,
    strip,
)
from youtube_multi_dl.tagging import existing_files_by_id, read_provenance, tag_audio

# --- pure helpers ---------------------------------------------------------


def test_parse_track_numbers():
    assert parse_track_numbers("") == []
    assert parse_track_numbers("1,3-5,7") == [1, 3, 4, 5, 7]
    assert parse_track_numbers(" 1 , 2 ") == [1, 2]


def test_parse_track_numbers_invalid():
    with pytest.raises(UserError) as e:
        parse_track_numbers("1,foo")
    assert e.value.code == "INVALID_ARGS"


def test_strip_removes_patterns_case_insensitively():
    assert strip("Harry Nilsson - Gotta Get Up", [r" *-? *Harry Nilsson *-? *"]).strip() == "Gotta Get Up"
    assert strip("Title", None) == "Title"


def test_clean_filename():
    assert clean_filename("a/b\\c") == "abc"
    assert clean_filename("  spaced  ") == "spaced"


# --- chapters normalization ----------------------------------------------


def test_normalize_chapters_fills_missing_bounds():
    # typical YouTube chapters: only start times, no end times
    raw = [
        {"title": "A", "start_time": 0, "end_time": None},
        {"title": "B", "start_time": 12, "end_time": None},
        {"title": "C", "start_time": 24, "end_time": None},
    ]
    out = normalize_chapters(raw, duration=36.0)
    # each chapter ends where the next begins; the final one ends at the true duration
    assert [(c.start, c.end) for c in out] == [(0.0, 12.0), (12.0, 24.0), (24.0, 36.0)]


def test_normalize_chapters_mmss_strings():
    # hand-authored / example chapters files use "MM:SS" start times
    raw = [
        {"title": "A", "start_time": "00:00"},
        {"title": "B", "start_time": "01:56"},
        {"title": "C", "start_time": "04:29"},
    ]
    out = normalize_chapters(raw, duration=300.0)
    assert [(c.start, c.end) for c in out] == [(0.0, 116.0), (116.0, 269.0), (269.0, 300.0)]


def test_normalize_chapters_from_durations_accumulate():
    # the "unstructured tracklist" workflow: three 12s durations -> cumulative starts
    raw = [
        {"title": "Alpha", "start_time": 0, "end_time": 12},
        {"title": "Bravo", "start_time": 12, "end_time": 24},
        {"title": "Charlie", "start_time": 24, "end_time": 36},
    ]
    out = normalize_chapters(raw, duration=36.0)
    assert [(c.start, c.end) for c in out] == [(0.0, 12.0), (12.0, 24.0), (24.0, 36.0)]


# --- chapters file parsing ------------------------------------------------


def test_parse_chapters_file_json(tmp_path: Path):
    p = tmp_path / "ch.json"
    p.write_text(json.dumps([{"title": "A", "start_time": 0, "end_time": 5}]))
    assert parse_chapters_file(str(p)) == [{"title": "A", "start_time": 0, "end_time": 5}]


def test_parse_chapters_file_csv(tmp_path: Path):
    p = tmp_path / "ch.csv"
    p.write_text("Alpha,0,12\nBravo,12,24\n")
    out = parse_chapters_file(str(p))
    assert out[0]["title"] == "Alpha" and out[1]["start_time"] == "12"


EXAMPLES = Path(__file__).parent.parent / "examples" / "chapters_file"


@pytest.mark.parametrize("name", ["chapters.json", "chapters.csv", "chapters_end_time.json", "chapters_end_time.csv"])
def test_example_chapters_files_parse_and_normalize(name):
    chapters = parse_chapters_file(str(EXAMPLES / name))
    out = normalize_chapters(chapters, duration=600.0)
    assert len(out) == 4
    assert all(c.end >= c.start for c in out)  # sane, monotonic bounds


# --- tagging round trips (need ffmpeg to make files) ----------------------


@requires_ffmpeg
@pytest.mark.parametrize("fmt", ["opus", "mp3"])
def test_tag_roundtrip(make_audio, fmt):
    path = make_audio("track", fmt=fmt)
    tag_audio(
        path,
        title="Alpha",
        artist="Baden Powell",
        album="Os Afro-Sambas",
        tracknumber="1/3",
        youtube_video_id="abc123XYZ_-",
    )
    assert read_provenance(path) == "abc123XYZ_-"

    from mutagen import File as MutagenFile

    audio = MutagenFile(str(path), easy=True)
    assert audio is not None
    assert audio["title"] == ["Alpha"]
    assert audio["artist"] == ["Baden Powell"]
    assert audio["album"] == ["Os Afro-Sambas"]
    assert audio["tracknumber"] == ["1/3"]


@requires_ffmpeg
def test_existing_files_by_id(make_audio, tmp_path: Path):
    a = make_audio("one", fmt="opus")
    b = make_audio("two", fmt="mp3")
    tag_audio(a, title="A", artist="x", album="y", tracknumber="1/2", youtube_video_id="VID_A")
    tag_audio(b, title="B", artist="x", album="y", tracknumber="2/2", youtube_video_id="VID_B")
    by_id = existing_files_by_id(tmp_path)
    assert set(by_id) == {"VID_A", "VID_B"}
    assert by_id["VID_A"][0].name == a.name


# --- local chapter split (the core offline end-to-end) --------------------


@requires_ffmpeg
def test_split_by_chapters_offline(make_audio, tmp_path: Path):
    # a 6s source, split into three 2s chapters, tagged; no YouTube involved.
    source = make_audio("source", seconds=6.0, fmt="opus")
    duration = media_duration_s(source)
    assert 5.9 < duration < 6.2

    raw = [
        {"title": "Alpha", "start_time": 0, "end_time": None},
        {"title": "Bravo", "start_time": 2, "end_time": None},
        {"title": "Charlie", "start_time": 4, "end_time": None},
    ]
    chapters = normalize_chapters(raw, duration)
    out_dir = tmp_path / "album"
    out_dir.mkdir()
    for i, ch in enumerate(chapters, 1):
        dest = out_dir / f"{i:02d} - {ch.title}.opus"
        ffmpeg_extract_segment(source, ch.start, ch.end, dest)
        tag_audio(
            dest,
            title=ch.title or "",
            artist="Baden Powell",
            album="Os Afro-Sambas",
            tracknumber=f"{i}/3",
            youtube_video_id="SRC_ID",
        )

    files = sorted(out_dir.glob("*.opus"))
    assert [f.name for f in files] == ["01 - Alpha.opus", "02 - Bravo.opus", "03 - Charlie.opus"]
    for f in files:
        assert 1.8 < media_duration_s(f) < 2.3
    # all chapters carry the source video id as provenance
    assert set(existing_files_by_id(out_dir)) == {"SRC_ID"}


# --- downloader precondition errors (raised before any network) -----------


def test_downloader_rejects_bad_format():
    with pytest.raises(UserError) as e:
        downloader(urls=["x"], artist="a", audio_format="flac")
    assert e.value.code == "INVALID_ARGS"


def test_downloader_missing_chapters_file():
    with pytest.raises(UserError) as e:
        downloader(urls=["x"], artist="a", chapters_file="/definitely/not/here.json")
    assert e.value.code == "NO_CHAPTERS_FILE"


# --- schema conformance ---------------------------------------------------


def test_result_schema_accepts_sample():
    sample = {
        "version": schema.SCHEMA_VERSION,
        "ok": True,
        "mode": "playlist",
        "album": "Os Afro-Sambas",
        "artist": "Baden Powell",
        "directory": "/abs/Os Afro-Sambas",
        "format": "opus",
        "chapters_file": None,
        "tracks": [
            {
                "index": 1,
                "status": "downloaded",
                "title": "Canto de Ossanha",
                "youtube_video_id": "abc",
                "url": "https://y/watch?v=abc",
                "file": "/abs/01.opus",
            },
        ],
    }
    schema.validate_result(sample)


def test_result_schema_rejects_bad_status():
    bad = {
        "version": schema.SCHEMA_VERSION,
        "ok": True,
        "mode": "playlist",
        "album": "a",
        "artist": "b",
        "directory": "/x",
        "format": "opus",
        "chapters_file": None,
        "tracks": [{"index": 1, "status": "bogus", "title": "t", "youtube_video_id": None, "url": None, "file": None}],
    }
    with pytest.raises(jsonschema.ValidationError):
        schema.validate_result(bad)


def test_error_schema_roundtrip():
    err = schema.make_error("NO_JS_RUNTIME", "install deno or node")
    schema.validate_error(err)
    assert err["ok"] is False and err["error"]["code"] == "NO_JS_RUNTIME"


# --- mode detection + probe (no network) ----------------------------------


def test_detect_mode():
    assert detect_mode({"extractor": "youtube", "chapters": [{"start_time": 0}]}, has_chapters_file=False) == "chapters"
    assert detect_mode({"extractor": "youtube"}, has_chapters_file=True) == "chapters"
    assert detect_mode({"extractor": "youtube"}, has_chapters_file=False) == "single_songs"
    assert detect_mode({"extractor": "youtube:tab"}, has_chapters_file=False) == "playlist"


def test_probe_schema_accepts_sample():
    sample = {
        "version": schema.SCHEMA_VERSION,
        "kind": "probe",
        "mode": "single_songs",
        "title": "Some Full Album",
        "duration_s": 2038,
        "chapters": [],
        "entries": [],
        "description": "1. Song A [2:24]\n2. Song B [2:02]",
        "hint": "single video with no chapters",
    }
    schema.validate_probe(sample)


# --- self-describing CLI flags (subprocess, no network) -------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "youtube_multi_dl.command_line", *args], capture_output=True, text=True
    )


def test_cli_print_schema():
    proc = _run_cli("--print-schema")
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert set(data) == {"result", "error", "probe"}


def test_cli_print_skill():
    proc = _run_cli("--print-skill")
    assert proc.returncode == 0
    assert proc.stdout.startswith("---")
    assert "youtube-multi-dl" in proc.stdout


def test_resolve_output_path(monkeypatch):
    from youtube_multi_dl.command_line import resolve_output_path

    monkeypatch.delenv("YMD_OUTPUT_DIR", raising=False)
    assert resolve_output_path("") == ""  # nothing set -> current dir
    assert resolve_output_path(".") == "."  # explicit -o . -> current dir

    monkeypatch.setenv("YMD_OUTPUT_DIR", "/music")
    assert resolve_output_path("") == "/music"  # fall back to the env var
    assert resolve_output_path(".") == "."  # explicit -o . still wins over the env var
    assert resolve_output_path("/x") == "/x"  # any explicit path wins
