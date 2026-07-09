# youtube-multi-dl

> [!IMPORTANT]
> **`youtube-multi-dl` has been renamed to [`youtube-music-dl`](https://github.com/fortana-co/youtube-music-dl) and is no longer maintained under this name.**
> It's the same tool by the same maintainer — the new name just better reflects its focus. Please switch:
>
> ```sh
> pip uninstall youtube-multi-dl && pip install youtube-music-dl
> ```
>
> This `3.1.0` release still works as documented, but every run prints a reminder to migrate. All future development happens in [`youtube-music-dl`](https://github.com/fortana-co/youtube-music-dl).

**youtube-multi-dl** makes it super easy to download and label music from YouTube. It handles single songs, [playlists](https://www.youtube.com/watch?v=PlnanwD_vS0&index=1&list=PLcOYKKFxnwAdGh4NCgpXq_FNQoZKL6xWM), and [single-song](https://www.youtube.com/watch?v=SDeuYY3Hi_I) [albums](https://www.youtube.com/watch?v=eTYushgUR00) (it splits them by chapters).

It tags them (title, artist, album, track number) so they're correctly grouped and ordered in whatever music player you use, cleans up the song titles, and gives files clean names. Output is [Opus](https://opus-codec.org/) by default (excellent quality at small sizes, and copied straight from YouTube's stream without re-encoding when possible) or mp3.

It's a wrapper around the amazing [yt-dlp](https://github.com/yt-dlp/yt-dlp), built to be as simple as possible to use from the command line, in a script, or by an AI agent. It prints a single JSON object describing what it did.

```sh
# Download and label tracks 1-10 of this playlist by "Star Band de Dakar"
youtube-multi-dl "https://www.youtube.com/watch?v=PlnanwD_vS0&index=1&list=PLcOYKKFxnwAdGh4NCgpXq_FNQoZKL6xWM" -a "Star Band de Dakar" -p "1-10"

# Download "Nilsson Schmilsson" from a single vid, split it by chapters, and label each song
youtube-multi-dl eTYushgUR00 -a "Harry Nilsson" --album "Nilsson Schmilsson"

# Download this Lucinda Williams album from a list of single-song URLs/IDs
youtube-multi-dl vWyXoGUdj4U 9R_dkP2duog qAJ8OCqe0v4 qWJCu3d6EX0 dPr0Iyh0z60 4VMUjcQ2ggs haUHiHVTvtg IOCPe_ff2RE ihuPM-xiCqY pjYxBxGSNnY HrSEeNE_Uzw cpP11qYuhg8 -a "Lucinda Williams" --album "Sweet Old World"

# Download this Pharoah Sanders album from a single vid, split it by chapters, and label each song; youtube-multi-dl guesses at the album name from the video metadata
youtube-multi-dl SDeuYY3Hi_I -a "Pharoah Sanders"
```

## Installation

`pip install youtube-multi-dl`

### Deps

`youtube-multi-dl` needs a few system binaries (used by `yt-dlp`):

- **[FFmpeg](https://www.ffmpeg.org/)** and `ffprobe` to convert and split audio
  - **macOS**: `brew install ffmpeg`
  - **Ubuntu**: `sudo apt install ffmpeg`
- **A JavaScript runtime**: modern YouTube requires one for extraction; [Deno](https://deno.com/) is recommended (Node also works)
  - **macOS**: `brew install deno`
  - **Ubuntu**: [see Deno install docs](https://docs.deno.com/runtime/getting_started/installation/)

If a required binary is missing, `youtube-multi-dl` tells you (with an `error.code` of `NO_FFMPEG` or `NO_JS_RUNTIME`) instead of failing cryptically.

It's worth noting that `yt-dlp` occasionally "breaks", for example because YouTube changes something that prevents it from properly downloading videos. In these cases fixes appear quickly. If `youtube-multi-dl` suddenly stops working, try running `pip install --upgrade "yt-dlp[default]"` to upgrade `yt-dlp`.

## What it does that plain yt-dlp doesn't

`yt-dlp` can extract audio, embed metadata, and split by chapters on its own. `youtube-multi-dl` is a focused convenience layer on top of it that adds:

- **Custom-timestamp splitting.** Split a single "full album" video at boundaries you supply in a JSON/CSV `--chapters-file`. Useful when the tracklist is only in the description and there are no real YouTube chapters. yt-dlp can only split by chapters that already exist.
- **Albums from a list of single-song URLs**, tagged with a shared album and sequential track numbers, in one command.
- **Opinionated one-liner defaults**: makes an album folder, cleans song titles (strips the artist/album out), tags everything, and gives files clean, ordered names.
- **Automatic mode detection**: you don't tell it whether the URL is a playlist, a chaptered video, or single songs, it figures it out. It also auto-splits a single video that *does* have chapters, with no extra flag. When driven with an agent, it can download albums that don't have chapters, as long as the description has track names and durations, or if these are supplied by the user.
- **Agent-friendly output**: one JSON object on stdout, a stable error/exit-code contract, idempotent re-runs, and a skill that teaches agents how to run common workflows.

## Usage

**youtube-multi-dl** downloads tagged tracks into an `<artist>/<album>/` folder, created inside your current directory (or the `-o` path), so you can browse your music by artist on disk. Run `youtube-multi-dl -h` for the full help.

It prints **one JSON object to stdout** (logs go to stderr), so `youtube-multi-dl … 2>/dev/null | jq` gives you clean JSON. Re-runs are **idempotent**. Tracks already present (matched by an embedded `youtube_video_id` tag) are skipped. Exit code is `0` on success, `2` if some tracks failed, `1` on a fatal error.

### Required Arguments

- `url`: URL or ID of a YouTube playlist, a video with chapters, or one or more single-song URLs
- `-a/--artist` ARTIST

### Optional Arguments

- `--album`: required for single-song URLs; otherwise defaults to the playlist/video title
- `-p`, `--playlist-items`: playlist items to download; e.g. "1,3-5,7-9,11,12"
- `-t`, `--track-numbers`: track numbers to assign; must be the same length as the items
- `-s`, `--strip-patterns` : extra regex patterns to remove from titles
- `--no-strip-meta`: don't strip the artist/album out of titles
- `-f`, `--audio-format`: **{opus,mp3}**; default `opus`; Opus is copied from YouTube's stream without re-encoding when possible; mp3 is for maximum device compatibility
- `-q`, `--audio-quality`: a bitrate like `160K`, or `0`–`9` VBR for mp3; Omit for opus to avoid re-encoding (recommended)
- `--chapters-file`: JSON or CSV file of chapters used to split a single video at custom timestamps; [see these examples](./examples/chapters_file)
- `-o`, `--output-path`: directory in which the album directory is created; Precedence: this flag (even `-o .`) → the `YMD_OUTPUT_DIR` env var → the current directory
- `--force`: re-download tracks even if they're already present
- `--probe`: print what a real run *would* do (mode, chapters, description) as JSON, **without downloading** — useful for deciding whether an album video needs a `--chapters-file`
- `--print-schema` / `--print-skill`: print the JSON Schemas / the agent skill and exit

### File names and tags

Tracks land at `<artist>/<album>/NN - Title.ext` (e.g. `Harry Nilsson/Nilsson Schmilsson/01 - Gotta Get Up.opus`), named cleanly and in order. The artist/album is stripped out of both the **title tag** (what your player shows) and the filename. The source video is not lost: it's stored in a `youtube_video_id` tag on each file (yt-dlp also embeds the source URL), which is how re-runs know what's already been downloaded.

### Env vars

- `YMD_OUTPUT_DIR`: default output directory
  - E.g. set `export YMD_OUTPUT_DIR="$HOME/Music"`

## Use with AI agents

Because the CLI is non-interactive and emits schema-stable JSON, an agent can drive it directly. E.g. "download this album by this artist to `~/Music`", a YouTube URL, or a CSV of albums to fetch one by one. This repo ships a [skill](skills/youtube-multi-dl/SKILL.md) that teaches an agent the workflows, the output schema, and the error codes. To use this skill with an agent, copy or symlink it into your agent's skills directory.

The CLI is self-describing, so an agent needs no filesystem paths: `--print-skill` prints the skill, `--print-schema` prints the JSON Schemas, and `--probe <url>` reports the detected mode (playlist / chaptered video / single song) and the video description **without downloading** — which is how an agent decides whether a "full album" video needs a generated `--chapters-file`.

## Contributing

Fork the repo and submit a PR. Create an issue if something is broken!

### Development

This project uses [uv](https://docs.astral.sh/uv/) for packaging and development. Run `uv sync` to set things up:

```sh
uv sync
```

By default this creates a virtual environment at `.venv` in the repo root (the standard location `uv` uses) and installs all dependencies into it, including dev tools (`ruff`, `pyright`). `pyrightconfig.json` points `pyright` at this `.venv`, so type checking can resolve `yt-dlp`, `mutagen`, and the other deps without any extra configuration.

`uv sync` installs the project as an **editable** install in `.venv`, so running it through `uv run` always reflects your latest code — no reinstall step:

```sh
uv run youtube-multi-dl SDeuYY3Hi_I -a "Pharoah Sanders"
```

Note that `python -m youtube_multi_dl.command_line ...` works too. Run other tools the same way with `uv run`, e.g. `uv run pyright`, or activate the environment with `source .venv/bin/activate`.

Run `cd .git/hooks && ln -s -f ../../pre-push` to add the `pre-push` hook to ensure you can't push anything that doesn't pass ruff, pyright and pytest.

### Style

Uses [ruff](https://docs.astral.sh/ruff/) for formatting, linting, and import sorting.

- `uv run ruff format .` to format source files in place
- `uv run ruff check .` to lint (add `--fix` to auto-fix)
- `uv run pyright` to type-check
- `uv run pytest` to run the tests

### Release/Deploy to PyPI

```sh
uv build
uv publish
```

### Install locally

To put a `youtube-multi-dl` command on your PATH that **tracks the repo** — so it always picks up later code edits — install it editable:

```sh
uv tool install --editable .
```

Plain `uv tool install .` snapshots the current code instead, so you'd have to re-run `uv tool install . --reinstall` after every edit. Also, remember that you can skip install and simply do `uv run youtube-multi-dl ...`, which always reflects the latest code.

## License

This code is licensed under the [MIT License](https://opensource.org/licenses/MIT).

## Thanks

To the maintainers of **yt-dlp**, [Mutagen](https://github.com/quodlibet/mutagen) and **FFmpeg**, and to anyone who doesn't want all that sweet music to go behind ads or a paywall.
