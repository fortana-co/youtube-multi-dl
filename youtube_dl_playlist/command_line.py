import sys
import argparse
import subprocess

from .downloader import downloader


parser = argparse.ArgumentParser(description='Download a playlist from YouTube using youtube-dl')

# user must pass url, artist (album can be taken from playlist title)
parser.add_argument('-u', '--url', required=True,
                    help='URL of YouTube playlist')
parser.add_argument('-a', '--artist', required=True,
                    help='Playlist artist(s)')
parser.add_argument('-A', '--album',
                    help='Playlist album(s), defaults to YouTube playlist name')
parser.add_argument('--playlist-items',
                    help='Playlist tracks to download')
parser.add_argument('--keep-id', action='store_true',
                    help='Keep YouTube URL/ID in filename')


def main():
    """The `console_scripts` entry point for pick-git. There's no need to pass
    arguments to this function, because `argparse` reads `sys.argv[1:]`.

    http://python-packaging.readthedocs.io/en/latest/command-line-scripts.html#the-console-scripts-entry-point
    """
    args = parser.parse_args()
    kwargs = {}
    for name in [
        'url',
        'artist',
        'album',
        'playlist_items',
        'keep_id',
    ]:
        if args.__getattribute__(name) is not None:
            kwargs[name] = args.__getattribute__(name)
    if not subprocess.call(['which', 'ffmpeg']) == 0:
        print("ffmpeg isn't installed! youtube-dl-playlist needs ffmpeg to convert video to audio...")
        print("\ninstructions: https://trac.ffmpeg.org/wiki/CompilationGuide")
        print("osx: `brew install ffmpeg`")
        print("ubuntu: `sudo apt-get install ffmpeg`")
        sys.exit()
    downloader(**kwargs)
