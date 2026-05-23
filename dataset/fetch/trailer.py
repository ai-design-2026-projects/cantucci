from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

log = logging.getLogger(__name__)


def _ydl_opts(outdir: Path, client: str | None = None) -> dict:
    """
    yt-dlp configuration for downloading the smallest usable
    video stream for frame extraction.
    """

    opts = {
        # prefer small downloadable video
        "format": (
            "worstvideo[height>=240]/"
            "worst[height>=240]/"
            "bestvideo[height<=480]/"
            "best"
        ),

        "outtmpl": str(outdir / "%(id)s.%(ext)s"),

        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,

        "retries": 5,
        "fragment_retries": 5,

        "skip_unavailable_fragments": True,
        "ignoreerrors": False,
        "geo_bypass": True,
        "nocheckcertificate": True,
    }

    # only specify client if requested
    if client is not None:
        opts["extractor_args"] = {
            "youtube": {
                "player_client": [client]
            }
        }

    return opts


def _download(youtube_key: str, outdir: Path) -> Path:
    """
    Download a single YouTube video into outdir.

    Tries multiple YouTube clients because yt-dlp
    periodically breaks for some clients.
    """
    import yt_dlp

    url = f"https://www.youtube.com/watch?v={youtube_key}"

    # ordered fallback clients
    clients = [
        None,        # let yt-dlp choose
        "web",
        "android",
        "ios",
        "mweb",
    ]

    last_error = None

    for client in clients:
        try:
            with yt_dlp.YoutubeDL(
                _ydl_opts(outdir, client)
            ) as ydl:

                info = ydl.extract_info(
                    url,
                    download=True,
                )

                if info is None:
                    raise RuntimeError(
                        "yt-dlp returned no info"
                    )

                path = Path(
                    ydl.prepare_filename(info)
                )

                if path.exists():
                    log.info(
                        "download_success",
                        extra={
                            "youtube_key": youtube_key,
                            "client": client,
                        },
                    )
                    return path

        except yt_dlp.utils.DownloadError as exc:
            msg = str(exc)
            last_error = msg

            # DRM videos cannot be downloaded
            if "DRM protected" in msg:
                log.warning(
                    "drm_video",
                    extra={
                        "youtube_key": youtube_key,
                        "client": client,
                    },
                )
                continue

            log.warning(
                "download_failed",
                extra={
                    "youtube_key": youtube_key,
                    "client": client,
                    "error": msg,
                },
            )

        except Exception as exc:
            last_error = str(exc)

    raise RuntimeError(
        f"Failed to download {youtube_key}. "
        f"Last error: {last_error}"
    )


def _video_duration_s(path: Path) -> float:
    """
    Return video duration in seconds using ffprobe.
    """
    out = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    return float(out.stdout.strip())


def _extract_frames(
    video: Path,
    n_frames: int,
    outdir: Path,
) -> list[Path]:
    """
    Extract evenly spaced frames.

    Drops first/last 5% to avoid
    black intro/outro cards.
    """
    duration = _video_duration_s(video)

    start = duration * 0.05
    end = duration * 0.95

    span = max(end - start, 1e-3)

    timestamps = [
        start + span * (i + 0.5) / n_frames
        for i in range(n_frames)
    ]

    frame_paths: list[Path] = []

    for i, ts in enumerate(timestamps):
        frame_path = (
            outdir / f"frame_{i:03d}.jpg"
        )

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-ss",
                f"{ts:.3f}",
                "-i",
                str(video),
                "-frames:v",
                "1",
                "-q:v",
                "3",
                str(frame_path),
            ],
            check=True,
        )

        frame_paths.append(frame_path)

    return frame_paths


def fetch_frames(
    youtube_key: str,
    n_frames: int = 16,
) -> list[Image.Image]:
    """
    Download YouTube video and return
    evenly sampled PIL frames.

    Returns [] on failure instead of
    crashing batch pipelines.
    """
    if not youtube_key:
        return []

    if n_frames < 1:
        raise ValueError(
            f"n_frames must be >= 1, got {n_frames}"
        )

    with tempfile.TemporaryDirectory(
        prefix="trailer_"
    ) as td:

        tmp = Path(td)

        try:
            video = _download(
                youtube_key,
                tmp,
            )

            frame_paths = _extract_frames(
                video,
                n_frames,
                tmp,
            )

            images = [
                Image.open(p)
                .convert("RGB")
                .copy()
                for p in frame_paths
            ]

            log.info(
                "fetch_frames_success",
                extra={
                    "youtube_key": youtube_key,
                    "n_frames": len(images),
                },
            )

            return images

        except Exception as exc:
            log.warning(
                "fetch_frames_failed",
                extra={
                    "youtube_key": youtube_key,
                    "error": str(exc),
                },
            )

            # caller maps [] -> zero embedding
            return []