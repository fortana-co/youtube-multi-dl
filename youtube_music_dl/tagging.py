"""
Per-format audio tagging and provenance/idempotency helpers.

We support exactly two output formats:

- **mp3**  -> ID3 tags (via `EasyID3`), for maximum device compatibility.
- **opus** -> Vorbis comments (via `OggOpus`), the modern default.

Both carry the same logical fields, including a custom `youtube_video_id` provenance tag. That tag travels with the
file (surviving moves/renames), and is what we read back to decide whether a video has already been downloaded.
"""

from pathlib import Path

from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3NoHeaderError
from mutagen.oggopus import OggOpus

# Custom provenance field. On mp3 this needs a one-time TXXX registration; on
# opus (Vorbis comments) arbitrary keys just work.
PROVENANCE_KEY = "youtube_video_id"
EasyID3.RegisterTXXXKey(PROVENANCE_KEY, PROVENANCE_KEY)

SUPPORTED_EXTENSIONS = (".mp3", ".opus")


def tag_audio(
    path: Path,
    *,
    title: str,
    artist: str,
    album: str,
    tracknumber: str,
    youtube_video_id: str | None,
) -> None:
    """Write the canonical tags to `path`, dispatching on its extension."""
    ext = path.suffix.lower()
    if ext == ".mp3":
        try:
            audio = EasyID3(str(path))
        except ID3NoHeaderError:
            audio = EasyID3()
    elif ext == ".opus":
        audio = OggOpus(str(path))
    else:
        raise ValueError(f"unsupported audio extension for tagging: {ext}")

    audio["title"] = title
    audio["artist"] = artist
    audio["album"] = album
    audio["tracknumber"] = tracknumber
    if youtube_video_id:
        audio[PROVENANCE_KEY] = youtube_video_id
    audio.save(str(path))


def update_tags(path: Path, *, artist: str | None = None, album: str | None = None) -> None:
    """Change only the artist and/or album, leaving title, track number, and provenance intact."""
    ext = path.suffix.lower()
    if ext == ".mp3":
        try:
            audio = EasyID3(str(path))
        except ID3NoHeaderError:
            audio = EasyID3()
    elif ext == ".opus":
        audio = OggOpus(str(path))
    else:
        raise ValueError(f"unsupported audio extension for tagging: {ext}")

    if artist is not None:
        audio["artist"] = artist
    if album is not None:
        audio["album"] = album
    audio.save(str(path))


def read_provenance(path: Path) -> str | None:
    """Return the `youtube_video_id` tag from an audio file, or None."""
    ext = path.suffix.lower()
    try:
        if ext == ".mp3":
            audio = EasyID3(str(path))
        elif ext == ".opus":
            audio = OggOpus(str(path))
        else:
            return None
    except Exception:
        return None
    value = audio.get(PROVENANCE_KEY)
    return value[0] if value else None


def existing_files_by_id(directory: Path) -> dict[str, list[Path]]:
    """Map each already-downloaded youtube_video_id to the file(s) carrying it.

    Used for idempotency: a video whose id is already present is skipped. Chapter
    splits produce several files that share the source video's id, hence a list.
    """
    by_id: dict[str, list[Path]] = {}
    if not directory.is_dir():
        return by_id
    for path in sorted(directory.iterdir()):
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        video_id = read_provenance(path)
        if video_id:
            by_id.setdefault(video_id, []).append(path)
    return by_id
