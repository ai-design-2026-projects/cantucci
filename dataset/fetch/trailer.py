from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

log = logging.getLogger(__name__)


def _ydl_opts(
    outdir: Path,
    cookiefile: str | None = None,
    cookies_from_browser: str | None = None,
) -> dict:
    """yt-dlp options targeting the smallest video-bearing format available.

    Uses ``wv*`` (worstvideo*), which matches any format with a video track
    regardless of audio presence. Audio is irrelevant — only frames are used.

    Args:
        outdir:               Directory to write the downloaded file.
        cookiefile:           Path to a Netscape-format cookies file.
        cookies_from_browser: Browser name to extract cookies from (e.g. ``"chrome"``,
                              ``"firefox"``). Ignored when *cookiefile* is set.
    """
    opts: dict = {
        "format": "wv*[height>=240][ext=mp4]/wv*[ext=mp4]/wv*/best",
        "extractor_args": {
            "youtube": {
                "player_client": ["tv", "mweb", "web_safari", "web"],
            },
        },
        "outtmpl": str(outdir / "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "retries": 2,
        "fragment_retries": 2,
    }
    if cookiefile:
        opts["cookiefile"] = cookiefile
    elif cookies_from_browser:
        opts["cookiesfrombrowser"] = (cookies_from_browser,)
    return opts


def _download(
    youtube_key: str,
    outdir: Path,
    cookiefile: str | None = None,
    cookies_from_browser: str | None = None,
) -> Path:
    """Download a single YouTube video to *outdir*; return the resulting file path."""
    import yt_dlp

    url = f"https://www.youtube.com/watch?v={youtube_key}"
    with yt_dlp.YoutubeDL(_ydl_opts(outdir, cookiefile, cookies_from_browser)) as ydl:
        info = ydl.extract_info(url, download=True)
        return Path(ydl.prepare_filename(info))


def _video_duration_s(path: Path) -> float:
    """Return video duration in seconds using ffprobe."""
    out = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True, capture_output=True, text=True,
    )
    return float(out.stdout.strip())


def _extract_frames(video: Path, n_frames: int, outdir: Path) -> list[Path]:
    """Extract *n_frames* evenly-spaced frames from *video* into *outdir* as JPEGs.

    Drops the first and last 5% of the video to avoid logo cards / black frames.
    """
    duration = _video_duration_s(video)
    start = duration * 0.05
    end = duration * 0.95
    span = max(end - start, 1e-3)
    timestamps = [start + span * (i + 0.5) / n_frames for i in range(n_frames)]

    frame_paths: list[Path] = []
    for i, ts in enumerate(timestamps):
        frame_path = outdir / f"frame_{i:03d}.jpg"
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-ss", f"{ts:.3f}",
                "-i", str(video),
                "-frames:v", "1",
                "-q:v", "3",
                str(frame_path),
            ],
            check=True,
        )
        frame_paths.append(frame_path)
    return frame_paths


def fetch_frames(
    youtube_key: str,
    n_frames: int = 16,
    *,
    cookiefile: str | None = None,
    cookies_from_browser: str | None = None,
) -> list[Image.Image]:
    """Download a YouTube trailer and return *n_frames* evenly-spaced PIL images.

    The video is downloaded at a low resolution (>=360p mp4 preferred) into a
    tempdir, frames are sampled with ffmpeg, then everything is cleaned up
    before returning.

    Args:
        youtube_key:          The ``?v=`` portion of a YouTube watch URL.
        n_frames:             Number of frames to sample evenly across the video,
                              excluding the first/last 5%.
        cookiefile:           Path to a Netscape-format cookies file, required when
                              YouTube bot-detection blocks unauthenticated downloads.
        cookies_from_browser: Browser name to extract cookies from (e.g. ``"chrome"``,
                              ``"firefox"``). Ignored when *cookiefile* is set.

    Returns:
        ``n_frames`` PIL images decoded into memory.

    Raises:
        RuntimeError: If yt-dlp or ffmpeg fails. The caller is expected to
            translate this into a zero embedding row for the affected movie.
    """
    if not youtube_key:
        raise ValueError("youtube_key must be a non-empty string")
    if n_frames < 1:
        raise ValueError(f"n_frames must be >= 1, got {n_frames}")

    with tempfile.TemporaryDirectory(prefix="trailer_") as td:
        tmp = Path(td)
        try:
            video = _download(youtube_key, tmp, cookiefile, cookies_from_browser)
        except Exception as exc:
            raise RuntimeError(f"yt-dlp download failed for {youtube_key}: {exc}") from exc

        try:
            frame_paths = _extract_frames(video, n_frames, tmp)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"ffmpeg frame extraction failed for {youtube_key}: {exc}") from exc

        images = [Image.open(p).convert("RGB").copy() for p in frame_paths]

    log.info(
        "fetch_frames",
        extra={"youtube_key": youtube_key, "n_frames": len(images)},
    )
    return images
