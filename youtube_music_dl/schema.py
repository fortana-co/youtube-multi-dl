"""
JSON Schemas for the youtube-music-dl CLI, plus validation helpers.

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
    "UPGRADE_FAILED",  # `upgrade` subcommand could not upgrade yt-dlp
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
    "title": "youtube-music-dl result",
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
        "format": {"enum": ["opus", "m4a", "mp3"]},
        "chapters_file": {
            "type": ["string", "null"],
            "description": "absolute path to the normalized chapters file used for a split, else null",
        },
        "tracks": {"type": "array", "items": TRACK_SCHEMA},
    },
}

ERROR_SCHEMA: dict[str, Any] = {
    "title": "youtube-music-dl error",
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


# --- probe (dry-run) output --------------------------------------------------
# `--probe` reports what a real run *would* do for a URL, without downloading, so
# an agent can decide (e.g. build a --chapters-file for an album video whose
# tracklist is only in the description) before committing to a download.

PROBE_CHAPTER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": ["string", "null"]},
        "start_time": {"type": ["number", "string", "null"]},
        "end_time": {"type": ["number", "string", "null"]},
    },
}

PROBE_ENTRY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["index", "youtube_video_id", "title"],
    "properties": {
        "index": {"type": "integer", "minimum": 1},
        "youtube_video_id": {"type": ["string", "null"]},
        "title": {"type": "string"},
    },
}

PROBE_SCHEMA: dict[str, Any] = {
    "title": "youtube-music-dl probe",
    "type": "object",
    "additionalProperties": False,
    "required": ["version", "kind", "mode", "title", "duration_s", "chapters", "entries", "description", "hint"],
    "properties": {
        "version": {"const": SCHEMA_VERSION},
        "kind": {"const": "probe"},
        "mode": {"enum": ["playlist", "single_songs", "chapters"]},
        "title": {"type": ["string", "null"]},
        "duration_s": {"type": ["number", "null"], "description": "length of a single video, else null"},
        "chapters": {
            "type": "array",
            "items": PROBE_CHAPTER_SCHEMA,
            "description": "chapters detected in a single video",
        },
        "entries": {"type": "array", "items": PROBE_ENTRY_SCHEMA, "description": "playlist entries, else empty"},
        "description": {"type": ["string", "null"], "description": "video description (parse it for a tracklist)"},
        "hint": {"type": "string", "description": "what a real run would do, and what to consider"},
    },
}


# --- chapters file (input) ---------------------------------------------------
# The JSON form of a --chapters-file: an array of chapters. Times are seconds or
# "MM:SS"/"HH:MM:SS" strings. All fields are optional (a missing title becomes the
# track number; a missing start/end is inferred from neighbours / the true
# duration), but unknown keys are rejected to catch mistakes like "start" for
# "start_time". CSV files are not covered by this schema.

CHAPTERS_FILE_SCHEMA: dict[str, Any] = {
    "title": "youtube-music-dl chapters file",
    "type": "array",
    "items": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title": {"type": "string"},
            "start_time": {"type": ["number", "string"]},
            "end_time": {"type": ["number", "string"]},
        },
    },
}


# --- retag output ------------------------------------------------------------
# `retag <dir>` rewrites the artist/album tags on an album's files and moves the
# folder to match, without re-downloading.

RETAG_FILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["file", "youtube_video_id"],
    "properties": {
        "file": {"type": "string"},
        "youtube_video_id": {"type": ["string", "null"]},
    },
}

RETAG_SCHEMA: dict[str, Any] = {
    "title": "youtube-music-dl retag result",
    "type": "object",
    "additionalProperties": False,
    "required": ["version", "ok", "action", "artist", "album", "directory", "files"],
    "properties": {
        "version": {"const": SCHEMA_VERSION},
        "ok": {"const": True},
        "action": {"const": "retag"},
        "artist": {"type": "string"},
        "album": {"type": "string"},
        "directory": {"type": "string", "description": "absolute path to the (possibly moved) album directory"},
        "files": {"type": "array", "items": RETAG_FILE_SCHEMA},
    },
}


# --- upgrade output ----------------------------------------------------------
# `upgrade` upgrades yt-dlp in the current environment (YouTube changes often, so
# yt-dlp needs frequent updates). `from`/`to` are the yt-dlp versions before/after.

UPGRADE_SCHEMA: dict[str, Any] = {
    "title": "youtube-music-dl upgrade result",
    "type": "object",
    "additionalProperties": False,
    "required": ["version", "ok", "action", "package", "from", "to"],
    "properties": {
        "version": {"const": SCHEMA_VERSION},
        "ok": {"const": True},
        "action": {"const": "upgrade"},
        "package": {"const": "yt-dlp"},
        "from": {"type": ["string", "null"], "description": "yt-dlp version before the upgrade, or null if unknown"},
        "to": {"type": ["string", "null"], "description": "yt-dlp version after the upgrade, or null if unknown"},
    },
}


def validate_result(obj: dict[str, Any]) -> None:
    jsonschema.validate(obj, RESULT_SCHEMA)


def validate_upgrade(obj: dict[str, Any]) -> None:
    jsonschema.validate(obj, UPGRADE_SCHEMA)


def validate_chapters_file(obj: Any) -> None:
    jsonschema.validate(obj, CHAPTERS_FILE_SCHEMA)


def validate_retag(obj: dict[str, Any]) -> None:
    jsonschema.validate(obj, RETAG_SCHEMA)


def validate_probe(obj: dict[str, Any]) -> None:
    jsonschema.validate(obj, PROBE_SCHEMA)


def validate_error(obj: dict[str, Any]) -> None:
    jsonschema.validate(obj, ERROR_SCHEMA)


def make_error(code: ErrorCode, message: str) -> dict[str, Any]:
    return {"version": SCHEMA_VERSION, "ok": False, "error": {"code": code, "message": message}}
