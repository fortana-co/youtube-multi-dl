import os
import sys
import glob
import subprocess

import youtube_dl
from mutagen.easyid3 import EasyID3


def downloader(url, artist, album='', playlist_items='', remove_source_file=False):
    opts = {'ignoreerrors': True}
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
        if text == 'd':
            pass
        elif text == 's':
            download = False
        elif text == 'e':
            print('\nexiting...')
            sys.exit(0)

    os.chdir(directory)

    args = [url, artist, album, info, download, info_opts, download_opts, remove_source_file]
    if info.get('extractor') == 'youtube':
        if not info.get('chapters'):
            no_chapters(*args)
        else:
            chapters(*args)
    elif info.get('extractor') == 'youtube:playlist':
        playlist(*args)


def no_chapters(url, artist, album, info, download, info_opts, download_opts, remove_source_file, *args):
    """Single file, no chapters.
    """
    print('\nthis video is not a playlist, and it has no chapters, are you sure you want to proceed?')
    text = capture_input('(y)es, (n)o: ', 'y', 'n')
    if text.lower() == 'y':
        pass
    elif text.lower() == 'n':
        try:
            os.rmdir(os.getcwd())
        except Exception as e:
            print(e)
        print('\nexiting...')
        sys.exit(0)

    if download:
        with youtube_dl.YoutubeDL(download_opts) as ydl:
            ydl.download([url])

    for file in glob.glob('*{}.mp3'.format(info['id'])):
        set_audio_id3(
            file,
            title=info['title'],
            artist=artist,
            album=album,
        )


def chapters(url, artist, album, info, download, info_opts, download_opts, remove_source_file, *args):
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

    for i, chapter in enumerate(chapters):
        start_time = chapter['start_time']
        end_time = chapter['end_time']
        title = chapter.get('title') or str(i + 1)
        file = clean_filename('{}.mp3'.format(title))
        if split:
            cmd = [
                'ffmpeg', '-i', source_file, '-acodec', 'copy', '-ss', str(start_time), '-to', str(end_time), file,
            ]
            subprocess.check_output(cmd)
        set_audio_id3(
            file,
            title=title,
            artist=artist,
            album=album,
            tracknumber='{}/{}'.format(i + 1, len(chapters)),
        )
    if remove_source_file:
        try:
            os.remove(source_file)
        except:
            pass


def playlist(url, artist, album, info, download, info_opts, download_opts, remove_source_file, *args):
    if download:
        with youtube_dl.YoutubeDL(download_opts) as ydl:
            ydl.download([url])

    for i, entry in enumerate(info.get('entries')):
        with youtube_dl.YoutubeDL(info_opts) as ydl:
            track_info = ydl.extract_info(entry['id'], download=False)
        if not track_info:
            continue
        for file in glob.glob('*{}.mp3'.format(track_info['id'])):
            set_audio_id3(
                file,
                title=track_info['title'],
                artist=artist,
                album=album,
                tracknumber='{}/{}'.format(i + 1, len(info.get('entries'))),
            )


def capture_input(prompt, *options):
    while True:
        text = input(prompt).lower()
        if text in options:
            return text
        else:
            print('`{}` is not a valid option'.format(text))


def set_audio_id3(file, **kwargs):
    try:
        audio = EasyID3(file)
    except Exception as e:
        print("{}\ntried to set metadata on {} but couldn't, skipping...".format(e, file))
        return
    for k, v in kwargs.items():
        audio[k] = v
    audio.save()


def clean_filename(file):
    return file.replace('/', '').replace(chr(92), '').replace(chr(0), '')
