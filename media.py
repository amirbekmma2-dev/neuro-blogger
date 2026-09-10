from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from config import VIDEO_TOTAL_DURATION

logger = logging.getLogger(__name__)


def _run(cmd: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    logger.info("ffmpeg %s", " ".join(cmd[:14]))
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, check=False, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        logger.error("ffmpeg timeout %ss", timeout)
        raise RuntimeError(f"ffmpeg timeout {timeout}s") from exc


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


def duration_seconds(path: Path) -> float:
    r = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(path),
        ]
    )
    try:
        return float((r.stdout or "").strip())
    except ValueError:
        return 0.0


def _encode_args() -> list[str]:
    return [
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
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
        "-ar",
        "44100",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
    ]


def extract_last_seconds(src: Path, dest: Path, seconds: int = 10) -> Path:
    if not has_ffmpeg():
        raise RuntimeError("ffmpeg yo'q")
    vf = "fps=30,format=yuv420p"
    cmd = ["ffmpeg", "-y", "-sseof", f"-{seconds}", "-i", str(src)]
    if not has_audio(src):
        cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        maps = ["-map", "0:v:0", "-map", "1:a:0", "-shortest"]
    else:
        maps = ["-map", "0:v:0", "-map", "0:a:0?"]
    cmd += ["-t", str(seconds), "-vf", vf, *maps, *_encode_args(), str(dest)]
    r = _run(cmd)
    if r.returncode != 0 or not dest.exists() or dest.stat().st_size < 1000:
        logger.error("extract failed: %s", (r.stderr or "")[-800:])
        raise RuntimeError("ffmpeg extract failed")
    logger.info("extract %ss -> %s (%.1fs)", seconds, dest.name, duration_seconds(dest))
    return dest


def _with_audio(src: Path) -> Path:
    if has_audio(src):
        return src
    dest = src.with_name(src.stem + "_a.mp4")
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-f",
        "lavfi",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-shortest",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(dest),
    ]
    r = _run(cmd)
    if r.returncode != 0 or not dest.exists():
        logger.error("add audio failed: %s", (r.stderr or "")[-400:])
        return src
    return dest


def concat_videos(parts: list[Path], dest: Path) -> Path:
    if not has_ffmpeg():
        raise RuntimeError("ffmpeg yo'q")
    logger.info("concat start %s", [p.name for p in parts])
    parts = [_with_audio(p) for p in parts]
    if len(parts) == 1:
        shutil.copyfile(parts[0], dest)
        return dest
    n = len(parts)
    cmd: list[str] = ["ffmpeg", "-y"]
    for p in parts:
        cmd += ["-i", str(p)]
    links = "".join(f"[{i}:v:0][{i}:a:0]" for i in range(n))
    fc = f"{links}concat=n={n}:v=1:a=1[v][a]"
    cmd += [
        "-filter_complex",
        fc,
        "-map",
        "[v]",
        "-map",
        "[a]",
        *_encode_args(),
        str(dest),
    ]
    r = _run(cmd)
    if r.returncode != 0 or not dest.exists() or dest.stat().st_size < 1000:
        logger.error("concat failed: %s", (r.stderr or "")[-800:])
        raise RuntimeError("ffmpeg concat failed")
    logger.info("concat %s -> %s (%.1fs)", [p.name for p in parts], dest.name, duration_seconds(dest))
    return dest


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
        *_encode_args(),
        "-t",
        str(VIDEO_TOTAL_DURATION),
        str(dest),
    ]
    r = _run(cmd)
    if r.returncode != 0 or not dest.exists() or dest.stat().st_size < 1000:
        logger.error("ffmpeg failed: %s", (r.stderr or "")[-800:])
        return src
    logger.info("reel ready %s (%s KB, %.1fs)", dest.name, dest.stat().st_size // 1024, duration_seconds(dest))
    return dest
