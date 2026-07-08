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
import shutil
import sys
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from .downloader import AUDIO_FORMATS, DEFAULT_AUDIO_FORMAT, UserError, downloader
from .schema import ErrorCode, make_error, validate_error, validate_result

if sys.version_info < (3, 12):
    sys.exit("you need at least python3.12 to run youtube-multi-dl")


def get_version() -> str:
    try:
        return version("youtube-multi-dl")
    except PackageNotFoundError:
        return "0.0.0"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="youtube-multi-dl",
        description="Download and label albums/playlists from YouTube. Emits JSON on stdout; logs on stderr.",
    )
    parser.add_argument("-v", "--version", action="store_true", help="print version and exit")
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
    parser.add_argument("-o", "--output-path", default="", help="directory in which the album directory is created")
    parser.add_argument("--force", action="store_true", help="re-download even if a track is already present")
    return parser


def preflight() -> tuple[ErrorCode, str] | None:
    missing = [b for b in ("ffmpeg", "ffprobe") if not shutil.which(b)]
    if missing:
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


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.version:
        emit({"version": get_version()})
        sys.exit(0)
    if not args.url:
        parser.error("at least one url is required")
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
            audio_format=args.audio_format,
            audio_quality=args.audio_quality,
            chapters_file=args.chapters_file,
            output_path=args.output_path,
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
