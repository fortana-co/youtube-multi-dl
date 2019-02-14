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
        text = input('(d)ownload again, (s)kip download but continue, (e)xit: ')
        if text.lower() == 'd':
            pass
        elif text.lower() == 's':
            download = False
        elif text.lower() == 'e':
            print('\nexiting...')
            sys.exit(0)
        else:
            sys.exit('\n`{}` not a recognized option, exiting...'.format(text))

    os.chdir(directory)

    # single file, no chapters
    if info.get('extractor') == 'youtube' and not info.get('chapters'):
        print('\nthis video is not a playlist, and it has no chapters, are you sure you want to proceed?')
        text = input('(y)es, (n)o: ')
        if text.lower() == 'y':
            pass
        elif text.lower() == 'n':
            print('\nexiting...')
            sys.exit(0)
        else:
            sys.exit('\n`{}` not a recognized option, exiting...'.format(text))

        if download:
            with youtube_dl.YoutubeDL(download_opts) as ydl:
                ydl.download([url])

        files = glob.glob('*{}.mp3'.format(info['id']))
        if files:
            set_audio_id3(
                files[0],
                artist=artist,
                album=album,
            )
        sys.exit(0)

    if download:
        with youtube_dl.YoutubeDL(download_opts) as ydl:
            ydl.download([url])

    # single file with chapters
    if info.get('extractor') == 'youtube':
        split = True
        files = glob.glob('*{}.mp3'.format(info['id']))
        if not(files):
            split = False

        chapters = info.get('chapters')

        for i, chapter in enumerate(chapters):
            start_time = chapter['start_time']
            end_time = chapter['end_time']
            title = chapter.get('title') or str(i + 1)
            file = clean_filename('{}.mp3'.format(title))
            if split:
                cmd = ['ffmpeg', '-i', files[0], '-acodec', 'copy', '-ss', str(start_time), '-to', str(end_time), file]
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
                os.remove(file)
            except:
                pass

    # playlist
    if info.get('extractor') == 'youtube:playlist':
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
