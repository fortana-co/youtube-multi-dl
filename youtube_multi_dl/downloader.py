from typing import Any, List, Dict, Tuple
import os
import re
import sys
import csv
import json
import glob
import subprocess

import youtube_dl  # type: ignore
from mutagen.easyid3 import EasyID3  # type: ignore


def downloader(
    urls: List[str],
    artist="",
    album="",
    playlist_items="",
    strip_patterns: List[str] = None,
    strip_meta=True,
    audio_format="",
    audio_quality="",
    chapters_file="",
    output_path="",
    **kwargs,
) -> Any:
    opts: Dict[str, Any] = {"ignoreerrors": True}
    if playlist_items:
        opts["playlist_items"] = playlist_items

    info_opts = {**opts, "dump_single_json": True}
    postprocessor = {"key": "FFmpegExtractAudio", "preferredcodec": audio_format}
    if audio_quality:
        postprocessor["preferredquality"] = audio_quality
    download_opts = {**opts, "postprocessors": [postprocessor]}

    url = urls[0]
    with youtube_dl.YoutubeDL(info_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        sys.exit("couldn't get info")

    if chapters_file:
        chapters_file = os.path.abspath(os.path.expanduser(chapters_file))
        if not os.path.exists(chapters_file):
            sys.exit("no chapters file at {}, exiting...".format(chapters_file))

    is_single_songs = info.get("extractor") == "youtube" and not info.get("chapters") and not chapters_file
    if is_single_songs and not album:
        sys.exit("if you pass single-song URL(s), you must also specify an album (--album)")

    album = album or info["title"]
    directory = "./{}".format(album)

    if output_path:
        try:
            os.chdir(os.path.expanduser(output_path))
        except Exception:
            sys.exit("failed to cd into {}, exiting...".format(output_path))

    download = True
    try:
        os.makedirs(directory)
    except FileExistsError:
        print("\nthe album directory {} already exists".format(directory))
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
        patterns = [" *-? *{} *-? *".format(artist)]
        if album:
            patterns.append(" *- *{} *".format(album))
            patterns.append(" *{} *- *".format(album))
        strip_patterns = (strip_patterns or []) + patterns

    all_kwargs = {
        "url": url,
        "urls": urls,
        "album": album,
        "info": info,
        "download": download,
        "info_opts": info_opts,
        "download_opts": download_opts,
        "artist": artist,
        "strip_patterns": strip_patterns,
        "chapters_file": chapters_file,
        **kwargs,
    }

    if info.get("extractor") == "youtube":
        if not info.get("chapters") and not chapters_file:
            single_songs(**all_kwargs)
        else:
            chapters(**all_kwargs)
    else:
        print("extractor:", info.get("extractor"), ":: downloading playlist")
        playlist(**all_kwargs)


def single_songs(
    urls: List[str], artist, album, info_opts, download_opts, track_numbers, strip_patterns, **kwargs
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

    status = []
    tracks = parse_track_numbers(track_numbers)
    if tracks and len(urls) != len(tracks):
        sys.exit("you passed {} track(s) and {} url(s)".format(len(tracks), len(urls)))

    for i, url in enumerate(urls):
        idx = tracks[i] if tracks else i + 1

        with youtube_dl.YoutubeDL(info_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if not info:
            status.append((idx, False, "", ""))
            continue

        if not glob.glob("*{}.*".format(info["id"])):  # don't redownload file
            with youtube_dl.YoutubeDL(download_opts) as ydl:
                ydl.download([url])
        else:
            print(
                "\nfound matching file for {}... if you wish to download and process file again, "
                "delete this file, or delete album directory\n".format(info["title"])
            )

        title = strip(info["title"], strip_patterns) or info["title"]
        for file in glob.glob("*{}.*".format(info["id"])):
            _, extension = os.path.splitext(file)
            set_audio_id3(file, title=title, artist=artist, album=album, tracknumber="{}/{}".format(idx, len(urls)))
            try:
                os.rename(file, "{}-{}{}".format(title, info["id"], extension))
            except Exception:
                pass
        status.append((idx, True, info["id"], info["title"]))
    print("\n{}\n".format("\n".join(format_status_with_url(s) for s in status)))


def chapters(
    url,
    artist,
    album,
    info,
    download,
    download_opts,
    remove_chapters_source_file,
    strip_patterns,
    chapters_file,
    **kwargs,
) -> None:
    """Single file with chapters."""

    if download:
        with youtube_dl.YoutubeDL(download_opts) as ydl:
            ydl.download([url])

    source_file = ""
    files = glob.glob("*{}.*".format(info["id"]))
    if files:
        source_file = files[0]

    chapters: List[Dict] = []
    if chapters_file:
        read = False
        with open(chapters_file) as file_handle:
            try:
                chapters = json.load(file_handle)
                read = True
            except json.JSONDecodeError:
                print("\nfailed to read {} as JSON, trying as CSV\n".format(chapters_file))
        if not read:
            chapters = read_as_csv(chapters_file)
    else:
        chapters = info.get("chapters")

    status = []
    for i, chapter in enumerate(chapters):
        idx = i + 1

        raw_title = chapter.get("title") or str(idx)
        title = clean_filename(strip(raw_title, strip_patterns) or raw_title)

        start_time = chapter.get("start_time")
        if start_time is None or start_time == "":
            if i > 0:
                start_time = chapters[i - 1].get("end_time")
                if start_time is None or start_time == "":
                    sys.exit(
                        "chapter {} has no start_time, and chapter {} has no end_time".format(chapter, chapters[i - 1])
                    )
            else:
                start_time = 0

        end_time = chapter.get("end_time")
        if end_time is None or end_time == "":
            if i < len(chapters) - 1:
                end_time = chapters[i + 1].get("start_time")
                if end_time is None or end_time == "":
                    sys.exit(
                        "chapter {} has no end_time, and chapter {} has no start_time".format(chapter, chapters[i + 1])
                    )
            else:
                end_time = 1000000000

        file = (glob.glob("*{}.*".format(title)) or [""])[0]
        if source_file:
            _, extension = os.path.splitext(source_file)
            file = "{}{}".format(title, extension)
            cmd = ["ffmpeg", "-i", source_file, "-acodec", "copy", "-ss", str(start_time), "-to", str(end_time), file]
            subprocess.check_output(cmd)
        if set_audio_id3(file, title=title, artist=artist, album=album, tracknumber="{}/{}".format(idx, len(chapters))):
            status.append((idx, True, title))
        else:
            status.append((idx, False, title))
    if remove_chapters_source_file and source_file:
        try:
            os.remove(source_file)
        except Exception:
            pass
    full_url = "https://www.youtube.com/watch?v={}".format(info["id"])
    print("\nplaylist built from single video with chapters: {}".format(full_url))
    print("\n{}\n".format("\n".join(format_status(s) for s in status)))


def playlist(
    url, artist, album, info, download, info_opts, download_opts, track_numbers, strip_patterns, **kwargs
) -> None:
    tracks = parse_track_numbers(track_numbers)
    entries = info.get("entries")
    if tracks and len(entries) != len(tracks):
        sys.exit("you passed {} track(s) but there are {} file(s) in the playlist".format(len(tracks), len(entries)))
    if download:
        with youtube_dl.YoutubeDL(download_opts) as ydl:
            ydl.download([url])

    status = []
    for i, entry in enumerate(entries):
        idx = tracks[i] if tracks else i + 1
        with youtube_dl.YoutubeDL(info_opts) as ydl:
            track_info = ydl.extract_info(entry["id"], download=False)
        if track_info is None:
            status.append((idx, False, entry["id"], entry.get("title", "")))
            continue

        title = strip(track_info["title"], strip_patterns) or track_info["title"]
        status.append((idx, True, track_info["id"], title))
        for file in glob.glob("*{}.*".format(track_info["id"])):
            _, extension = os.path.splitext(file)
            set_audio_id3(file, title=title, artist=artist, album=album, tracknumber="{}/{}".format(idx, len(entries)))
            try:
                os.rename(file, "{}-{}{}".format(title, track_info["id"], extension))
            except Exception:
                pass
    print("\n{}\n".format("\n".join(format_status_with_url(s) for s in status)))


def format_status(track: Tuple[int, bool, str]) -> str:
    num, success, name = track
    return "    ".join([str(num).rjust(5), "✔" if success else "✘", name])


def format_status_with_url(track: Tuple[int, bool, str, str]) -> str:
    num, success, youtube_id, name = track
    return "    ".join(
        [str(num).rjust(5), "✔" if success else "✘", "https://www.youtube.com/watch?v={}".format(youtube_id), name]
    )


def capture_input(prompt: str, *options) -> str:
    while True:
        text = input(prompt).lower()
        if text in options:
            return text
        else:
            print("`{}` is not a valid option".format(text))


def set_audio_id3(file: str, **kwargs) -> bool:
    try:
        audio = EasyID3(file)
    except Exception as e:
        print("{}\ntried to set metadata on {} but couldn't, skipping...".format(e, file))
        return False
    for k, v in kwargs.items():
        audio[k] = v
    audio.save()
    return True


def clean_filename(file: str) -> str:
    return file.replace("/", "").replace(chr(92), "").replace(chr(0), "")


def read_as_csv(file: str) -> List[Dict]:
    with open(file) as file_handle:
        reader = csv.reader(file_handle, delimiter=",")
        chapters = [
            {"title": row[0], "start_time": row[1], "end_time": row[2] if len(row) >= 3 else None} for row in reader
        ]
        if len(chapters) == 0:
            sys.exit("failed to read {} as CSV, exiting...".format(file))
        return chapters


def strip(s: str, patterns: List[str] = None) -> str:
    if not patterns:
        return s
    for pattern in patterns:
        s = re.sub(pattern, "", s, flags=re.IGNORECASE)
    return s


def parse_track_numbers(s: str) -> List[int]:
    tracks: List[int] = []
    try:
        s = s.replace(" ", "")
        if not s:
            return []
        for rng in s.split(","):
            pair = rng.split("-")
            if len(pair) == 1:
                tracks.append(int(pair[0]))
            else:
                tracks += [i for i in range(int(pair[0]), int(pair[1]) + 1)]
        return tracks
    except Exception as e:
        sys.exit("invalid track numbers: {}".format(e))
