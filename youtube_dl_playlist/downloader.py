import os
import sys
import glob
import subprocess

import youtube_dl
from mutagen.easyid3 import EasyID3


def downloader(url, artist, album='', playlist_items='', keep_id=False, keep_source_file=False):
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

    album = album or info['title']
    directory = './{}'.format(album)
    try:
        os.makedirs(directory)
    except FileExistsError as e:
        sys.exit("{}\n\nyoutube-dl-playlist can't overwrite existing directories".format(e))
    os.chdir(directory)

    with youtube_dl.YoutubeDL(download_opts) as ydl:
        ydl.download([url])

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
                if not keep_id:
                    os.rename(
                        file,
                        ''.join(file.split('-{}'.format(track_info['id']))),
                    )

    if info.get('extractor') == 'youtube':
        source_file = glob.glob('*{}.mp3'.format(info['id']))[0]
        chapters = info.get('chapters')
        if not chapters:
            sys.exit('monolithic file with no chapters')

        for i, chapter in enumerate(chapters):
            start_time = chapter['start_time']
            end_time = chapter['end_time']
            title = chapter.get('title') or str(i + 1)
            file = clean('{}.mp3'.format(title))
            command = [
                'ffmpeg', '-i', source_file, '-acodec', 'copy', '-ss', str(start_time), '-to', str(end_time), file,
            ]
            subprocess.check_output(command)
            set_audio_id3(
                file,
                title=title,
                artist=artist,
                album=album,
                tracknumber='{}/{}'.format(i + 1, len(chapters)),
            )


def set_audio_id3(file, **kwargs):
    audio = EasyID3(file)
    for k, v in kwargs.items():
        audio[k] = v
    audio.save()


def clean(file):
    return file.replace('/', '').replace(chr(92), '').replace(chr(0), '')
