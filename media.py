from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def has_audio(path: Path) -> bool:
    r = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            str(path),
        ]
    )
    return bool(r.stdout.strip())


def prepare_reel(src: Path) -> Path:
    if not has_ffmpeg():
        logger.warning("ffmpeg нет — отдаю исходник как есть")
        return src
    dest = src.with_name(src.stem + "_reel.mp4")
    vf = (
        "scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,"
        "fps=30,format=yuv420p"
    )
    cmd = ["ffmpeg", "-y", "-i", str(src)]
    if not has_audio(src):
        cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        map_args = ["-map", "0:v:0", "-map", "1:a:0", "-shortest"]
    else:
        map_args = ["-map", "0:v:0", "-map", "0:a:0?"]
    cmd += [
        "-vf",
        vf,
        *map_args,
        "-c:v",
        "libx264",
        "-profile:v",
        "high",
        "-level",
        "4.1",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        "-t",
        "15",
        str(dest),
    ]
    r = _run(cmd)
    if r.returncode != 0 or not dest.exists() or dest.stat().st_size < 1000:
        logger.error("ffmpeg failed: %s", r.stderr[-800:])
        return src
    logger.info("reel ready %s (%s KB)", dest.name, dest.stat().st_size // 1024)
    return dest
