import sys
import argparse
import subprocess

if sys.version_info.major < 3 or sys.version_info.minor < 5:
    sys.exit(
        'you need at least python3.5 to run youtube-multi-dl\n\n'
        'make sure you installed it with `pip3 install youtube-multi-dl`',
    )

from .downloader import downloader  # noqa

parser = argparse.ArgumentParser(description='Download a playlist from YouTube using youtube-dl')

parser.add_argument('-v', '--version', action='store_true', help='show version and exit')
# user must pass url, artist (album can be taken from playlist title)
parser.add_argument(
    'url',
    type=str,
    nargs='+',
    help='URL of YouTube playlist or video with chapters, or list of single-song URLs',
)
parser.add_argument('-a', '--artist', required=True, help='Artist(s)')
parser.add_argument('-A', '--album', default='', help='Album(s), defaults to YouTube playlist or video name')
parser.add_argument('-p', '--playlist-items', default='', help='Playlist tracks to download; e.g. "1,3-5,7-9,11,12"')
parser.add_argument(
    '-t',
    '--track-numbers',
    default='',
    help='Track numbers to assign to playlist items; must have same length as playlist items',
)
parser.add_argument(
    '-r',
    '--remove-chapters-source-file',
    action='store_true',
    help='For video with chapters, remove source file after download',
)
parser.add_argument('-s', '--strip-patterns', type=str, nargs='+', help='Remove patterns from title(s)')
parser.add_argument('-S', '--strip-meta', action='store_true', help='Remove artist and album names from title(s)')


def main():
    """The `console_scripts` entry point for youtube-multi-dl. There's no need to pass
    arguments to this function, because `argparse` reads `sys.argv[1:]`.

    http://python-packaging.readthedocs.io/en/latest/command-line-scripts.html#the-console-scripts-entry-point
    """
    if len(sys.argv) > 1 and (sys.argv[1] == '-v' or sys.argv[1] == '--version'):
        print('youtube-multi-dl version 0.3.0')
        sys.exit(0)
    if len(sys.argv) == 1:
        sys.argv.append('-h')

    args = parser.parse_args()
    kwargs = {}
    for name in [
        'artist',
        'album',
        'playlist_items',
        'remove_chapters_source_file',
        'strip_meta',
        'strip_patterns',
        'track_numbers',
    ]:
        kwargs[name] = args.__getattribute__(name)
    kwargs['urls'] = args.__getattribute__('url')
    if subprocess.call(['which', 'ffmpeg']) != 0:
        print("ffmpeg isn't installed! youtube-multi-dl needs ffmpeg to convert video to audio...")
        print("\ninstructions: https://trac.ffmpeg.org/wiki/CompilationGuide")
        print("osx: `brew install ffmpeg`")
        print("ubuntu: `sudo apt-get install ffmpeg`")
        sys.exit()

    try:
        downloader(**kwargs)
    except KeyboardInterrupt:
        sys.exit()
