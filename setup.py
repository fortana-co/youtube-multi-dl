from setuptools import setup


setup(
    name='youtube-multi-dl',
    version='2.0.0',
    description='Download and label albums and playlists from YouTube using yt-dlp',
    long_description='Check it out on GitHub',
    keywords='youtube yt-dlp mp3 download playlist album chapters file id3',
    url='https://github.com/fortana-co/youtube-multi-dl',
    download_url='https://github.com/fortana-co/youtube-multi-dl/tarball/2.0.0',
    author='kylebebak',
    author_email='kylebebak@gmail.com',
    license='MIT',
    packages=['youtube_multi_dl'],
    entry_points={
        'console_scripts': ['youtube-multi-dl=youtube_multi_dl.command_line:main'],
    },
    install_requires=[
        'yt-dlp',
        'mutagen',
    ],
    classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
    ],
)
