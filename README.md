# youtube-music-dl

**youtube-music-dl** is an agent-friendly CLI tool that makes it super easy to download and label music from YouTube. It handles single songs, playlists, and full-album videos (it splits them by chapters).

It tags them (title, artist, album, track number) so they're correctly grouped and ordered in your music player, cleans up the song titles, and gives files clean names. Output is Opus by default; `m4a` and `mp3` are also supported. Opus has excellent quality at small sizes, and is copied straight from YouTube's stream without re-encoding.

It's a wrapper around the amazing [yt-dlp](https://github.com/yt-dlp/yt-dlp). It can be used from the command line, in a script, or by an AI agent.

```sh
# Download this Pharoah Sanders album from a single vid, split it by chapters, and label each song
youtube-music-dl SDeuYY3Hi_I -a "Pharoah Sanders" --album Pharoah

# Download "Nilsson Schmilsson" from a single vid, split it by its chapters, and label each song
youtube-music-dl <id> -a "Harry Nilsson" --album "Nilsson Schmilsson"

# Download and label tracks 1-10 of this playlist by "Star Band de Dakar"
youtube-music-dl "https://www.youtube.com/watch?v=...&index=1&list=..." -a "Star Band de Dakar" -p "1-10"

# Download this Lucinda Williams album from a list of single-song URLs/IDs
youtube-music-dl <id_1> <id_2> <id_3> ... -a "Lucinda Williams" --album "Sweet Old World"
```

## Installation

`pip install youtube-music-dl`

### Deps

`youtube-music-dl` needs a few system binaries used by `yt-dlp`:

- `ffmpeg` and `ffprobe` to convert and split audio
  - macOS: `brew install ffmpeg`
  - Ubuntu: `sudo apt install ffmpeg`
- A JavaScript runtime: [Deno](https://deno.com/) recommended, Node also works
  - macOS: `brew install deno`
  - Ubuntu: [see Deno install docs](https://docs.deno.com/runtime/getting_started/installation/)

If a required binary is missing, `youtube-music-dl` tells you with an `error.code` of `NO_FFMPEG` or `NO_JS_RUNTIME`.

It's worth noting that `yt-dlp` occasionally "breaks", for example because YouTube changes something that prevents it from properly downloading videos. In these cases fixes appear quickly. If `youtube-music-dl` suddenly stops working, try running `pip install --upgrade "yt-dlp[default]"` to upgrade `yt-dlp`.

## What it does that plain yt-dlp doesn't

`yt-dlp` can extract audio, embed metadata, and split by chapters on its own. `youtube-music-dl` is a focused convenience layer on top of it that adds:

- **Opinionated one-liner defaults**: makes an artist/album folder, cleans song titles (strips the artist/album out), tags everything, and gives files clean, ordered names.
- **Agent-friendly output**: one JSON object on stdout, a stable error/exit-code contract, idempotent re-runs, and a skill that teaches agents how to run common workflows.
- **Custom timestamp splitting.** Split a single "full album" video at boundaries you supply in a JSON/CSV `--chapters-file`. Useful when there are no real YouTube chapters.
- **Albums from a list of single-song URLs**, tagged with a shared album and sequential track numbers, in one command.
- **Automatic mode detection**: you don't tell it whether the URL is a playlist, a chaptered video, or single songs, it figures it out. It also auto-splits a single video that *does* have chapters, with no extra flag. When driven with an agent, it can download and split albums that don't have chapters, as long as the description has track names and durations.

## Usage

**youtube-music-dl** downloads tracks into an `<artist>/<album>` folder. You can specify the output directory with `$YMD_OUTPUT_DIR` or with `-o`. This makes it easy to browse your music by artist on disk. Run `youtube-music-dl -h` for the full help.

It prints one JSON object to stdout (logs go to stderr), so `youtube-music-dl … 2>/dev/null` gives you clean JSON. Re-runs are idempotent. Tracks already present (matched by an embedded `youtube_video_id` tag) are skipped. Exit code is `0` on success, `2` if some tracks failed, `1` on a fatal error.

### Required Arguments

- `url`: URL or ID of a YouTube playlist, a video with chapters, or one or more single-song URLs
- `-a/--artist`

### Optional Arguments

- `--album`: required for single-song URLs; otherwise defaults to the playlist/video title
- `-p`, `--playlist-items`: playlist items to download; e.g. "1,3-5,7-9,11,12"
- `-t`, `--track-numbers`: track numbers to assign; must be the same length as the items
- `-s`, `--strip-patterns` : extra regex patterns to remove from titles
- `--no-strip-meta`: don't strip the artist/album out of titles
- `-f`, `--audio-format`: **{opus,m4a,mp3}**; default `opus`; see [Audio formats](#audio-formats) below. `opus` and `m4a` copy the native YouTube stream without re-encoding when possible; `mp3` always transcodes
- `-q`, `--audio-quality`: a bitrate like `160K`, or `0`–`9` VBR for mp3; omit for opus/m4a to avoid re-encoding (recommended)
- `--chapters-file`: JSON or CSV file of chapters used to split a single video at custom timestamps; [see these examples](./examples/chapters_file)
- `-o`, `--output-dir`: directory in which the album directory is created; precedence: this flag (even `-o .`) → the `YMD_OUTPUT_DIR` env var → the current directory
- `--force`: re-download tracks even if they're already present
- `--probe`: print what a real run *would* do as JSON, **without downloading**; useful e.g. for deciding whether an album video needs a `--chapters-file`
- `--print-schema`: print the JSON Schemas and exit
- `--print-skill`: print the agent skill and exit

### File names and tags

Tracks are downloaded to `<artist>/<album>/NN - Title.ext` (e.g. `Harry Nilsson/Nilsson Schmilsson/01 - Gotta Get Up.opus`), named cleanly and in order. The artist/album is stripped out of both the title tag (what your player shows) and the filename.

The source video is not lost: it's stored in a `youtube_video_id` tag on each file, which is how re-runs know what's already been downloaded.

### Audio formats

There are three formats, and **the file extension you get is always the format you asked for**. Note that you can set your own default with `YMD_AUDIO_FORMAT`. Pick by where you'll listen:

- **`opus`** (default): the best quality-per-byte, and it's what YouTube stores natively, so it's copied without re-encoding on essentially every video. Plays everywhere except Apple Music and other apps in the Apple ecosystem (but works with mpv, VLC, IINA, Jellyfin, etc).
- **`m4a`**: native AAC in an MP4 container. Choose this e.g. if you live in **Apple Music**, which doesn't play Opus. Copied without re-encoding when an AAC stream is available (it almost always is).
- **`mp3`**: maximum device compatibility (old car stereos, cheap players). Always transcoded, since YouTube never serves mp3.

### Fixing a wrong artist/album with `retag`

Got the artist or album wrong? Fix it without re-downloading:

```sh
youtube-music-dl retag "<album directory>" -a "Charly García"
# or --album "New Name", or both
```

`retag` points at an existing `<artist>/<album>` directory, rewrites the `artist`/`album` tags on its `.opus`/`.m4a`/`.mp3` files, and moves the `<artist>/<album>` folder to match, leaving titles, track numbers, etc untouched. It refuses with `INVALID_ARGS` if the directory has no audio files, or if the destination already exists (you probably already have the corrected album there). Anything more involved than this is a job for a real library manager like [beets](https://beets.io/).

### Env vars

- `YMD_OUTPUT_DIR`: default output directory
  - E.g. set `export YMD_OUTPUT_DIR="$HOME/Music"`
- `YMD_AUDIO_FORMAT`: default audio format (`opus`/`m4a`/`mp3`), used when `-f`/`--audio-format` isn't passed (an explicit `-f` wins)
  - E.g. an Apple-ecosystem user might set `export YMD_AUDIO_FORMAT="m4a"`
- `YMD_AUDIO_QUALITY`: default audio quality, used when `-q`/`--audio-quality` isn't passed (an explicit `-q` wins)
  - E.g. set `export YMD_AUDIO_QUALITY="160K"`

## Use with AI agents

Because the CLI is non-interactive and emits stable JSON, an agent can drive it easily. E.g. "download this album by this artist to `~/Music`", a YouTube URL, or a CSV of albums to fetch one by one. This repo ships a [skill](skills/youtube-music-dl/SKILL.md) that teaches an agent the workflows, the output schema, and the error codes. To use this skill with an agent, copy or symlink it into your agent's skills directory.

The CLI is self-describing, so an agent needs no filesystem paths: `--print-skill` prints the skill, `--print-schema` prints the JSON Schemas, and `--probe <url>` reports the detected mode (playlist, chaptered video, or single song) and the video description **without downloading**, which is e.g. how an agent decides whether a "full album" video needs a generated `--chapters-file`.

## Contributing

Fork the repo and submit a PR. Create an issue if something is missing or broken!

### Development

This project uses [uv](https://docs.astral.sh/uv/) for packaging and development. Run `uv sync` to set things up:

```sh
uv sync
```

By default this creates a virtual environment at `.venv` in the repo root (the standard location `uv` uses) and installs all dependencies into it, including dev tools. `pyrightconfig.json` points `pyright` at this `.venv`, so type checking can resolve `yt-dlp`, `mutagen`, and the other deps.

`uv sync` installs the project as an editable install in `.venv`, so running it through `uv run` always reflects your latest code:

```sh
uv run youtube-music-dl ...
```

Run other tools the same way with `uv run`, e.g. `uv run pyright`, or activate the environment with `source .venv/bin/activate`.

Run `cd .git/hooks && ln -s -f ../../pre-push` to install the `pre-push` hook to ensure you can't push anything that doesn't pass ruff, pyright and pytest.

### Style

Uses [ruff](https://docs.astral.sh/ruff/) for formatting, linting, and import sorting.

- `uv run ruff format .` to format source files in place
- `uv run ruff check .` to lint (add `--fix` to auto-fix)
- `uv run pyright` to type-check
- `uv run pytest` to run the tests

### Install locally

To put a `youtube-music-dl` command on your PATH that tracks the repo, so it always picks up latest code edits:

```sh
uv tool install --editable .
```

Plain `uv tool install .` snapshots the current code instead, so you'd have to re-run `uv tool install . --reinstall` after every edit. Also, remember that you can skip install and simply do `uv run youtube-music-dl ...`, which always reflects the latest code.

## License

[MIT](https://opensource.org/licenses/MIT).

## Thanks

To the maintainers of **yt-dlp**, [Mutagen](https://github.com/quodlibet/mutagen) and **FFmpeg**, and to anyone who doesn't want all that sweet music to go behind ads or a paywall.
