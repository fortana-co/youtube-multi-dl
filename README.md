# youtube-multi-dl
![License](https://camo.githubusercontent.com/890acbdcb87868b382af9a4b1fac507b9659d9bf/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f6c6963656e73652d4d49542d626c75652e737667)

__youtube-multi-dl__ makes it super easy to download and label music from YouTube. It handles single songs, [playlists](https://www.youtube.com/watch?v=PlnanwD_vS0&index=1&list=PLcOYKKFxnwAdGh4NCgpXq_FNQoZKL6xWM), and [single-song](https://www.youtube.com/watch?v=SDeuYY3Hi_I) [albums](https://www.youtube.com/watch?v=eTYushgUR00) (it splits them by chapters).

It gives them ID3 tags so they're correctly grouped and ordered, and ready for whatever music player you use. If you pass `-S`, it strips artist and album names from song titles.

It's a wrapper around the amazing [youtube-dl](https://github.com/rg3/youtube-dl). It's built to be as simple as possible:

~~~sh
# download and label tracks 1-10 of this playlist by "Star Band de Dakar"
youtube-multi-dl "https://www.youtube.com/watch?v=PlnanwD_vS0&index=1&list=PLcOYKKFxnwAdGh4NCgpXq_FNQoZKL6xWM" -a "Star Band de Dakar" -p "1-10" -S

# download "Nilsson Schmilsson" from a single vid, split it by chapters, and label each song
youtube-multi-dl eTYushgUR00 -a "Harry Nilsson" -A "Nilsson Schmilsson" -S

# download this Lucinda Williams album from a list of single-song URLs/IDs
youtube-multi-dl vWyXoGUdj4U 9R_dkP2duog qAJ8OCqe0v4 qWJCu3d6EX0 dPr0Iyh0z60 4VMUjcQ2ggs haUHiHVTvtg IOCPe_ff2RE ihuPM-xiCqY pjYxBxGSNnY HrSEeNE_Uzw cpP11qYuhg8 -a "Lucinda Williams" -A "Sweet Old World" -S

# download this Pharoah Sanders album from a single vid, split it by chapters, and label each song; youtube-multi-dl guesses at the album name from the video metadata
youtube-multi-dl SDeuYY3Hi_I -a "Pharoah Sanders" -S
~~~


## Installation
`pip3 install youtube-multi-dl`

`youtube-multi-dl` requires Python 3. Use `pip3` to install it. If you don't have Python 3, you can install it with your package manager:

- __macOS__: `brew install python`


### Deps
Like `youtube-dl`, `youtube-multi-dl` depends on [FFmpeg](https://www.ffmpeg.org/). On most platforms, you can install FFmpeg using a package manager.

- __macOS__: `brew install ffmpeg`
- __Ubuntu__: `sudo apt install ffmpeg`


## Usage
__youtube-multi-dl__ makes a folder with the album name and downloads songs into this folder. It makes the folder in your current working directory. This means you might want to `cd ~/Desktop` or something like that before running it.

__youtube-multi-dl__ tries to be a good CLI tool. Run `youtube-multi-dl -h` to see a help message with all the args you can pass.


### Required Arguments
- `url`: URL or ID of YouTube playlist or video with chapters, or list of single-song URLs
- `-a` ARTIST, `--artist` ARTIST


### Optional Arguments
- `-A` ALBUM, `--album` ALBUM
- `-p` PLAYLIST_ITEMS, `--playlist-items` PLAYLIST_ITEMS: playlist tracks to download; e.g. "1,3-5,7-9,11,12"
- `-t` TRACK_NUMBERS, `--track-numbers` TRACK_NUMBERS: track numbers to assign to playlist items; must have same length as playlist items
- `-r`, `--remove-chapters-source-file`: for video with chapters, remove source file after download
- `-s` STRIP_PATTERNS [STRIP_PATTERNS ...], `--strip-patterns` STRIP_PATTERNS [STRIP_PATTERNS ...]: remove patterns from title(s)
- `-S`, `--strip-meta`: remove artist and album names from title(s)


### File Names
It might look like __youtube-multi-dl__ isn't doing a great job of cleaning file names. You pass `-S` but it doesn't strip the artist/album name! It leaves the YouTube video ID in there!

This is how it's supposed to work; __youtube-multi-dl__ needs the meta info in the file name. What it actually cleans is the song's title (the __ID3 title tag__). This determines the name of the track in your music player.


## Contributing
Fork the repo and submit a PR. Create an issue if something is broke!


### Development
See `main.py` in the root of the repo? This script makes it easy to test the package. It ensures __youtube-multi-dl__ can be invoked from the command line, without going through the shim created by `setuptools` when the package is installed.

For example, from the root of the repo, just run `python3 main.py SDeuYY3Hi_I -a "Pharoah Sanders" -S`.


### Style
Uses [yapf](https://github.com/google/yapf). Run `cd .git/hooks && ln -s -f ../../pre-push` to add `pre-push` hook to ensure you can't push anything that doesn't pass yapf check.

Run `pip3 install yapf` to install yapf, and run `yapf -i -r youtube_multi_dl` to format source files in place.


### Wish List
Some single-song albums aren't divided into chapters, [like this one](https://www.youtube.com/watch?v=fEqrnR7_yT8). But if you look at the description, it clearly has metadata about the songs in the album. Can we find and parse this metadata so __youtube-multi-dl__ can split videos like this into individual songs, the way it does for videos with chapters?


## License
This code is licensed under the [MIT License](https://opensource.org/licenses/MIT).


## Thanks
To the maintainers of __youtube-dl__, [Mutagen](https://github.com/quodlibet/mutagen) and __FFmpeg__, and to anyone who doesn't want every last song to disappear behind ads or a paywall.
