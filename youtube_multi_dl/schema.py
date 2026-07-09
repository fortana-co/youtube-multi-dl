"""
JSON Schemas for the youtube-multi-dl CLI, plus validation helpers.

The CLI writes exactly one JSON object to stdout (all human/progress logging goes
to stderr). On success that object conforms to `RESULT_SCHEMA`; on a fatal
precondition/usage error it conforms to `ERROR_SCHEMA`. Tests validate the CLI's
real output against these schemas so the two can never drift.
"""

from typing import Any, Literal, get_args

import jsonschema

SCHEMA_VERSION = "1"

# Machine-readable error codes an agent can branch on. Keep these stable.
ErrorCode = Literal[
    "INVALID_ARGS",  # bad/missing CLI arguments
    "ALBUM_REQUIRED",  # single-song URLs given without --album
    "NO_FFMPEG",  # ffmpeg/ffprobe not on PATH
    "NO_JS_RUNTIME",  # no JavaScript runtime (deno/node) for yt-dlp
    "NO_CHAPTERS_FILE",  # --chapters-file path does not exist
    "NO_INFO",  # yt-dlp could not extract info for the URL
    "DOWNLOAD_FAILED",  # the (single) source download failed
    "INTERRUPTED",  # KeyboardInterrupt
]
ERROR_CODES: tuple[ErrorCode, ...] = get_args(ErrorCode)

TRACK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["index", "status", "title", "youtube_video_id", "url", "file"],
    "properties": {
        "index": {"type": "integer", "minimum": 1},
        "status": {"enum": ["downloaded", "skipped", "failed"]},
        "title": {"type": "string"},
        "youtube_video_id": {"type": ["string", "null"]},
        "url": {"type": ["string", "null"]},
        "file": {"type": ["string", "null"]},
    },
}

RESULT_SCHEMA: dict[str, Any] = {
    "title": "youtube-multi-dl result",
    "type": "object",
    "additionalProperties": False,
    "required": ["version", "ok", "mode", "album", "artist", "directory", "format", "chapters_file", "tracks"],
    "properties": {
        "version": {"const": SCHEMA_VERSION},
        "ok": {"type": "boolean", "description": "true iff no track failed"},
        "mode": {"enum": ["playlist", "single_songs", "chapters"]},
        "album": {"type": "string"},
        "artist": {"type": "string"},
        "directory": {"type": "string", "description": "absolute path to the album directory"},
        "format": {"enum": ["opus", "mp3"]},
        "chapters_file": {
            "type": ["string", "null"],
            "description": "absolute path to the normalized chapters file used for a split, else null",
        },
        "tracks": {"type": "array", "items": TRACK_SCHEMA},
    },
}

ERROR_SCHEMA: dict[str, Any] = {
    "title": "youtube-multi-dl error",
    "type": "object",
    "additionalProperties": False,
    "required": ["version", "ok", "error"],
    "properties": {
        "version": {"const": SCHEMA_VERSION},
        "ok": {"const": False},
        "error": {
            "type": "object",
            "additionalProperties": False,
            "required": ["code", "message"],
            "properties": {
                "code": {"enum": list(ERROR_CODES)},
                "message": {"type": "string"},
            },
        },
    },
}


def validate_result(obj: dict[str, Any]) -> None:
    jsonschema.validate(obj, RESULT_SCHEMA)


def validate_error(obj: dict[str, Any]) -> None:
    jsonschema.validate(obj, ERROR_SCHEMA)


def make_error(code: ErrorCode, message: str) -> dict[str, Any]:
    return {"version": SCHEMA_VERSION, "ok": False, "error": {"code": code, "message": message}}
