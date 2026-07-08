import argparse
import subprocess
import sys
from typing import Any

import yt_dlp
from packaging.version import Version

# yt-dlp is effectively dynamic; treat as untyped.
youtube_dl: Any = yt_dlp

if sys.version_info < (3, 12):
    sys.exit("you need at least python3.12 to run youtube-multi-dl\n\n")

from .downloader import downloader  # noqa

your_version = "2.0.0"

audio_formats = ("aac", "flac", "mp3", "m4a", "opus", "vorbis", "wav", "best")

parser = argparse.ArgumentParser(description="Download a playlist from YouTube using yt-dlp")

parser.add_argument("-v", "--version", action="store_true", help="show version and exit")
# user must pass url, artist (album can be taken from playlist title)
parser.add_argument(
    "url", type=str, nargs="+", help="URL of YouTube playlist or video with chapters, or list of single-song URLs"
)
parser.add_argument("-a", "--artist", required=True, help="Artist(s)")
parser.add_argument("--album", default="", help="Album(s), defaults to YouTube playlist or video name")
parser.add_argument("-p", "--playlist-items", default="", help='Playlist tracks to download; e.g. "1,3-5,7-9,11,12"')
parser.add_argument(
    "-t",
    "--track-numbers",
    default="",
    help="Track numbers to assign to playlist items; must have same length as playlist items",
)
parser.add_argument(
    "-r",
    "--remove-chapters-source-file",
    action="store_true",
    help="For video with chapters, remove source file after download",
)
parser.add_argument("-s", "--strip-patterns", type=str, nargs="+", help="Remove patterns from title(s)")
parser.add_argument("--no-strip-meta", action="store_true", help="Don't remove artist and album names from title(s)")
parser.add_argument(
    "-f",
    "--audio-format",
    type=str,
    default="mp3",
    help=f'Audio format; one of {audio_formats}; default "mp3"; '
    '"best" optimizes for audio quality, but may not be the format you want',
)
parser.add_argument(
    "-q",
    "--audio-quality",
    type=str,
    default="",
    help="Audio quality; insert a value between "
    "0 (better) and 9 (worse) for VBR or a specific bitrate like 128K (default 160)",
)
parser.add_argument("--chapters-file", type=str, default="", help="JSON or CSV file with chapters info")
parser.add_argument(
    "-o", "--output-path", type=str, default="", help="Directory in which album/playlist directory is created"
)


def latest_version(package_info_url: str) -> Version | None:
    import json
    import urllib.request

    try:
        response = urllib.request.urlopen(package_info_url)
        text = response.read()
        info = json.loads(text.decode("utf-8"))

        versions = info["releases"].keys() or ["0.0.0"]
        return max(Version(v) for v in versions)
    except Exception:
        return None


def print_version(always_show_version: bool = True) -> None:
    version = latest_version("https://pypi.python.org/pypi/youtube-multi-dl/json")

    if version is not None:
        if version > Version(your_version):
            print(f"\n####\nthe latest version of youtube-multi-dl is {version}, but you have {your_version}")
            print("run e.g. `pip install --upgrade youtube-multi-dl` to upgrade\n####")
            print("\nsee release notes here: https://github.com/fortana-co/youtube-multi-dl/blob/master/RELEASES.md")
        elif always_show_version:
            print(f"latest version is {version}, you're up to date!")


def print_ydl_version(always_show_version: bool = True) -> None:
    version = latest_version("https://pypi.python.org/pypi/yt-dlp/json")
    if version is not None:
        if version > Version(youtube_dl.version.__version__):
            print(f"\n####\nthe latest version of yt-dlp is {version}, but you have {youtube_dl.version.__version__}")
            print("you should upgrade yt-dlp")
        elif always_show_version:
            print(f"latest yt-dlp version is {version}, you're up to date!")


def main() -> None:
    """The `console_scripts` entry point for youtube-multi-dl. There's no need to pass
    arguments to this function, because `argparse` reads `sys.argv[1:]`.

    http://python-packaging.readthedocs.io/en/latest/command-line-scripts.html#the-console-scripts-entry-point
    """
    if len(sys.argv) > 1 and (sys.argv[1] == "-v" or sys.argv[1] == "--version"):
        print(f"youtube-multi-dl version {your_version}")
        print_version()
        print(f"\nyt-dlp version {youtube_dl.version.__version__}")
        print_ydl_version()

        sys.exit(0)
    if len(sys.argv) == 1:
        sys.argv.append("-h")

    args = parser.parse_args()

    audio_format: str = args.audio_format
    audio_quality: str = args.audio_quality
    if audio_format not in audio_formats:
        print(f"invalid audio format: must be one of {audio_formats}")
        sys.exit()
    if audio_format != "best" and not audio_quality:
        audio_quality = "160"

    if subprocess.call(["which", "ffmpeg"]) != 0:
        print("ffmpeg isn't installed! youtube-multi-dl needs ffmpeg to convert video to audio...")
        print("osx: `brew install ffmpeg`")
        print("ubuntu: `sudo apt-get install ffmpeg`")
        sys.exit()

    try:
        downloader(
            urls=args.url,
            artist=args.artist,
            album=args.album,
            playlist_items=args.playlist_items,
            strip_patterns=args.strip_patterns,
            strip_meta=not args.no_strip_meta,
            audio_format=audio_format,
            audio_quality=audio_quality,
            chapters_file=args.chapters_file,
            output_path=args.output_path,
            remove_chapters_source_file=args.remove_chapters_source_file,
            track_numbers=args.track_numbers,
        )
    except KeyboardInterrupt:
        sys.exit()

    print_version(False)
    print_ydl_version(False)
