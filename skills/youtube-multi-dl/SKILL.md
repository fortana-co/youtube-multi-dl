---
name: youtube-multi-dl
description: Download and label music albums or playlists from YouTube as tagged audio files (opus by default, or mp3). Use when a user wants to download an album, a playlist, or an "album" video split into per-song tracks — given an album+artist name, a YouTube URL/ID, or a CSV/spreadsheet of albums to fetch. Produces cleanly-named, ID3/Vorbis-tagged files and emits machine-readable JSON.
---

# youtube-multi-dl

A CLI wrapper around `yt-dlp` that downloads audio from YouTube and labels it: clean titles, artist/album/track-number tags, and a `youtube_video_id` provenance tag. It handles playlists, single "album" videos with chapters, and albums assembled from a list of single-song URLs.

## Preconditions (check once, before first use)

Run `youtube-multi-dl --version`. If a command later fails, verify the tooling:

- `ffmpeg` and `ffprobe` on PATH (`brew install ffmpeg` / `apt install ffmpeg`).
- A JavaScript runtime for yt-dlp: **deno** recommended (`brew install deno`), or node. Without one, YouTube extraction fails or is degraded.

If a required binary is missing the CLI exits `1` with an error object whose `error.code` is `NO_FFMPEG` or `NO_JS_RUNTIME` — surface that to the user with the install hint.

## CLI contract (how to consume output)

- **stdout is exactly one JSON object.** All logs/progress go to **stderr**. Always parse stdout as JSON; ignore or forward stderr. Example: `youtube-multi-dl <url> -a "Artist" 2>/dev/null`
- **Exit codes:** `0` = every track downloaded or already present; `2` = some tracks failed (a result object is still emitted — inspect per-track `status`); `1` = fatal error (an error object with a stable `error.code`).
- **Idempotent:** re-running skips tracks already present (matched by the `youtube_video_id` tag). Pass `--force` to re-download.

Success object (run `youtube-multi-dl --print-schema` for the authoritative JSON Schemas of the result, error, and probe outputs):

```json
{
  "version": "1", "ok": true, "mode": "playlist|single_songs|chapters",
  "album": "…", "artist": "…", "directory": "/abs/path", "format": "opus",
  "chapters_file": null,
  "tracks": [
    {"index": 1, "status": "downloaded|skipped|failed",
     "title": "…", "youtube_video_id": "…", "url": "…", "file": "/abs/path.opus"}
  ]
}
```

Error object: `{"version":"1","ok":false,"error":{"code":"…","message":"…"}}`.

## Key options

- `-a/--artist`: required
- `--album`: required only for single-song URLs
- `-p/--playlist-items "1,3-5"`: tracks in playlist to download
- `-t/--track-numbers "1,3-5"`: same length as playlist
- `-f/--audio-format {opus,mp3}`: default `opus`
- `-o/--output-path DIR`: an `<artist>/<album>/` directory is created inside DIR. If omitted, defaults to `$YMD_OUTPUT_DIR` (a music dir the user may have configured), else the current directory. Prefer omitting `-o` when the user hasn't named a location, so their configured default is used; only ask where to save if neither is available.
- `--chapters-file FILE.json`: split a single video at custom timestamps
- `--probe`: report what a real run *would* do (mode, chapters, description) **without downloading**
- `--print-schema` / `--print-skill`: print the JSON Schemas / this document

See all command line options by running `youtube-multi-dl -h`.

## Decide the mode with `--probe` (do this for a single video)

For a bare URL/ID you're unsure about, probe first — it inspects without downloading:

```sh
youtube-multi-dl --probe "<url>" 2>/dev/null
```

It returns `{mode, title, duration_s, chapters, entries, description, hint}`. Use it to pick the workflow:

- `mode: "playlist"` → just download it (workflow 2).
- `mode: "chapters"` (non-empty `chapters`) → download it; it auto-splits (workflow 2).
- `mode: "single_songs"` → **decide**: if it's genuinely one song, download with `--album`; if the `description` reveals it's a full album (a tracklist with timestamps/durations), build a `--chapters-file` from that description and run (workflow 3). Downloading without a chapters file would save the whole video as one track.

## Workflows

### 1. "Download album X by artist Y to DIR"

1. If the artist is unknown and not inferable, ask the user for it.
2. Find the album on YouTube — prefer an official/topic **playlist** or a **full-album video**. Confirm it's the right album/artist before downloading.
3. Run: `youtube-multi-dl "<url>" -a "Y" --album "X" -o "DIR" 2>/dev/null`
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
