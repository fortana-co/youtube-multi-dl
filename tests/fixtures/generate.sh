#!/bin/bash

# Regenerate the fixture videos (requires ffmpeg). Run: bash generate.sh Each is tiny: color + sine tone, no copyrighted
# content. Segments are 12s so the 3-track album qualifies for YouTube auto-chapters.

set -e
cd "$(dirname "$0")"

seg () { # color hz outfile
  ffmpeg -y -hide_banner -loglevel error \
    -f lavfi -i "color=c=$1:size=320x240:rate=15" \
    -f lavfi -i "sine=frequency=$2" -t 12 \
    -c:v libx264 -pix_fmt yuv420p -c:a aac "$3"
}

# 3-segment album: Alpha (red/440), Bravo (green/550), Charlie (blue/660)
seg red 440 seg1.mp4
seg green 550 seg2.mp4
seg blue 660 seg3.mp4
printf "file 'seg1.mp4'\nfile 'seg2.mp4'\nfile 'seg3.mp4'\n" > concat.txt
ffmpeg -y -hide_banner -loglevel error -f concat -safe 0 -i concat.txt -c copy album-3-tracks.mp4
rm -f seg1.mp4 seg2.mp4 seg3.mp4 concat.txt

# two standalone playlist tracks
seg purple 330 playlist-track-01.mp4
seg orange 494 playlist-track-02.mp4

echo "generated: album-3-tracks.mp4, playlist-track-01.mp4, playlist-track-02.mp4"
