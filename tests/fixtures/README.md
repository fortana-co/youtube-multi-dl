# Live test fixtures

Tiny, synthetic videos (color + sine tone, no copyrighted content) that exercise
every download path. The live tests in `tests/test_youtube.py` read
`fixtures.json` **in this directory** and skip if it's missing/incomplete, so the
default `pytest` run stays fully offline. Override the path with the
`YMD_FIXTURES` env var if you keep your populated copy elsewhere.

Upload the videos to your YouTube account once, as **Unlisted** (not Private —
yt-dlp can't reach truly private videos without auth cookies), then commit the
filled-in `fixtures.json`.

Regenerate the `.mp4` files any time with `bash generate.sh` (needs ffmpeg).

## Files

| File | Duration | Contents |
|------|----------|----------|
| `album-3-tracks.mp4` | 36s | 3×12s segments — Alpha (red/440Hz), Bravo (green/550Hz), Charlie (blue/660Hz) |
| `playlist-track-01.mp4` | 12s | "Playlist Track One" (purple/330Hz) |
| `playlist-track-02.mp4` | 12s | "Playlist Track Two" (orange/494Hz) |

The three album segments are exactly 12s each, so split boundaries are known:
`0:00–0:12 Alpha`, `0:12–0:24 Bravo`, `0:24–0:36 Charlie`.

## Uploads to create (4 videos + 1 playlist), all Unlisted

1. **Structured-chapters album** — upload `album-3-tracks.mp4`.
   - Title: `ymd test — album (structured chapters)`
   - Description: paste `DESCRIPTION-structured-chapters.txt` (yields real YouTube chapters).

2. **Unstructured-tracklist album** — upload `album-3-tracks.mp4` again (a second video).
   - Title: `ymd test — album (unstructured tracklist)`
   - Description: paste `DESCRIPTION-unstructured-tracklist.txt` (no chapters; agent parses it).

3. **Playlist track 1** — upload `playlist-track-01.mp4`. Title: `ymd test — Playlist Track One`.
4. **Playlist track 2** — upload `playlist-track-02.mp4`. Title: `ymd test — Playlist Track Two`.
5. **Playlist** — create an Unlisted playlist `ymd test — playlist`, add tracks 1 then 2, in order.

Then fill in `fixtures.json` with the video ids / playlist url and commit it.
