import csv
import glob
import json
import os
import re
import subprocess
import sys
from typing import Any, NamedTuple, TypedDict

import yt_dlp
from mutagen.easyid3 import EasyID3

# yt-dlp's `extract_info`/`YoutubeDL` are effectively dynamic; treat as untyped.
youtube_dl: Any = yt_dlp

# yt-dlp returns richly-nested, loosely-specified dicts; alias for readability.
Info = dict[str, Any]
# yt-dlp `YoutubeDL` options.
Opts = dict[str, Any]


class Chapter(TypedDict, total=False):
    title: str
    start_time: float | str | None
    end_time: float | str | None


class Status(NamedTuple):
    number: int
    success: bool
    name: str


class StatusWithUrl(NamedTuple):
    number: int
    success: bool
    youtube_id: str
    name: str


def downloader(
    urls: list[str],
    artist: str = "",
    album: str = "",
    playlist_items: str = "",
    strip_patterns: list[str] | None = None,
    strip_meta: bool = True,
    audio_format: str = "",
    audio_quality: str = "",
    chapters_file: str = "",
    output_path: str = "",
    remove_chapters_source_file: bool = False,
    track_numbers: str = "",
) -> None:
    opts: Opts = {"ignoreerrors": True}
    if playlist_items:
        opts["playlist_items"] = playlist_items

    info_opts: Opts = {**opts, "dump_single_json": True}
    postprocessor: dict[str, str] = {"key": "FFmpegExtractAudio", "preferredcodec": audio_format}
    if audio_quality:
        postprocessor["preferredquality"] = audio_quality
    download_opts: Opts = {**opts, "postprocessors": [postprocessor]}

    url = urls[0]
    with youtube_dl.YoutubeDL(info_opts) as ydl:
        info: Info | None = ydl.extract_info(url, download=False)
    if not info:
        sys.exit("couldn't get info")

    if chapters_file:
        chapters_file = os.path.abspath(os.path.expanduser(chapters_file))
        if not os.path.exists(chapters_file):
            sys.exit(f"no chapters file at {chapters_file}, exiting...")

    is_single_songs = info.get("extractor") == "youtube" and not info.get("chapters") and not chapters_file
    if is_single_songs and not album:
        sys.exit("if you pass single-song URL(s), you must also specify an album (--album)")

    album = album or info["title"]
    directory = f"./{album}"

    if output_path:
        try:
            os.chdir(os.path.expanduser(output_path))
        except Exception:
            sys.exit(f"failed to cd into {output_path}, exiting...")

    download = True
    try:
        os.makedirs(directory)
    except FileExistsError:
        print(f"\nthe album directory {directory} already exists")
        text = ""
        if is_single_songs:
            text = capture_input("(d)ownload again, (e)xit: ", "d", "e")
        else:
            text = capture_input("(d)ownload again, (s)kip download but continue, (e)xit: ", "d", "s", "e")
        if text == "s":
            download = False
        elif text == "e":
            print("\nexiting...")
            sys.exit(0)

    os.chdir(directory)

    if strip_meta:
        patterns = [f" *-? *{artist} *-? *"]
        if album:
            patterns.append(f" *- *{album} *")
            patterns.append(f" *{album} *- *")
        strip_patterns = (strip_patterns or []) + patterns

    if info.get("extractor") == "youtube":
        if not info.get("chapters") and not chapters_file:
            single_songs(
                urls=urls,
                artist=artist,
                album=album,
                info_opts=info_opts,
                download_opts=download_opts,
                track_numbers=track_numbers,
                strip_patterns=strip_patterns,
            )
        else:
            chapters(
                url=url,
                artist=artist,
                album=album,
                info=info,
                download=download,
                download_opts=download_opts,
                remove_chapters_source_file=remove_chapters_source_file,
                strip_patterns=strip_patterns,
                chapters_file=chapters_file,
            )
    else:
        print("extractor:", info.get("extractor"), ":: downloading playlist")
        playlist(
            url=url,
            artist=artist,
            album=album,
            info=info,
            download=download,
            info_opts=info_opts,
            download_opts=download_opts,
            track_numbers=track_numbers,
            strip_patterns=strip_patterns,
        )


def single_songs(
    urls: list[str],
    artist: str,
    album: str,
    info_opts: Opts,
    download_opts: Opts,
    track_numbers: str,
    strip_patterns: list[str] | None,
) -> None:
    if len(urls) == 1:
        print("\nthis video is not a playlist, and it has no chapters, are you sure you want to proceed?")
        text = capture_input("(y)es, (n)o: ", "y", "n")
        if text == "n":
            try:
                os.rmdir(os.getcwd())
            except Exception:
                pass
            print("\nexiting...")
            sys.exit(0)

    status: list[StatusWithUrl] = []
    tracks = parse_track_numbers(track_numbers)
    if tracks and len(urls) != len(tracks):
        sys.exit(f"you passed {len(tracks)} track(s) and {len(urls)} url(s)")

    for i, url in enumerate(urls):
        idx = tracks[i] if tracks else i + 1

        with youtube_dl.YoutubeDL(info_opts) as ydl:
            info: Info | None = ydl.extract_info(url, download=False)
        if not info:
            status.append(StatusWithUrl(idx, False, "", ""))
            continue

        if not glob.glob(f"*{info['id']}.*"):  # don't redownload file
            with youtube_dl.YoutubeDL(download_opts) as ydl:
                ydl.download([url])
        else:
            print(
                f"\nfound matching file for {info['title']}... if you wish to download and process file again, "
                "delete this file, or delete album directory\n"
            )

        title = strip(info["title"], strip_patterns) or info["title"]
        for file in glob.glob(f"*{info['id']}.*"):
            _, extension = os.path.splitext(file)
            set_audio_id3(file, title=title, artist=artist, album=album, tracknumber=f"{idx}/{len(urls)}")
            try:
                os.rename(file, f"{title}-{info['id']}{extension}")
            except Exception:
                pass
        status.append(StatusWithUrl(idx, True, info["id"], info["title"]))
    lines = "\n".join(format_status_with_url(s) for s in status)
    print(f"\n{lines}\n")


def chapters(
    url: str,
    artist: str,
    album: str,
    info: Info,
    download: bool,
    download_opts: Opts,
    remove_chapters_source_file: bool,
    strip_patterns: list[str] | None,
    chapters_file: str,
) -> None:
    """Single file with chapters."""

    if download:
        with youtube_dl.YoutubeDL(download_opts) as ydl:
            ydl.download([url])

    source_file = ""
    files = glob.glob(f"*{info['id']}.*")
    if files:
        source_file = files[0]

    chapters: list[Chapter] = []
    if chapters_file:
        read = False
        with open(chapters_file) as file_handle:
            try:
                chapters = json.load(file_handle)
                read = True
            except json.JSONDecodeError:
                print(f"\nfailed to read {chapters_file} as JSON, trying as CSV\n")
        if not read:
            chapters = read_as_csv(chapters_file)
    else:
        chapters = info.get("chapters") or []

    status: list[Status] = []
    for i, chapter in enumerate(chapters):
        idx = i + 1

        raw_title = chapter.get("title") or str(idx)
        title = clean_filename(strip(raw_title, strip_patterns) or raw_title)

        start_time = chapter.get("start_time")
        if start_time is None or start_time == "":
            if i > 0:
                start_time = chapters[i - 1].get("end_time")
                if start_time is None or start_time == "":
                    sys.exit(f"chapter {chapter} has no start_time, and chapter {chapters[i - 1]} has no end_time")
            else:
                start_time = 0

        end_time = chapter.get("end_time")
        if end_time is None or end_time == "":
            if i < len(chapters) - 1:
                end_time = chapters[i + 1].get("start_time")
                if end_time is None or end_time == "":
                    sys.exit(f"chapter {chapter} has no end_time, and chapter {chapters[i + 1]} has no start_time")
            else:
                end_time = 1000000000

        file = (glob.glob(f"*{title}.*") or [""])[0]
        if source_file:
            _, extension = os.path.splitext(source_file)
            file = f"{title}{extension}"
            cmd = ["ffmpeg", "-i", source_file, "-acodec", "copy", "-ss", str(start_time), "-to", str(end_time), file]
            subprocess.check_output(cmd)
        if set_audio_id3(file, title=title, artist=artist, album=album, tracknumber=f"{idx}/{len(chapters)}"):
            status.append(Status(idx, True, title))
        else:
            status.append(Status(idx, False, title))
    if remove_chapters_source_file and source_file:
        try:
            os.remove(source_file)
        except Exception:
            pass
    full_url = f"https://www.youtube.com/watch?v={info['id']}"
    print(f"\nplaylist built from single video with chapters: {full_url}")
    lines = "\n".join(format_status(s) for s in status)
    print(f"\n{lines}\n")


def playlist(
    url: str,
    artist: str,
    album: str,
    info: Info,
    download: bool,
    info_opts: Opts,
    download_opts: Opts,
    track_numbers: str,
    strip_patterns: list[str] | None,
) -> None:
    tracks = parse_track_numbers(track_numbers)
    entries = info.get("entries") or []
    if tracks and len(entries) != len(tracks):
        sys.exit(f"you passed {len(tracks)} track(s) but there are {len(entries)} file(s) in the playlist")
    if download:
        with youtube_dl.YoutubeDL(download_opts) as ydl:
            ydl.download([url])

    status: list[StatusWithUrl] = []
    for i, entry in enumerate(entries):
        idx = tracks[i] if tracks else i + 1
        with youtube_dl.YoutubeDL(info_opts) as ydl:
            if entry is None:
                status.append(StatusWithUrl(idx, False, "", ""))
                continue
            else:
                track_info: Info | None = ydl.extract_info(entry["id"], download=False)
                if track_info is None:
                    status.append(StatusWithUrl(idx, False, entry["id"], entry.get("title", "")))
                    continue

        title = strip(track_info["title"], strip_patterns) or track_info["title"]
        status.append(StatusWithUrl(idx, True, track_info["id"], title))
        for file in glob.glob(f"*{track_info['id']}.*"):
            _, extension = os.path.splitext(file)
            set_audio_id3(file, title=title, artist=artist, album=album, tracknumber=f"{idx}/{len(entries)}")
            try:
                os.rename(file, f"{title}-{track_info['id']}{extension}")
            except Exception:
                pass
    lines = "\n".join(format_status_with_url(s) for s in status)
    print(f"\n{lines}\n")


def format_status(track: Status) -> str:
    num, success, name = track
    return "    ".join([str(num).rjust(5), "✔" if success else "✘", name])


def format_status_with_url(track: StatusWithUrl) -> str:
    num, success, youtube_id, name = track
    return "    ".join(
        [str(num).rjust(5), "✔" if success else "✘", f"https://www.youtube.com/watch?v={youtube_id}", name]
    )


def capture_input(prompt: str, *options: str) -> str:
    while True:
        text = input(prompt).lower()
        if text in options:
            return text
        else:
            print(f"`{text}` is not a valid option")


def set_audio_id3(file: str, **tags: str) -> bool:
    try:
        audio = EasyID3(file)
    except Exception as e:
        print(f"{e}\ntried to set metadata on {file} but couldn't, skipping...")
        return False
    for k, v in tags.items():
        audio[k] = v
    audio.save()
    return True


def clean_filename(file: str) -> str:
    return file.replace("/", "").replace(chr(92), "").replace(chr(0), "")


def read_as_csv(file: str) -> list[Chapter]:
    with open(file) as file_handle:
        reader = csv.reader(file_handle, delimiter=",")
        chapters = [
            Chapter(title=row[0], start_time=row[1], end_time=row[2] if len(row) >= 3 else None) for row in reader
        ]
        if len(chapters) == 0:
            sys.exit(f"failed to read {file} as CSV, exiting...")
        return chapters


def strip(s: str, patterns: list[str] | None = None) -> str:
    if not patterns:
        return s
    for pattern in patterns:
        s = re.sub(pattern, "", s, flags=re.IGNORECASE)
    return s


def parse_track_numbers(s: str) -> list[int]:
    tracks: list[int] = []
    try:
        s = s.replace(" ", "")
        if not s:
            return []
        for rng in s.split(","):
            pair = rng.split("-")
            if len(pair) == 1:
                tracks.append(int(pair[0]))
            else:
                tracks += list(range(int(pair[0]), int(pair[1]) + 1))
        return tracks
    except Exception as e:
        sys.exit(f"invalid track numbers: {e}")
