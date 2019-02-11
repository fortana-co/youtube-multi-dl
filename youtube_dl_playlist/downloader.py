import os
import sys
import glob

import youtube_dl
from mutagen.easyid3 import EasyID3


def downloader(url, artist, album='', playlist_items='', keep_id=False):
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
    directory = f"./{album}"
    try:
        os.makedirs(directory)
    except FileExistsError as e:
        sys.exit(f"{e}\n\nyoutube-dl-playlist can't overwrite existing directories")
    os.chdir(directory)

    with youtube_dl.YoutubeDL(download_opts) as ydl:
        ydl.download([url])

    if info.get('extractor') == 'youtube:playlist':
        for i, entry in enumerate(info.get('entries')):
            with youtube_dl.YoutubeDL(info_opts) as ydl:
                track_info = ydl.extract_info(entry['id'], download=False)
            if not track_info:
                continue
            for file in glob.glob(f"*{track_info['id']}.mp3"):
                audio = EasyID3(file)
                audio['title'] = track_info['title']
                audio['artist'] = artist
                audio['album'] = album
                audio['tracknumber'] = f"{i + 1}/{len(info.get('entries'))}"
                audio.save()
                if not keep_id:
                    os.rename(
                        file,
                        ''.join(file.split(f"-{track_info['id']}")),
                    )
