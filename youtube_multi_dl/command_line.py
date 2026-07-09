"""
Command-line entry point.

Contract for programmatic/agent use:

- Exactly one JSON object is written to **stdout**. All logging/progress goes to
  **stderr**. So `youtube-multi-dl ... 2>/dev/null | jq` yields clean JSON.
- On success stdout conforms to `schema.RESULT_SCHEMA`; on a fatal error it
  conforms to `schema.ERROR_SCHEMA`.
- Exit codes: `0` = all tracks downloaded/skipped, `2` = some tracks failed
  (a result object is still emitted), `1` = fatal error (an error object is
  emitted). The tool is always non-interactive; re-runs are idempotent (already
  downloaded videos are skipped) unless `--force` is given.
"""

import argparse
import json
import os
import shutil
import sys
from importlib.metadata import PackageNotFoundError, version
from importlib.resources import files
from pathlib import Path
from typing import Any

from .downloader import AUDIO_FORMATS, DEFAULT_AUDIO_FORMAT, UserError, downloader, probe_urls
from .schema import (
    ERROR_SCHEMA,
    PROBE_SCHEMA,
    RESULT_SCHEMA,
    ErrorCode,
    make_error,
    validate_error,
    validate_probe,
    validate_result,
)

if sys.version_info < (3, 12):
    sys.exit("you need at least python3.12 to run youtube-multi-dl")


def get_version() -> str:
    try:
        return version("youtube-multi-dl")
    except PackageNotFoundError:
        return "0.0.0"


OUTPUT_DIR_ENV = "YMD_OUTPUT_DIR"


def resolve_output_path(cli_value: str) -> str:
    """
    Resolve where the album directory goes.

    Precedence: an explicit `-o` wins; otherwise fall back to ``$YMD_OUTPUT_DIR``; otherwise `""` (the current
    directory).
    """
    return cli_value or os.environ.get(OUTPUT_DIR_ENV, "")


def read_skill() -> str:
    """Return the SKILL.md text. Packaged with the wheel; falls back to the repo in dev."""
    packaged = files("youtube_multi_dl").joinpath("SKILL.md")
    if packaged.is_file():
        return packaged.read_text(encoding="utf-8")
    dev = Path(__file__).resolve().parent.parent / "skills" / "youtube-multi-dl" / "SKILL.md"
    return dev.read_text(encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="youtube-multi-dl",
        description="Download and label albums/playlists from YouTube. Emits JSON on stdout; logs on stderr.",
    )
    parser.add_argument("-v", "--version", action="store_true", help="print version and exit")
    parser.add_argument("--print-skill", action="store_true", help="print the agent skill (SKILL.md) and exit")
    parser.add_argument("--print-schema", action="store_true", help="print the JSON Schemas for the output and exit")
    parser.add_argument(
        "--probe",
        action="store_true",
        help="report what a real run would do for the URL (mode, chapters, description) without downloading",
    )
    parser.add_argument(
        "url", nargs="*", help="URL/ID of a YouTube playlist, a video with chapters, or one or more single-song URLs"
    )
    parser.add_argument("-a", "--artist", help="artist(s)")
    parser.add_argument(
        "--album", default="", help="album; defaults to the playlist/video title (required for single-song URLs)"
    )
    parser.add_argument("-p", "--playlist-items", default="", help='playlist items to download, e.g. "1,3-5,7-9"')
    parser.add_argument("-t", "--track-numbers", default="", help="track numbers to assign; same length as the items")
    parser.add_argument("-s", "--strip-patterns", nargs="+", help="extra regex patterns to remove from titles")
    parser.add_argument("--no-strip-meta", action="store_true", help="don't remove artist and album names from titles")
    parser.add_argument(
        "-f",
        "--audio-format",
        choices=AUDIO_FORMATS,
        default=DEFAULT_AUDIO_FORMAT,
        help=f"audio format (default {DEFAULT_AUDIO_FORMAT!r}); opus copies YouTube's stream when possible",
    )
    parser.add_argument(
        "-q",
        "--audio-quality",
        default="",
        help="audio quality; a bitrate like 160K, or 0-9 VBR for mp3. Omit for opus to avoid re-encoding.",
    )
    parser.add_argument("--chapters-file", default="", help="JSON or CSV file of chapters to split a single video by")
    parser.add_argument(
        "-o",
        "--output-path",
        default="",
        help=f"directory in which the album directory is created; defaults to ${OUTPUT_DIR_ENV}, else the current dir",
    )
    parser.add_argument("--force", action="store_true", help="re-download even if a track is already present")
    return parser


def preflight(need_ffmpeg: bool = True) -> tuple[ErrorCode, str] | None:
    missing = [b for b in ("ffmpeg", "ffprobe") if not shutil.which(b)]
    if need_ffmpeg and missing:
        return (
            "NO_FFMPEG",
            f"missing required binaries: {', '.join(missing)}. Install ffmpeg (e.g. `brew install ffmpeg`).",
        )
    if not (shutil.which("deno") or shutil.which("node")):
        return (
            "NO_JS_RUNTIME",
            "no JavaScript runtime found; YouTube extraction needs one. Install deno (e.g. `brew install deno`).",
        )
    return None


def emit(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, indent=2))


def fail(code: ErrorCode, message: str) -> None:
    error = make_error(code, message)
    validate_error(error)
    emit(error)
    sys.exit(1)


DEPRECATION_NOTICE = """\

  ┌────────────────────────────────────────────────────────────────────┐
  │  youtube-multi-dl has been renamed to youtube-music-dl and is NO   │
  │  LONGER MAINTAINED under this name. Same tool, same maintainer —   │
  │  just a clearer name. Please switch:                               │
  │                                                                    │
  │      pip install youtube-music-dl                                  │
  │                                                                    │
  │  https://github.com/fortana-co/youtube-music-dl                    │
  └────────────────────────────────────────────────────────────────────┘

"""


def print_deprecation_notice() -> None:
    # stderr, so the stdout JSON contract is unaffected for scripts/agents
    print(DEPRECATION_NOTICE, file=sys.stderr)


def main() -> None:
    print_deprecation_notice()
    parser = build_parser()
    args = parser.parse_args()

    if args.version:
        emit({"version": get_version()})
        sys.exit(0)
    if args.print_skill:
        print(read_skill().strip())
        sys.exit(0)
    if args.print_schema:
        emit({"result": RESULT_SCHEMA, "error": ERROR_SCHEMA, "probe": PROBE_SCHEMA})
        sys.exit(0)
    if not args.url:
        parser.error("at least one url is required")

    if args.probe:
        # probe only inspects (no download), so it doesn't need ffmpeg
        precondition = preflight(need_ffmpeg=False)
        if precondition is not None:
            fail(*precondition)
        try:
            info = probe_urls(args.url, chapters_file=args.chapters_file)
        except UserError as e:
            fail(e.code, str(e))
        except KeyboardInterrupt:
            fail("INTERRUPTED", "interrupted")
        validate_probe(info)
        emit(info)
        sys.exit(0)

    if not args.artist:
        parser.error("the following argument is required: -a/--artist")

    precondition = preflight()
    if precondition is not None:
        fail(*precondition)

    try:
        result = downloader(
            urls=args.url,
            artist=args.artist,
            album=args.album,
            playlist_items=args.playlist_items,
            strip_patterns=args.strip_patterns,
            strip_meta=not args.no_strip_meta,
            audio_format=args.audio_format,
            audio_quality=args.audio_quality,
            chapters_file=args.chapters_file,
            output_path=resolve_output_path(args.output_path),
            track_numbers=args.track_numbers,
            force=args.force,
        )
    except UserError as e:
        fail(e.code, str(e))
    except KeyboardInterrupt:
        fail("INTERRUPTED", "interrupted")

    validate_result(result)
    emit(result)
    sys.exit(0 if result["ok"] else 2)


if __name__ == "__main__":
    main()
