import sys
import argparse
import subprocess

if sys.version_info.major < 3 or sys.version_info.minor < 5:
    sys.exit(
        'you need at least python3.5 to run youtube-multi-dl\n\n'
        'make sure you installed it with `pip3 install youtube-multi-dl`',
    )

from .downloader import downloader  # noqa

your_version = '1.2.1'

audio_formats = ('aac', 'flac', 'mp3', 'm4a', 'opus', 'vorbis', 'wav', 'best')

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
parser.add_argument('--no-strip-meta', action='store_true', help='Don\'t remove artist and album names from title(s)')
parser.add_argument(
    '-f',
    '--audio-format',
    type=str,
    default='mp3',
    help='Audio format; one of {}; default "mp3"; '
    '"best" optimizes for audio quality, but may not be the format you want'.format(audio_formats),
)
parser.add_argument(
    '-q',
    '--audio-quality',
    type=str,
    default='',
    help='Audio quality; insert a value between '
    '0 (better) and 9 (worse) for VBR or a specific bitrate like 128K (default 160)',
)
parser.add_argument('--chapters-file', type=str, default='', help='JSON or CSV file with chapters info')
parser.add_argument(
    '-o',
    '--output-path',
    type=str,
    default='',
    help='Directory in which album/playlist directory is created',
)


def check_version(always_show_version=False):
    import urllib.request
    import json
    from distutils.version import LooseVersion

    try:
        response = urllib.request.urlopen('https://pypi.python.org/pypi/youtube-multi-dl/json')
        text = response.read()
        info = json.loads(text.decode('utf-8'))

        versions = info['releases'].keys() or ['0.0.0']
        latest_version = max(LooseVersion(v) for v in versions)
        if latest_version > LooseVersion(your_version):
            print(
                '\n####\nthe latest version of youtube-multi-dl is {}, but you have {}'.format(
                    latest_version.vstring,
                    your_version,
                ),
            )
            print('run `pip3 install --upgrade youtube-multi-dl` to upgrade\n####')
            print('\nsee release notes here: https://github.com/fortana-co/youtube-multi-dl/blob/master/RELEASES.md')
        elif always_show_version:
            print("latest version is {}, you're up to date!".format(latest_version))
    except Exception:
        pass
    sys.exit(0)


def main():
    """The `console_scripts` entry point for youtube-multi-dl. There's no need to pass
    arguments to this function, because `argparse` reads `sys.argv[1:]`.

    http://python-packaging.readthedocs.io/en/latest/command-line-scripts.html#the-console-scripts-entry-point
    """
    if len(sys.argv) > 1 and (sys.argv[1] == '-v' or sys.argv[1] == '--version'):
        print('youtube-multi-dl version {}'.format(your_version))
        check_version(always_show_version=True)
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
        'strip_patterns',
        'track_numbers',
        'audio_format',
        'audio_quality',
        'chapters_file',
        'output_path',
    ]:
        kwargs[name] = args.__getattribute__(name)
    kwargs['urls'] = args.__getattribute__('url')
    kwargs['strip_meta'] = not args.__getattribute__('no_strip_meta')

    if kwargs['audio_format'] not in audio_formats:
        print('invalid audio format: must be one of {}'.format(audio_formats))
        sys.exit()
    if kwargs['audio_format'] != 'best' and not kwargs['audio_quality']:
        kwargs['audio_quality'] = '160'

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

    check_version()
