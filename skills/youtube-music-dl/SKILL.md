---
name: youtube-music-dl
description: Download and label music albums or playlists from YouTube as tagged audio files (opus by default; m4a and mp3 also supported). Use when a user wants to download an album, a playlist, or an "album" video split into per-song tracks — given an album+artist name, a YouTube URL/ID, or a CSV/spreadsheet of albums to fetch. Produces cleanly-named, tagged files and emits machine-readable JSON.
---

# youtube-music-dl

A CLI wrapper around `yt-dlp` that downloads audio from YouTube and labels it: clean titles, artist/album/track-number tags, and a `youtube_video_id` provenance tag. It handles playlists, single "album" videos with chapters, and albums assembled from a list of single-song URLs.

## Preconditions (check once, before first use)

Run `youtube-music-dl --version`. If a command later fails, verify the tooling:

- `ffmpeg` and `ffprobe` on PATH (`brew install ffmpeg` / `apt install ffmpeg`).
- A JavaScript runtime for yt-dlp: **deno** recommended (`brew install deno`), or node. Without one, YouTube extraction fails or is degraded.

If a required binary is missing the CLI exits `1` with an error object whose `error.code` is `NO_FFMPEG` or `NO_JS_RUNTIME` — surface that to the user with the install hint.

**Stale yt-dlp is the usual cause of sudden extraction failures.** YouTube changes often, so if a run fails with `NO_INFO`/`DOWNLOAD_FAILED` (or tracks fail unexpectedly), yt-dlp is probably out of date. The error message says so and includes the fix; you can run `youtube-music-dl upgrade` to update yt-dlp in place (prints before/after versions as JSON), then retry. It automatically uses the right mechanism for how the tool was installed (pip, or `uv tool upgrade` for uv installs).

## CLI contract (how to consume output)

- **stdout is exactly one JSON object.** All logs/progress go to **stderr**. Always parse stdout as JSON; ignore or forward stderr. Example: `youtube-music-dl <url> -a "Artist" 2>/dev/null`
- **Exit codes:** `0` = every track downloaded or already present; `2` = some tracks failed (a result object is still emitted — inspect per-track `status`); `1` = fatal error (an error object with a stable `error.code`).
- **Idempotent:** re-running skips tracks already present (matched by the `youtube_video_id` tag). Pass `--force` to re-download.
- **On exit `2`, re-run the identical command.** YouTube throttles bursts of requests, so a track can fail once and succeed moments later; the tool retries in-process, but heavier rate limiting still gets through. Re-running only refetches what's missing. Don't diagnose a failure with `--probe` — a probe hits the same API and gets throttled too, so a failed probe can't tell a dead video from a rate-limited one. Read `tracks[].permanent` instead: `true` means private, deleted, or region-blocked, and no amount of re-running will help (`tracks[].reason` carries yt-dlp's explanation) — drop that track via `-p/--playlist-items` and move on. Only tracks with `permanent: false` are worth retrying.

Success object (run `youtube-music-dl --print-schema` for the authoritative JSON Schemas of the result, error, and probe outputs):

```json
{
  "version": "1", "ok": true, "mode": "playlist|single_songs|chapters",
  "album": "…", "artist": "…", "directory": "/abs/path", "format": "opus",
  "chapters_file": null,
  "tracks": [
    {"index": 1, "status": "downloaded|skipped|failed",
     "title": "…", "youtube_video_id": "…", "url": "…", "file": "/abs/path.opus",
     "reason": "yt-dlp's error, if this track failed", "permanent": false}
  ]
}
```

Error object: `{"version":"1","ok":false,"error":{"code":"…","message":"…"}}`.

## Key options

- `-a/--artist`: required
- `--album`: required only for single-song URLs
- `-p/--playlist-items "1,3-5"`: tracks in playlist to download
- `-t/--track-numbers "1,3-5"`: same length as playlist
- `-f/--audio-format {opus,m4a,mp3}`: default `opus` (or `$YMD_AUDIO_FORMAT`). The file extension always matches the format. `opus` and `m4a` copy YouTube's native stream without re-encoding when possible; `mp3` always transcodes.
- `-o/--output-dir DIR`: an `<artist>/<album>/` directory is created inside DIR. If omitted, defaults to `$YMD_OUTPUT_DIR` (a music dir the user may have configured), else the current directory. Prefer omitting `-o` when the user hasn't named a location, so their configured default is used; only ask where to save if neither is available.
- `--chapters-file FILE.json`: split a single video at custom timestamps (JSON files are validated against the `chapters_file` schema from `--print-schema`; malformed ones fail with `INVALID_ARGS`)
- `--probe`: report what a real run *would* do (mode, chapters, description) **without downloading**
- `--print-schema` / `--print-skill`: print the JSON Schemas (`result`, `error`, `probe`, `retag`, `upgrade`, `chapters_file`) / this document

See all command line options by running `youtube-music-dl -h`.

## Fix tags without re-downloading: `retag`

If the user got the artist or album wrong, don't re-download — use the `retag` subcommand. It rewrites the artist/album tags on the album's files and moves the `<artist>/<album>` folder to match. Titles, track numbers, and provenance are left intact.

```sh
youtube-music-dl retag "<existing album directory>" -a "New Artist" --album "New Album"
```

Point it at the existing `<artist>/<album>` directory (the one holding the `.opus`/`.m4a`/`.mp3` files). Pass `-a` and/or `--album` — whichever changed. It errors with `INVALID_ARGS` if the directory has no audio files, or if the destination already exists (which usually means the corrected album is already there). Output conforms to the `retag` schema.

## Decide the mode with `--probe` (do this for a single video)

For a bare URL/ID you're unsure about, probe first — it inspects without downloading:

```sh
youtube-music-dl --probe "<url>" 2>/dev/null
```

It returns `{mode, title, duration_s, chapters, entries, description, hint}`. Use it to pick the workflow:

- `mode: "playlist"` → just download it (workflow 2).
- `mode: "chapters"` (non-empty `chapters`) → download it; it auto-splits (workflow 2).
- `mode: "single_songs"` → **decide**: if it's genuinely one song, download with `--album`; if the `description` reveals it's a full album (a tracklist with timestamps/durations), build a `--chapters-file` from that description and run (workflow 3). Downloading without a chapters file would save the whole video as one track.

## Workflows

### 1. "Download album X by artist Y to DIR"

1. If the artist is unknown and not inferable, ask the user for it.
2. Find the album on YouTube — prefer an official/topic **playlist** or a **full-album video**. Confirm it's the right album/artist before downloading.
3. Run: `youtube-music-dl "<url>" -a "Y" --album "X" -o "DIR" 2>/dev/null`
4. Parse the JSON; confirm `ok` and that each `tracks[].file` exists. Report the `directory` and any `failed` tracks to the user.

### 2. A YouTube URL/ID the user supplies

Run directly with `-a`. The tool auto-detects the mode:

- A **playlist** URL → each entry becomes a track;
- A single video **with chapters** → auto-split into per-chapter tracks;
- One or more single-song URLs → an album (requires `--album`).

### 3. A single "album" video whose songs are only in the description

`--probe` reports this case as `mode: "single_songs"` with an empty `chapters` array but a `description` containing a tracklist. Build a chapters file from that description and pass it with `--chapters-file`:

- Parse the tracklist. If it gives **cumulative timestamps** (`0:00 Song A`), use them as `start_time`. If it gives **durations** (`Song A [2:24]`), **accumulate** them into cumulative start times (first at 0).
- Write JSON: `[{"title": "Song A", "start_time": 0}, {"title": "Song B", "start_time": 144}, …]` (`end_time` is optional; omit it and each track runs to the next start, the last to the true end). CSV `title,start_time,end_time` per row also works.
- Run with `--chapters-file`. The tool writes a **normalized** chapters file to a temp path and echoes it on stderr — show the user that path so they can tweak boundaries and re-run.

### 4. A CSV/spreadsheet of albums to download

Iterate rows one at a time. For each: run workflow 1, parse the JSON result, and mark the row done on `ok == true` (else record the error/failed tracks and move on). Re-runs are safe/idempotent, so the batch can be resumed.
