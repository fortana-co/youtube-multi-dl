from setuptools import setup


setup(
    name='youtube-dl-playlist',
    version='0.1.0',
    description='Download and label playlists from YouTube using youtube-dl',
    long_description='Check it out on GitHub',
    keywords='youtube youtube-dl mp3 download playlist',
    url='https://github.com/fortana-co/youtube-dl-playlist',
    download_url='https://github.com/fortana-co/youtube-dl-playlist/tarball/0.1.0',
    author='kylebebak',
    author_email='kylebebak@gmail.com',
    license='MIT',
    packages=['youtube_dl_playlist'],
    entry_points={
        'console_scripts': ['youtube-dl-playlist=youtube_dl_playlist.command_line:main'],
    },
    install_requires=[
        'youtube-dl',
        'mutagen',
    ],
    classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
    ],
)
