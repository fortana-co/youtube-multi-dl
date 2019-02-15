from typing import Any, List, Dict, Tuple
import os
import re
import sys
import glob
import subprocess

import youtube_dl
from mutagen.easyid3 import EasyID3


def downloader(url='', album='', playlist_items='', **kwargs) -> Any:
    opts: Dict[str, Any] = {'ignoreerrors': True}
    if playlist_items:
        opts['playlist_items'] = playlist_items

    info_opts = {**opts, 'dump_single_json': True, 'extract_flat': True}
    download_opts = {
        **opts,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    with youtube_dl.YoutubeDL(info_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        sys.exit("couldn't get playlist info")

    download = True
    album = album or info['title']
    directory = './{}'.format(info['title'])
    try:
        os.makedirs(directory)
    except FileExistsError:
        print('\nthe album directory {} already exists'.format(directory))
        text = capture_input('(d)ownload again, (s)kip download but continue, (e)xit: ', 'd', 's', 'e')
        if text == 's':
            download = False
        elif text == 'e':
            print('\nexiting...')
            sys.exit(0)

    os.chdir(directory)

    all_kwargs = {
        'url': url,
        'album': album,
        'info': info,
        'download': download,
        'info_opts': info_opts,
        'download_opts': download_opts,
        **kwargs,
    }
    if info.get('extractor') == 'youtube':
        if not info.get('chapters'):
            no_chapters(**all_kwargs)
        else:
            chapters(**all_kwargs)
    elif info.get('extractor') == 'youtube:playlist':
        playlist(**all_kwargs)


def no_chapters(url, artist, album, info, download, download_opts, strip_patterns, **kwargs) -> Any:
    """Single file, no chapters.
    """
    print('\nthis video is not a playlist, and it has no chapters, are you sure you want to proceed?')
    text = capture_input('(y)es, (n)o: ', 'y', 'n')
    if text == 'n':
        try:
            os.rmdir(os.getcwd())
        except Exception as e:
            print(e)
        print('\nexiting...')
        sys.exit(0)

    if download:
        with youtube_dl.YoutubeDL(download_opts) as ydl:
            ydl.download([url])

    title = strip(info['title'], strip_patterns)
    for file in glob.glob('*{}.mp3'.format(info['id'])):
        set_audio_id3(
            file,
            title=title,
            artist=artist,
            album=album,
        )
        try:
            os.rename(file, '{}-{}.mp3'.format(title, info['id']))
        except Exception:
            pass


def chapters(url, artist, album, info, download, download_opts, remove_source_file, strip_patterns, **kwargs) -> Any:
    """Single file with chapters.
    """
    if download:
        with youtube_dl.YoutubeDL(download_opts) as ydl:
            ydl.download([url])

    split = True
    files = glob.glob('*{}.mp3'.format(info['id']))
    if not(files):
        split = False
    source_file = files[0]

    chapters = info.get('chapters')

    status = []
    for i, chapter in enumerate(chapters):
        idx = i + 1
        start_time = chapter['start_time']
        end_time = chapter['end_time']
        title = clean_filename(strip(chapter.get('title') or str(idx), strip_patterns))
        file = '{}.mp3'.format(title)
        if split:
            cmd = [
                'ffmpeg', '-i', source_file, '-acodec', 'copy', '-ss', str(start_time), '-to', str(end_time), file,
            ]
            subprocess.check_output(cmd)
        if set_audio_id3(
            file,
            title=title,
            artist=artist,
            album=album,
            tracknumber='{}/{}'.format(idx, len(chapters)),
        ):
            status.append((idx, True, title))
        else:
            status.append((idx, False,title))
    if remove_source_file:
        try:
            os.remove(source_file)
        except Exception:
            pass
    print('\nplaylist built from single video with chapters: {}'.format(url))
    print('\n{}\n'.format('\n'.join(format_status_chapters(s) for s in status)))


def playlist(
    url, artist, album, info, download, info_opts, download_opts, strip_patterns, track_numbers, **kwargs,
) -> Any:
    tracks = parse_track_numbers(track_numbers)
    entries = info.get('entries')
    if tracks and len(entries) != len(tracks):
        sys.exit('you passed {} track(s) but there are {} file(s) in the playlist'.format(len(tracks), len(entries)))
    if download:
        with youtube_dl.YoutubeDL(download_opts) as ydl:
            ydl.download([url])

    status = []
    for i, entry in enumerate(entries):
        idx = tracks[i] if tracks else i + 1
        with youtube_dl.YoutubeDL(info_opts) as ydl:
            track_info = ydl.extract_info(entry['id'], download=False)
        if track_info is None:
            status.append((idx, False, entry['id'], entry.get('title', '')))
            continue

        title = strip(track_info['title'], strip_patterns)
        status.append((idx, True, track_info['id'], title))
        for file in glob.glob('*{}.mp3'.format(track_info['id'])):
            set_audio_id3(
                file,
                title=title,
                artist=artist,
                album=album,
                tracknumber='{}/{}'.format(idx, len(entries)),
            )
            try:
                os.rename(file, '{}-{}.mp3'.format(title, track_info['id']))
            except Exception:
                pass
    print('\n{}\n'.format('\n'.join(format_status(s) for s in status)))


def format_status_chapters(track: Tuple[int, bool, str]) -> str:
    num, success, name = track
    return '    '.join([str(num).rjust(5), '✔' if success else '✘', name])


def format_status(track: Tuple[int, bool, str, str]) -> str:
    num, success, youtube_id, name = track
    return '    '.join([
        str(num).rjust(5), '✔' if success else '✘', 'https://www.youtube.com/watch?v={}'.format(youtube_id), name,
    ])


def capture_input(prompt: str, *options) -> str:
    while True:
        text = input(prompt).lower()
        if text in options:
            return text
        else:
            print('`{}` is not a valid option'.format(text))


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
    return file.replace('/', '').replace(chr(92), '').replace(chr(0), '')


def strip(s: str, patterns: List[str] = None) -> str:
    if not patterns:
        return s
    for pattern in patterns:
        s = re.sub(pattern, '', s, flags=re.IGNORECASE)
    return s


def parse_track_numbers(s: str) -> List[int]:
    tracks: List[int] = []
    try:
        s = s.replace(' ', '')
        if not s:
            return []
        for rng in s.split(','):
            pair = rng.split('-')
            if len(pair) == 1:
                tracks.append(int(pair[0]))
            else:
                tracks += [i for i in range(int(pair[0]), int(pair[1]) + 1)]
        return tracks
    except Exception as e:
        sys.exit('invalid track numbers: {}'.format(e))
