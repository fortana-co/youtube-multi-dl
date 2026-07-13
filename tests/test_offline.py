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
from youtube_music_dl import schema
from youtube_music_dl.downloader import (
    UserError,
    clean_filename,
    detect_mode,
    downloader,
    ffmpeg_extract_segment,
    get_strip_meta_patterns,
    media_duration_s,
    normalize_chapters,
    parse_chapters_file,
    parse_track_numbers,
    retag,
    strip,
)
from youtube_music_dl.tagging import existing_files_by_id, read_provenance, tag_audio

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


def test_strip_collapses_and_trims_whitespace():
    # a removal that leaves a gap must collapse to a single space, not a double
    assert strip("A B C", [r"B"]) == "A C"
    # leading/trailing/interior whitespace is normalized even when nothing matches
    assert strip("  padded  title  ", [r"x"]) == "padded title"


@pytest.mark.parametrize(
    "raw, artist, album, expected",
    [
        # the strip-meta patterns drop a leading show/playlist index number that directly precedes the
        # artist (e.g. "1310 Artist - Title" -> "Title"), plus the artist and album names themselves
        (
            "1310 Ernest Tubb & Red Foley - Too Old To Cut The Mustard",
            "Ernest Tubb & Red Foley",
            "",
            "Too Old To Cut The Mustard",
        ),
        ("05 The Beatles - Yesterday", "The Beatles", "", "Yesterday"),
        ("42 - Coldplay - Viva la Vida", "Coldplay", "", "Viva la Vida"),
        # the artist lookahead guards it: a real title that merely begins with a number is never touched
        ("The Smashing Pumpkins - 1979", "The Smashing Pumpkins", "", "1979"),
        ("1979", "The Smashing Pumpkins", "", "1979"),
        ("Nena - 99 Luftballons", "Nena", "", "99 Luftballons"),
        ("24K Magic", "Bruno Mars", "", "24K Magic"),
        # album names are stripped too, on either side of the title
        ("Pink Floyd - The Wall - Mother", "Pink Floyd", "The Wall", "Mother"),
    ],
)
def test_get_strip_meta_patterns(raw: str, artist: str, album: str, expected: str):
    assert (strip(raw, get_strip_meta_patterns(artist, album)) or raw) == expected


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
@pytest.mark.parametrize("fmt", ["opus", "m4a", "mp3"])
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
        [sys.executable, "-m", "youtube_music_dl.command_line", *args], capture_output=True, text=True
    )


def test_cli_print_schema():
    proc = _run_cli("--print-schema")
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert set(data) == {"result", "error", "probe", "retag", "upgrade", "chapters_file"}


def test_cli_print_skill():
    proc = _run_cli("--print-skill")
    assert proc.returncode == 0
    assert proc.stdout.startswith("---")
    assert "youtube-music-dl" in proc.stdout


def test_resolve_output_dir(monkeypatch):
    from youtube_music_dl.command_line import resolve_output_dir

    monkeypatch.delenv("YMD_OUTPUT_DIR", raising=False)
    assert resolve_output_dir("") == ""  # nothing set -> current dir
    assert resolve_output_dir(".") == "."  # explicit -o . -> current dir

    monkeypatch.setenv("YMD_OUTPUT_DIR", "/music")
    assert resolve_output_dir("") == "/music"  # fall back to the env var
    assert resolve_output_dir(".") == "."  # explicit -o . still wins over the env var
    assert resolve_output_dir("/x") == "/x"  # any explicit path wins


def test_resolve_audio_quality(monkeypatch):
    from youtube_music_dl.command_line import resolve_audio_quality

    monkeypatch.delenv("YMD_AUDIO_QUALITY", raising=False)
    assert resolve_audio_quality("") == ""  # nothing set -> unset
    assert resolve_audio_quality("320K") == "320K"  # explicit -q

    monkeypatch.setenv("YMD_AUDIO_QUALITY", "160K")
    assert resolve_audio_quality("") == "160K"  # fall back to the env var
    assert resolve_audio_quality("320K") == "320K"  # explicit -q wins over the env var


def test_normalize_audio_quality():
    from youtube_music_dl.downloader import UserError, normalize_audio_quality

    # valid: K suffix stripped so yt-dlp actually honors the bitrate; VBR passes through
    assert normalize_audio_quality("") == ""
    assert normalize_audio_quality("160K") == "160"
    assert normalize_audio_quality("160k") == "160"
    assert normalize_audio_quality("320") == "320"
    assert normalize_audio_quality("5") == "5"  # VBR (mp3)
    assert normalize_audio_quality("0") == "0"

    # invalid: fail loudly before any download
    for bad in ("abc", "high", "-5", "k", "128kbps"):
        with pytest.raises(UserError) as exc:
            normalize_audio_quality(bad)
        assert exc.value.code == "INVALID_ARGS"


def test_resolve_audio_format(monkeypatch):
    from youtube_music_dl.command_line import resolve_audio_format
    from youtube_music_dl.downloader import DEFAULT_AUDIO_FORMAT

    monkeypatch.delenv("YMD_AUDIO_FORMAT", raising=False)
    assert resolve_audio_format("") == DEFAULT_AUDIO_FORMAT  # nothing set -> default
    assert resolve_audio_format("m4a") == "m4a"  # explicit -f

    monkeypatch.setenv("YMD_AUDIO_FORMAT", "mp3")
    assert resolve_audio_format("") == "mp3"  # fall back to the env var
    assert resolve_audio_format("m4a") == "m4a"  # explicit -f wins over the env var


def test_download_opts_per_format(tmp_path: Path):
    from youtube_music_dl.downloader import DEFAULT_MP3_QUALITY, download_opts

    # opus/m4a: select the matching native stream and DON'T force a quality (so it's a copy)
    for fmt, selection in [("opus", "bestaudio[acodec=opus]"), ("m4a", "bestaudio[ext=m4a]")]:
        opts = download_opts(tmp_path, fmt, "")
        pp = opts["postprocessors"][0]
        assert pp["preferredcodec"] == fmt
        assert "preferredquality" not in pp  # copy, no re-encode
        assert opts["format"].startswith(selection)

    # mp3: always transcodes, so it gets the default bitrate
    pp = download_opts(tmp_path, "mp3", "")["postprocessors"][0]
    assert pp["preferredcodec"] == "mp3"
    assert pp["preferredquality"] == DEFAULT_MP3_QUALITY

    # an explicit quality applies to any format (forces a re-encode)
    assert download_opts(tmp_path, "opus", "128")["postprocessors"][0]["preferredquality"] == "128"


def test_warn_if_transcoded(capsys):
    from youtube_music_dl.downloader import warn_if_transcoded

    warn_if_transcoded({"acodec": "opus"}, "opus", "id_copy")  # native opus -> copy, silent
    warn_if_transcoded({"acodec": "mp4a.40.2"}, "opus", "id_reencode")  # aac source -> notice
    warn_if_transcoded({"acodec": "opus"}, "mp3", "id_mp3")  # mp3 always transcodes -> silent by design

    err = capsys.readouterr().err
    assert "id_reencode" in err and "re-encoded" in err
    assert "id_copy" not in err and "id_mp3" not in err


def test_result_schema_format_enum_matches_audio_formats():
    # guard against the schema's `format` enum drifting from the supported formats
    from youtube_music_dl.downloader import AUDIO_FORMATS

    assert set(schema.RESULT_SCHEMA["properties"]["format"]["enum"]) == set(AUDIO_FORMATS)


# --- keeping yt-dlp fresh (hint + `upgrade` subcommand) --------------------


def test_outdated_ytdlp_hint(monkeypatch):
    import youtube_music_dl.downloader as dl

    monkeypatch.setattr(dl, "has_pip", lambda: True)  # deterministic regardless of the test env
    hint = dl.outdated_ytdlp_hint()
    assert "yt-dlp" in hint and dl.YT_DLP_SPEC in hint  # actionable upgrade command is present
    assert "youtube-music-dl upgrade" in hint  # the self-heal subcommand is mentioned


def test_ytdlp_upgrade_argv_selects_by_install(monkeypatch):
    import youtube_music_dl.downloader as dl

    # pip present (pip/pipx) -> upgrade yt-dlp with pip, in the running interpreter
    monkeypatch.setattr(dl, "has_pip", lambda: True)
    argv = dl.ytdlp_upgrade_argv()
    assert argv[:3] == [sys.executable, "-m", "pip"] and dl.YT_DLP_SPEC in argv

    # no pip but uv present (uv tool install) -> `uv tool upgrade <name>`
    monkeypatch.setattr(dl, "has_pip", lambda: False)
    monkeypatch.setattr(dl.shutil, "which", lambda name: "/usr/local/bin/uv" if name == "uv" else None)
    assert dl.ytdlp_upgrade_argv() == ["/usr/local/bin/uv", "tool", "upgrade", dl.DISTRIBUTION_NAME]

    # neither -> fall back to a concrete pip command (used only to show in the error message)
    monkeypatch.setattr(dl.shutil, "which", lambda name: None)
    assert dl.ytdlp_upgrade_argv()[:3] == [sys.executable, "-m", "pip"]


def test_upgrade_subcommand_success(monkeypatch, capfd):
    import youtube_music_dl.command_line as cl

    class Done:
        returncode = 0

    monkeypatch.setattr(cl.subprocess, "run", lambda *a, **k: Done())
    versions = iter(["2026.1.1", "2026.7.4"])  # before, after
    monkeypatch.setattr(cl, "ytdlp_version", lambda: next(versions))

    with pytest.raises(SystemExit) as exc:
        cl.main_upgrade([])
    assert exc.value.code == 0
    out = json.loads(capfd.readouterr().out)
    schema.validate_upgrade(out)
    assert out["package"] == "yt-dlp" and out["from"] == "2026.1.1" and out["to"] == "2026.7.4"


def test_upgrade_subcommand_failure(monkeypatch, capfd):
    import youtube_music_dl.command_line as cl

    class Failed:
        returncode = 1  # e.g. no pip in a `uv tool` env, or a network error

    monkeypatch.setattr(cl.subprocess, "run", lambda *a, **k: Failed())
    monkeypatch.setattr(cl, "ytdlp_version", lambda: "2026.1.1")

    with pytest.raises(SystemExit) as exc:
        cl.main_upgrade([])
    assert exc.value.code == 1
    out = json.loads(capfd.readouterr().out)
    schema.validate_error(out)
    assert out["error"]["code"] == "UPGRADE_FAILED"
    assert "uv tool upgrade" in out["error"]["message"]  # fallback path for isolated installs


# --- chapters file JSON validation ----------------------------------------


def test_chapters_file_schema_sample():
    schema.validate_chapters_file([{"title": "A", "start_time": 0, "end_time": 12}])
    schema.validate_chapters_file([{"start_time": "1:23"}])  # partial, "MM:SS" ok
    with pytest.raises(jsonschema.ValidationError):
        schema.validate_chapters_file([{"start_time": [1, 2]}])  # wrong type


def test_parse_chapters_file_rejects_bad_json(tmp_path: Path):
    good = tmp_path / "good.json"
    good.write_text(json.dumps([{"title": "A", "start_time": "0:00"}]))
    assert parse_chapters_file(str(good))[0]["title"] == "A"

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([{"title": "A", "start": 0}]))  # 'start' should be 'start_time'
    with pytest.raises(UserError) as e:
        parse_chapters_file(str(bad))
    assert e.value.code == "INVALID_ARGS"


# --- retag ----------------------------------------------------------------


def test_retag_schema_sample():
    schema.validate_retag(
        {
            "version": schema.SCHEMA_VERSION,
            "ok": True,
            "action": "retag",
            "artist": "X",
            "album": "Y",
            "directory": "/abs/X/Y",
            "files": [{"file": "/abs/X/Y/01 - a.opus", "youtube_video_id": "abc"}],
        }
    )


def _make_album(make_audio, base: Path, artist: str, album: str, titles: list[str]) -> Path:
    album_dir = base / artist / album
    album_dir.mkdir(parents=True)
    for i, title in enumerate(titles, 1):
        src = make_audio(f"src{i}", fmt="opus")
        dest = album_dir / f"{i:02d} - {title}.opus"
        src.rename(dest)
        tag_audio(
            dest, title=title, artist=artist, album=album, tracknumber=f"{i}/{len(titles)}", youtube_video_id=f"VID{i}"
        )
    return album_dir


@requires_ffmpeg
def test_retag_moves_and_retags(make_audio, tmp_path: Path):
    from mutagen.oggopus import OggOpus

    album = _make_album(make_audio, tmp_path, "Old Artist", "Old Album", ["A", "B"])
    result = retag(str(album), artist="New Artist", album="New Album")
    schema.validate_retag(result)

    new_dir = tmp_path / "New Artist" / "New Album"
    assert Path(result["directory"]) == new_dir
    assert not album.exists()  # moved
    assert not (tmp_path / "Old Artist").exists()  # emptied old artist dir cleaned up

    files = sorted(new_dir.glob("*.opus"))
    assert len(files) == 2
    a = OggOpus(files[0])
    assert a["artist"] == ["New Artist"] and a["album"] == ["New Album"]
    assert a["title"] == ["A"] and a["tracknumber"] == ["1/2"]  # preserved
    assert read_provenance(files[0]) == "VID1"  # provenance preserved


@requires_ffmpeg
def test_retag_only_album_renames_in_place(make_audio, tmp_path: Path):
    album = _make_album(make_audio, tmp_path, "Artist", "Old Album", ["A"])
    result = retag(str(album), album="New Album")
    assert Path(result["directory"]) == tmp_path / "Artist" / "New Album"
    assert result["artist"] == "Artist"  # unchanged


@requires_ffmpeg
def test_retag_dest_exists_errors(make_audio, tmp_path: Path):
    album = _make_album(make_audio, tmp_path, "Artist", "Album", ["A"])
    (tmp_path / "Artist" / "New").mkdir()  # destination already exists
    with pytest.raises(UserError) as e:
        retag(str(album), album="New")
    assert e.value.code == "INVALID_ARGS"


def test_retag_no_audio_errors(tmp_path: Path):
    empty = tmp_path / "Artist" / "Album"
    empty.mkdir(parents=True)
    with pytest.raises(UserError) as e:
        retag(str(empty), artist="X")
    assert e.value.code == "INVALID_ARGS"


def test_cli_retag_dispatch_errors_cleanly():
    proc = _run_cli("retag", "/definitely/not/here")
    assert proc.returncode == 1
    err = json.loads(proc.stdout)
    assert err["ok"] is False and err["error"]["code"] == "INVALID_ARGS"
