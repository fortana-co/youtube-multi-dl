"""
Orchestration over yt-dlp: download, split, clean, tag, and report.

Design notes:

- yt-dlp does the audio extraction *and* baseline metadata embedding. We control
  its output template (`<id>.<ext>`), so the produced file path is deterministic
  and we never glob for it.
- We then apply a targeted tagging pass for the fields yt-dlp gets wrong or omits
  (authoritative artist/album, cleaned title, `N/total` track number, provenance)
  and rename to a clean `NN - Title.<ext>`.
- Idempotency is by the `youtube_video_id` provenance tag on existing files.
- Everything here logs to stderr; the CLI is responsible for the single stdout
  JSON object. `downloader()` returns the result dict (see `schema.RESULT_SCHEMA`).
"""

import csv
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Generic, NamedTuple, TypeVar

import jsonschema
import yt_dlp

from .schema import SCHEMA_VERSION, ErrorCode, validate_chapters_file
from .tagging import SUPPORTED_EXTENSIONS, existing_files_by_id, read_provenance, tag_audio, update_tags

# yt-dlp's `extract_info`/`YoutubeDL` are effectively dynamic; treat as untyped.
youtube_dl: Any = yt_dlp

Info = dict[str, Any]
T = TypeVar("T")

# YouTube throttles bursts of requests, which surfaces as an extraction that fails and then succeeds moments later, so
# extractions are retried before being reported as failed. One entry per retry; a video whose failure we can't classify
# costs their sum in extra wall time. Kept short because downloads are serial, which already spaces requests out.
RETRY_DELAYS_S = (2.0, 5.0)

# Substrings (matched case-insensitively) of yt-dlp errors that no retry can fix, so we fail fast instead of backing
# off. Deliberately conservative: an unrecognized error is treated as transient and retried, so the worst case for a
# missing entry here is the wait we'd have done anyway. Never add throttling messages ("429", "confirm you're not a
# bot"); those are exactly what the retries exist for. Error text comes from YouTube, which means it can change w/o
# warning, but it probably won't -- these error messages have been stable for a long time. TODO: We could upload videos
# and add tests for these error cases.
PERMANENT_ERROR_FRAGMENTS = (
    "private video",
    "video unavailable",
    "removed by the uploader",
    "video has been removed",
    "account associated with this video has been terminated",
    "members-only content",
    "not available in your country",
)

AUDIO_FORMATS = ("opus", "m4a", "mp3")
DEFAULT_AUDIO_FORMAT = "opus"
# A bare number (kbps); See normalize_audio_quality
DEFAULT_MP3_QUALITY = "160"
EXT_BY_FORMAT = {"opus": ".opus", "m4a": ".m4a", "mp3": ".mp3"}

# Per-format yt-dlp stream selection. We prefer the source stream whose codec matches the target so the postprocessor
# can *copy* it (no re-encode); the `/bestaudio/best` tail is the fallback when that stream is missing (then the
# postprocessor transcodes, see download_audio). The output extension is always EXT_BY_FORMAT[audio_format] regardless
# of what got downloaded, because FFmpegExtractAudio normalizes everything to the requested codec.
FORMAT_SELECTION = {
    "opus": "bestaudio[acodec=opus]/bestaudio/best",  # native Opus (webm) -> copy .opus
    "m4a": "bestaudio[ext=m4a]/bestaudio/best",  # native AAC (m4a) -> copy .m4a
    "mp3": "bestaudio/best",  # always a transcode; just take the best source
}
# The source acodec prefix(es) that let each target be a copy rather than a re-encode.
# mp3 is intentionally empty: it's always a transcode by design, so it never warrants a notice.
COPY_SOURCE_BY_FORMAT = {"opus": ("opus",), "m4a": ("mp4a", "aac"), "mp3": ()}

# YouTube changes often, so yt-dlp needs frequent updates; we ship it unpinned and help users refresh it.
YT_DLP_SPEC = "yt-dlp[default]"
DISTRIBUTION_NAME = "youtube-music-dl"


def has_pip() -> bool:
    """
    Whether pip is importable in the running interpreter. True for pip/pipx installs; False for `uv tool` installs; uv
    doesn't put pip in a tool's environment, which is how we tell them apart.
    """
    return importlib.util.find_spec("pip") is not None


def ytdlp_upgrade_argv() -> list[str]:
    """
    The command to refresh yt-dlp, matched to how this tool was installed and targeting the environment whose yt-dlp we
    actually import.

    - pip/pipx installs have pip -> upgrade yt-dlp in place with pip.
    - `uv tool` installs have no pip -> `uv tool upgrade` re-resolves the tool's deps (incl. yt-dlp) to latest.
    """
    if has_pip():
        return [sys.executable, "-m", "pip", "install", "-U", YT_DLP_SPEC]
    uv = shutil.which("uv")
    if uv:
        return [uv, "tool", "upgrade", DISTRIBUTION_NAME]
    # Neither pip nor uv found: return the pip form so callers can still show a concrete command to run.
    return [sys.executable, "-m", "pip", "install", "-U", YT_DLP_SPEC]


def ytdlp_upgrade_command() -> str:
    return " ".join(shlex.quote(a) for a in ytdlp_upgrade_argv())


def outdated_ytdlp_hint() -> str:
    """A hint appended to extraction failures: the usual cause is an out-of-date yt-dlp."""
    return f"If this keeps happening, yt-dlp is probably out of date (YouTube changes frequently). Run `youtube-music-dl upgrade`, or: {ytdlp_upgrade_command()}"  # noqa: E501


class UserError(Exception):
    """A user-facing error carrying a stable machine `code`."""

    code: ErrorCode

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


def normalize_audio_quality(audio_quality: str) -> str:
    """
    Validate and normalize an `--audio-quality` value, failing loudly on junk.

    yt-dlp's `FFmpegExtractAudio` parses quality with `float_or_none`, so a bare "160K" gets silently dropped. yt-dlp's
    own CLI avoids this by stripping the K and validating a positive number. We do the same here, and raise
    `INVALID_ARGS` rather than silently ignore a bogus value (so callers find out before anything is downloaded).

    A number <= 10 is a VBR quality (effective for mp3; opus ignores it); a number > 10 is a kbps bitrate
    (e.g. "160K"/"160" -> 160 kbps). "" means "unset".
    """
    if not audio_quality:
        return ""
    normalized = audio_quality.strip().strip("kK")
    try:
        value = float(normalized)
    except ValueError:
        raise UserError(
            "INVALID_ARGS",
            f"invalid audio quality {audio_quality!r}; expected a bitrate like '160K', or a VBR value 0-10 for mp3",
        ) from None
    if value < 0:
        raise UserError("INVALID_ARGS", f"invalid audio quality {audio_quality!r}; must be non-negative")
    return normalized


class Track(NamedTuple):
    index: int
    status: str  # downloaded | skipped | failed
    title: str
    youtube_video_id: str | None
    url: str | None
    file: str | None
    # Why a track failed, straight from yt-dlp, and whether re-running could ever fix it. Both default to the
    # "nothing to report" values so the many non-failure construction sites stay unchanged.
    reason: str | None = None
    permanent: bool = False


class Outcome(NamedTuple, Generic[T]):
    """One extraction attempt: the value, or None plus the error yt-dlp reported for it."""

    value: T | None
    error: str = ""


class Chapter(NamedTuple):
    title: str | None
    start: float
    end: float


class Ctx(NamedTuple):
    """Shared, per-run configuration passed to the mode handlers."""

    directory: Path
    ext: str
    audio_format: str
    audio_quality: str
    artist: str
    album: str
    patterns: list[str]
    existing: dict[str, list[Path]]


def log(message: str) -> None:
    print(message, file=sys.stderr)


class StderrLogger:
    """
    yt-dlp logger that keeps all of yt-dlp's chatter on stderr, and retains the last error it saw. That last error is
    the only explanation of *why* an extraction failed: yt-dlp runs with `ignoreerrors`, so it reports failure by
    returning None and the reason survives nowhere else. One logger per extraction, so it can't pick up another's error.
    """

    def __init__(self) -> None:
        self.last_error: str = ""

    def debug(self, msg: str) -> None:
        if not msg.startswith("[debug] "):
            log(msg)

    def info(self, msg: str) -> None:
        log(msg)

    def warning(self, msg: str) -> None:
        log(msg)

    def error(self, msg: str) -> None:
        self.last_error = msg
        log(msg)


def js_runtimes_opt() -> dict[str, dict[str, Any]] | None:
    """Return the yt-dlp `js_runtimes` param, or None to accept the default (deno).

    yt-dlp enables only deno by default. If deno is absent but node is present, we
    explicitly select node so YouTube extraction still works.
    """
    if shutil.which("deno"):
        return None
    if shutil.which("node"):
        return {"node": {}}
    return None


def base_opts() -> dict[str, Any]:
    # No "logger" here: each extraction injects its own StderrLogger so it can read back that call's error.
    opts: dict[str, Any] = {
        "ignoreerrors": True,
        "quiet": True,
        "noprogress": True,
    }
    runtimes = js_runtimes_opt()
    if runtimes is not None:
        opts["js_runtimes"] = runtimes
    return opts


def probe_opts(playlist_items: str = "") -> dict[str, Any]:
    # `extract_flat="in_playlist"` lists playlist entries cheaply while still fully
    # extracting a single video (so its chapters are available).
    opts = base_opts()
    opts["extract_flat"] = "in_playlist"
    if playlist_items:
        opts["playlist_items"] = playlist_items
    return opts


def download_opts(target_dir: Path, audio_format: str, audio_quality: str) -> dict[str, Any]:
    """
    Note a non-empty quality forces a re-encode. mp3 is always a transcode anyway, so it gets a default bitrate; opus
    and m4a are left unset by default so their native stream is stream-copied.
    """
    postprocessor: dict[str, str] = {"key": "FFmpegExtractAudio", "preferredcodec": audio_format}
    quality = audio_quality or (DEFAULT_MP3_QUALITY if audio_format == "mp3" else "")
    if quality:
        postprocessor["preferredquality"] = quality
    opts = base_opts()
    # audio only: no need to fetch (and re-mux) video, and it lets the native stream be copied
    opts["format"] = FORMAT_SELECTION[audio_format]
    opts["outtmpl"] = str(target_dir / "%(id)s.%(ext)s")
    opts["postprocessors"] = [postprocessor, {"key": "FFmpegMetadata"}]
    return opts


def is_permanent_failure(error: str) -> bool:
    """Whether yt-dlp's error says the video can never be fetched (vs. throttling, which a retry can clear)."""
    normalized = error.lower()
    return any(fragment in normalized for fragment in PERMANENT_ERROR_FRAGMENTS)


def with_retries(fn: Callable[[], Outcome[T]], description: str) -> Outcome[T]:
    """
    Call `fn` until it succeeds, pausing RETRY_DELAYS_S between tries. Returns early on a failure yt-dlp has told
    us is permanent, so a private or deleted video is reported immediately instead of after the full backoff.
    """
    for delay_s in RETRY_DELAYS_S:
        outcome = fn()
        if outcome.value is not None:
            return outcome
        if is_permanent_failure(outcome.error):
            return outcome
        log(f"{description} failed, retrying in {delay_s:g}s")
        time.sleep(delay_s)
    return fn()


def extraction_failed_message(prefix: str, error: str) -> str:
    """
    Explain a failed extraction. A permanent failure gets yt-dlp's own reason and nothing else; anything else keeps the
    upgrade hint, since an unexplained failure really can mean yt-dlp has fallen behind YouTube. This lets us avoid
    sending someone to run `upgrade` because a video was private.
    """
    if is_permanent_failure(error):
        return f"{prefix}: {error}"
    detail = f" ({error})" if error else ""
    return f"{prefix}{detail}. {outdated_ytdlp_hint()}"


def probe(url: str, opts: dict[str, Any]) -> Outcome[Info]:
    return with_retries(lambda: probe_once(url, opts), f"extracting info for {url}")


def probe_once(url: str, opts: dict[str, Any]) -> Outcome[Info]:
    logger = StderrLogger()
    with youtube_dl.YoutubeDL({**opts, "logger": logger}) as ydl:
        return Outcome(ydl.extract_info(url, download=False), logger.last_error)


def download_audio(
    url: str, target_dir: Path, audio_format: str, audio_quality: str, ext: str
) -> Outcome[tuple[Info, Path]]:
    return with_retries(
        lambda: download_audio_once(url, target_dir, audio_format, audio_quality, ext), f"downloading {url}"
    )


def download_audio_once(
    url: str, target_dir: Path, audio_format: str, audio_quality: str, ext: str
) -> Outcome[tuple[Info, Path]]:
    """Download one video's audio into target_dir. Returns (info, final_path), or None plus yt-dlp's error."""
    logger = StderrLogger()
    opts = {**download_opts(target_dir, audio_format, audio_quality), "logger": logger}
    with youtube_dl.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    if not info:
        return Outcome(None, logger.last_error)
    video_id = info.get("id")
    if not video_id:
        return Outcome(None, logger.last_error)
    path = target_dir / f"{video_id}{ext}"
    if not path.exists():
        return Outcome(None, logger.last_error)
    warn_if_transcoded(info, audio_format, video_id)
    return Outcome((info, path), logger.last_error)


def warn_if_transcoded(info: Info, audio_format: str, video_id: str) -> None:
    """
    Log a stderr note when the requested format's native stream was missing and we had to re-encode. `info["acodec"]` is
    the *source* stream's codec (extract_info reports the selected stream, not the postprocessed output). Should be
    exceedingly rare on YouTube.
    """
    copyable = COPY_SOURCE_BY_FORMAT[audio_format]
    source_acodec = (info.get("acodec") or "").lower()
    if copyable and not source_acodec.startswith(copyable):
        log(f"note: no native {audio_format} stream for {video_id}; re-encoded from {source_acodec or 'source'}")


def finalize(src: Path, directory: Path, index: int, title: str, ext: str) -> Path:
    """Rename a downloaded `<id>.<ext>` file to a clean `NN - Title.<ext>`."""
    dest = directory / f"{index:02d} - {clean_filename(title)}{ext}"
    if src != dest:
        src.replace(dest)
    return dest


def video_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def detect_mode(top: Info, has_chapters_file: bool) -> str:
    """Decide how a URL would be handled: single video (single_songs/chapters) vs playlist."""
    is_single_video = top.get("extractor") == "youtube"
    if is_single_video and not top.get("chapters") and not has_chapters_file:
        return "single_songs"
    if is_single_video:
        return "chapters"
    return "playlist"


def probe_hint(mode: str, has_chapters_file: bool) -> str:
    if mode == "single_songs":
        return "Single video with no chapters. If this is a full album, its tracks may be listed in the description (with timestamps or durations); build a --chapters-file from it and re-run, or the whole video is downloaded as one track. If it really is one song, pass --album."  # noqa: E501
    if mode == "chapters":
        return (
            "Will split this single video with the provided --chapters-file."
            if has_chapters_file
            else "This video has chapters; it will be split into one track per chapter automatically."
        )
    return "This is a playlist; each entry becomes a track."


def probe_urls(urls: list[str], chapters_file: str = "") -> dict[str, Any]:
    """Report what a real run would do for a URL, without downloading (the `--probe` mode)."""
    top, error = probe(urls[0], probe_opts())
    if not top:
        raise UserError("NO_INFO", extraction_failed_message(f"couldn't extract info for {urls[0]}", error))

    mode = detect_mode(top, has_chapters_file=bool(chapters_file))
    entries: list[dict[str, Any]] = []
    if mode == "playlist":
        for i, entry in enumerate(top.get("entries") or [], start=1):
            if entry:
                entries.append({"index": i, "youtube_video_id": entry.get("id"), "title": entry.get("title") or ""})

    return {
        "version": SCHEMA_VERSION,
        "kind": "probe",
        "mode": mode,
        "title": top.get("title"),
        "duration_s": top.get("duration") if mode != "playlist" else None,
        "chapters": [
            {"title": c.get("title"), "start_time": c.get("start_time"), "end_time": c.get("end_time")}
            for c in (top.get("chapters") or [])
        ],
        "entries": entries,
        "description": top.get("description") if mode != "playlist" else None,
        "hint": probe_hint(mode, bool(chapters_file)),
    }


def downloader(
    urls: list[str],
    artist: str = "",
    album: str = "",
    playlist_items: str = "",
    strip_patterns: list[str] | None = None,
    strip_meta: bool = True,
    audio_format: str = DEFAULT_AUDIO_FORMAT,
    audio_quality: str = "",
    chapters_file: str = "",
    output_dir: str = "",
    track_numbers: str = "",
    force: bool = False,
) -> dict[str, Any]:
    if audio_format not in AUDIO_FORMATS:
        raise UserError("INVALID_ARGS", f"invalid audio format {audio_format!r}; must be one of {AUDIO_FORMATS}")
    ext = EXT_BY_FORMAT[audio_format]
    audio_quality = normalize_audio_quality(audio_quality)

    if chapters_file:
        chapters_file = os.path.abspath(os.path.expanduser(chapters_file))
        if not os.path.exists(chapters_file):
            raise UserError("NO_CHAPTERS_FILE", f"no chapters file at {chapters_file}")

    base_dir = Path(os.path.expanduser(output_dir)).resolve() if output_dir else Path.cwd()

    top, error = probe(urls[0], probe_opts(playlist_items))
    if not top:
        raise UserError("NO_INFO", extraction_failed_message(f"couldn't extract info for {urls[0]}", error))

    mode = detect_mode(top, has_chapters_file=bool(chapters_file))

    if mode == "single_songs" and not album:
        raise UserError("ALBUM_REQUIRED", "single-song URL(s) require an album name (--album)")
    album = album or top.get("title") or "album"
    # layout: <output>/<artist>/<album>/NN - Title.ext (artist level dropped if unset)
    artist_dir = clean_filename(artist)
    album_dir = clean_filename(album)
    directory = base_dir / artist_dir / album_dir if artist_dir else base_dir / album_dir
    directory.mkdir(parents=True, exist_ok=True)

    patterns = list(strip_patterns or [])
    if strip_meta:
        patterns.extend(get_strip_meta_patterns(artist, album))

    ctx = Ctx(
        directory=directory,
        ext=ext,
        audio_format=audio_format,
        audio_quality=audio_quality,
        artist=artist,
        album=album,
        patterns=patterns,
        existing={} if force else existing_files_by_id(directory),
    )

    chapters_file_used: str | None = None
    if mode == "playlist":
        tracks = do_playlist(top, ctx, track_numbers)
    elif mode == "single_songs":
        tracks = do_single_songs(urls, ctx, track_numbers)
    else:
        tracks, chapters_file_used = do_chapters(urls[0], top, chapters_file, ctx)

    failed = [t for t in tracks if t.status == "failed"]
    if failed:
        # Only nag about yt-dlp when something failed for a reason an upgrade could plausibly fix.
        if all(t.permanent for t in failed):
            log(f"note: {len(failed)} track(s) failed permanently (see each track's reason); re-running won't help")
        else:
            log(f"note: {len(failed)} track(s) failed; re-running skips what succeeded. {outdated_ytdlp_hint()}")

    return {
        "version": SCHEMA_VERSION,
        "ok": all(t.status != "failed" for t in tracks),
        "mode": mode,
        "album": album,
        "artist": artist,
        "directory": str(directory),
        "format": audio_format,
        "chapters_file": chapters_file_used,
        "tracks": [t._asdict() for t in tracks],
    }


def do_playlist(top: Info, ctx: Ctx, track_numbers: str) -> list[Track]:
    entries = list(top.get("entries") or [])
    tracks_nums = parse_track_numbers(track_numbers)
    if tracks_nums and len(entries) != len(tracks_nums):
        raise UserError(
            "INVALID_ARGS", f"you passed {len(tracks_nums)} track number(s) but the playlist has {len(entries)}"
        )

    total = len(entries)
    results: list[Track] = []
    for i, entry in enumerate(entries):
        index = tracks_nums[i] if tracks_nums else i + 1
        if entry is None:
            results.append(Track(index, "failed", "", None, None, None))
            continue
        video_id = entry.get("id")
        url = video_url(video_id) if video_id else None
        raw_title = entry.get("title") or (video_id or "")
        if video_id and video_id in ctx.existing:
            title = strip(raw_title, ctx.patterns) or raw_title
            results.append(Track(index, "skipped", title, video_id, url, str(ctx.existing[video_id][0])))
            continue
        results.append(download_and_tag(url, index, total, ctx))
    return results


def do_single_songs(urls: list[str], ctx: Ctx, track_numbers: str) -> list[Track]:
    tracks_nums = parse_track_numbers(track_numbers)
    if tracks_nums and len(urls) != len(tracks_nums):
        raise UserError("INVALID_ARGS", f"you passed {len(tracks_nums)} track number(s) and {len(urls)} url(s)")

    total = len(urls)
    results: list[Track] = []
    for i, url in enumerate(urls):
        index = tracks_nums[i] if tracks_nums else i + 1
        info, error = probe(url, probe_opts())
        if not info:
            results.append(Track(index, "failed", "", None, url, None, error or None, is_permanent_failure(error)))
            continue
        video_id = info.get("id")
        raw_title = info.get("title") or (video_id or "")
        if video_id and video_id in ctx.existing:
            title = strip(raw_title, ctx.patterns) or raw_title
            canonical = video_url(video_id)
            results.append(Track(index, "skipped", title, video_id, canonical, str(ctx.existing[video_id][0])))
            continue
        results.append(download_and_tag(url, index, total, ctx))
    return results


def download_and_tag(url: str | None, index: int, total: int, ctx: Ctx) -> Track:
    if not url:
        return Track(index, "failed", "", None, None, None)
    downloaded, error = download_audio(url, ctx.directory, ctx.audio_format, ctx.audio_quality, ctx.ext)
    if downloaded is None:
        return Track(index, "failed", "", None, url, None, error or None, is_permanent_failure(error))
    info, path = downloaded
    video_id = info.get("id")
    raw_title = info.get("title") or (video_id or "")
    title = strip(raw_title, ctx.patterns) or raw_title
    final = finalize(path, ctx.directory, index, title, ctx.ext)
    tag_audio(
        final,
        title=title,
        artist=ctx.artist,
        album=ctx.album,
        tracknumber=f"{index}/{total}",
        youtube_video_id=video_id,
    )
    report_url = video_url(video_id) if video_id else url
    return Track(index, "downloaded", title, video_id, report_url, str(final))


def do_chapters(url: str, top: Info, chapters_file: str, ctx: Ctx) -> tuple[list[Track], str | None]:
    source_id = top.get("id") or ""
    canonical = video_url(source_id) if source_id else url
    if source_id and source_id in ctx.existing:
        files = ctx.existing[source_id]
        return ([Track(i + 1, "skipped", f.stem, source_id, canonical, str(f)) for i, f in enumerate(files)], None)

    with tempfile.TemporaryDirectory(prefix="ymd-source-") as tmp:
        downloaded, error = download_audio(url, Path(tmp), ctx.audio_format, ctx.audio_quality, ctx.ext)
        if downloaded is None:
            message = extraction_failed_message(f"failed to download source video {url}", error)
            raise UserError("DOWNLOAD_FAILED", message)
        info, source_path = downloaded

        if chapters_file:
            raw_chapters = parse_chapters_file(chapters_file)
        else:
            raw_chapters = list(info.get("chapters") or top.get("chapters") or [])

        duration = media_duration_s(source_path)
        chapters = normalize_chapters(raw_chapters, duration)
        normalized_path = write_normalized_chapters(chapters, source_id)
        log(f"\nnormalized chapters written to {normalized_path} (edit and re-run with --chapters-file to adjust):")
        log(normalized_path.read_text())

        total = len(chapters)
        results: list[Track] = []
        for i, chapter in enumerate(chapters):
            index = i + 1
            raw_title = chapter.title or str(index)
            title = clean_filename(strip(raw_title, ctx.patterns) or raw_title)
            dest = ctx.directory / f"{index:02d} - {title}{ctx.ext}"
            try:
                ffmpeg_extract_segment(source_path, chapter.start, chapter.end, dest)
                tag_audio(
                    dest,
                    title=title,
                    artist=ctx.artist,
                    album=ctx.album,
                    tracknumber=f"{index}/{total}",
                    youtube_video_id=source_id,
                )
                results.append(Track(index, "downloaded", title, source_id, canonical, str(dest)))
            except Exception as e:  # report per-chapter failure, keep going
                log(f"failed to split/tag chapter {index} ({title}): {e}")
                results.append(Track(index, "failed", title, source_id, canonical, None))
    return results, str(normalized_path)


def retag(directory: str, artist: str | None = None, album: str | None = None) -> dict[str, Any]:
    """
    Rewrite the artist/album tags on an album's files and move its folder to match.

    `directory` must be an existing album directory (the `<album>` leaf of the tool's `<artist>/<album>` layout)
    containing .opus/.m4a/.mp3 files. Does not re-download or re-tag titles/track numbers. Errors if the destination
    already exists.
    """
    src = Path(os.path.expanduser(directory)).resolve()
    if not src.is_dir():
        raise UserError("INVALID_ARGS", f"not a directory: {src}")
    files = sorted(p for p in src.iterdir() if p.suffix.lower() in SUPPORTED_EXTENSIONS)
    if not files:
        raise UserError("INVALID_ARGS", f"no {'/'.join(SUPPORTED_EXTENSIONS)} files in {src}")
    if artist is None and album is None:
        raise UserError("INVALID_ARGS", "provide --artist and/or --album to change")

    # the tool's layout is <base>/<artist>/<album>; src is the <album> dir
    base = src.parent.parent
    new_artist = artist if artist is not None else src.parent.name
    new_album = album if album is not None else src.name
    dest = base / clean_filename(new_artist) / clean_filename(new_album)

    if dest != src and dest.exists():
        raise UserError(
            "INVALID_ARGS",
            f"destination already exists: {dest}. You likely already have this album there; move or remove it first.",
        )

    if dest != src:
        dest.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dest)
        try:  # tidy up the old artist dir if the move emptied it
            src.parent.rmdir()
        except OSError:
            pass
        files = sorted(p for p in dest.iterdir() if p.suffix.lower() in SUPPORTED_EXTENSIONS)

    for f in files:
        update_tags(f, artist=artist, album=album)

    return {
        "version": SCHEMA_VERSION,
        "ok": True,
        "action": "retag",
        "artist": new_artist,
        "album": new_album,
        "directory": str(dest),
        "files": [{"file": str(f), "youtube_video_id": read_provenance(f)} for f in files],
    }


def media_duration_s(path: Path) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]
    )
    return float(out.decode().strip())


def ffmpeg_extract_segment(source: Path, start: float, end: float, dest: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-ss",
            str(start),
            "-to",
            str(end),
            "-c",
            "copy",
            str(dest),
        ],
        check=True,
        stdout=sys.stderr.fileno(),
        stderr=sys.stderr.fileno(),
    )


def parse_timestamp(value: Any) -> float | None:
    """Parse a chapter time to seconds. Accepts numbers, "SS", "MM:SS", "HH:MM:SS"."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    seconds = 0.0
    try:
        for part in str(value).strip().split(":"):
            seconds = seconds * 60 + float(part)
    except ValueError:
        raise UserError("INVALID_ARGS", f"invalid chapter timestamp {value!r}") from None
    return seconds


def normalize_chapters(chapters: list[dict[str, Any]], duration: float) -> list[Chapter]:
    """Fill in missing start/end times; the final chapter ends at the true duration."""
    result: list[Chapter] = []
    n = len(chapters)
    for i, chapter in enumerate(chapters):
        start = parse_timestamp(chapter.get("start_time"))
        if start is None:
            start = result[i - 1].end if i > 0 else 0.0
        end = parse_timestamp(chapter.get("end_time"))
        if end is None:
            if i < n - 1:
                nxt = parse_timestamp(chapters[i + 1].get("start_time"))
                end = nxt if nxt is not None else duration
            else:
                end = duration
        result.append(Chapter(chapter.get("title"), start, end))
    return result


def write_normalized_chapters(chapters: list[Chapter], source_id: str) -> Path:
    fd, name = tempfile.mkstemp(prefix=f"ymd-chapters-{source_id}-", suffix=".json")
    data = [{"title": c.title, "start_time": c.start, "end_time": c.end} for c in chapters]
    with os.fdopen(fd, "w") as fh:
        json.dump(data, fh, indent=2)
    return Path(name)


def parse_chapters_file(path: str) -> list[dict[str, Any]]:
    text = Path(path).read_text()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log(f"\nfailed to read {path} as JSON, trying as CSV")
        return read_as_csv(path)
    try:
        validate_chapters_file(data)  # array of {title?, start_time?, end_time?}
    except jsonschema.ValidationError as e:
        raise UserError("INVALID_ARGS", f"invalid chapters file {path}: {e.message}") from None
    return data


def read_as_csv(path: str) -> list[dict[str, Any]]:
    with open(path) as fh:
        reader = csv.reader(fh, delimiter=",")
        chapters: list[dict[str, Any]] = [
            {"title": row[0], "start_time": row[1], "end_time": row[2] if len(row) >= 3 else None}
            for row in reader
            if row
        ]
    if not chapters:
        raise UserError("INVALID_ARGS", f"failed to read {path} as CSV")
    return chapters


def get_strip_meta_patterns(artist: str, album: str = "") -> list[str]:
    patterns = [
        rf"^ *\d+\W*(?={re.escape(artist)})",
        rf" *-? *{re.escape(artist)} *-? *",
    ]
    if album:
        patterns.append(rf" *- *{re.escape(album)} *")
        patterns.append(rf" *{re.escape(album)} *- *")
    return patterns


def strip(s: str, patterns: list[str] | None = None) -> str:
    if not patterns:
        return s
    for pattern in patterns:
        s = re.sub(pattern, "", s, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", s).strip()


def clean_filename(name: str) -> str:
    return name.replace("/", "").replace(chr(92), "").replace(chr(0), "").strip()


def parse_track_numbers(s: str) -> list[int]:
    tracks: list[int] = []
    s = s.replace(" ", "")
    if not s:
        return []
    try:
        for rng in s.split(","):
            pair = rng.split("-")
            if len(pair) == 1:
                tracks.append(int(pair[0]))
            else:
                tracks += list(range(int(pair[0]), int(pair[1]) + 1))
    except ValueError as e:
        raise UserError("INVALID_ARGS", f"invalid track numbers {s!r}: {e}") from None
    return tracks
