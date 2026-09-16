"""Бесплатный конвейер Reels: Pollinations (фото, без ключа) + Edge-TTS (uz, без ключа).

Зачем: Veo через API на free-tier = 0/0/0 (429), биллинг — расход против цели.
Этот модуль даёт посты с НУЛЕМ затрат уже сегодня.
Контракт совместим с gemini_video: generate_thirty_second_video(beats, dest, ...).
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from pathlib import Path
from urllib.parse import quote

import config
from config import VIDEO_DIR

logger = logging.getLogger(__name__)

POLLI_BASE = "https://image.pollinations.ai/prompt"
TTS_VOICE_MALE = "uz-UZ-SardorNeural"
TTS_VOICE_FEMALE = "uz-UZ-MadinaNeural"

IMG_W, IMG_H = 720, 1280


class FreeReelError(RuntimeError):
    pass


def extract_spoken(beats: dict[str, str]) -> dict[str, str]:
    """Вытащить o'zbek реплики из beat-промптов Veo (saying exactly: "...")."""
    out: dict[str, str] = {}
    for key in sorted(beats):
        m = re.search(r'saying exactly:\s*"(.+?)"', beats[key], re.S)
        if m:
            out[key] = m.group(1).strip()
        else:
            # fallback: весь beat как текст (обрежем)
            out[key] = beats[key][:200]
    return out


def _polli_url(prompt: str, seed: int) -> str:
    clean = f"{prompt}, vertical 9:16 photorealistic, no text, no watermark, no logo"
    return f"{POLLI_BASE}/{quote(clean[:800])}?width={IMG_W}&height={IMG_H}&nologo=true&model=flux&seed={seed}"


def fetch_image(prompt: str, dest: Path, seed: int | None = None) -> Path:
    import requests

    dest.parent.mkdir(parents=True, exist_ok=True)
    base_seed = seed if seed is not None else random.randint(1, 999999)
    # Короткий безопасный промпт: Pollinations 500 на длинных/спорных
    short = re.sub(r'\s+', ' ', prompt).strip()[:300]
    errs: list[str] = []
    for attempt in range(3):
        s = base_seed + attempt * 131
        url = _polli_url(short, s)
        logger.info("polli try%s seed=%s", attempt + 1, s)
        try:
            r = requests.get(url, timeout=180)
        except Exception as exc:
            errs.append(str(exc)[:120])
            continue
        if r.ok and len(r.content) >= 5000:
            dest.write_bytes(r.content)
            return dest
        errs.append(f"HTTP {r.status_code}")
        time.sleep(3)
    # Fallback 1: picsum (случайное фото, бесплатно, без ключа)
    try:
        r = requests.get(f"https://picsum.photos/seed/{base_seed}/720/1280", timeout=60)
        if r.ok and len(r.content) >= 5000:
            logger.warning("polli failed %s -> picsum fallback", errs)
            dest.write_bytes(r.content)
            return dest
    except Exception as exc:
        errs.append(str(exc)[:120])
    # Fallback 2: градиент PIL, чтобы конвейер не вставал никогда
    logger.warning("polli+picsum failed %s -> PIL placeholder", errs)
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (IMG_W, IMG_H), (18, 18, 40))
    dr = ImageDraw.Draw(img)
    for y in range(IMG_H):
        dr.line([(0, y), (IMG_W, y)], fill=(18, 18 + y * 40 // IMG_H, 60 + y * 60 // IMG_H))
    dr.text((40, 600), short[:60], fill=(255, 255, 255))
    img.save(dest, "JPEG", quality=85)
    return dest


async def tts_uz(text: str, dest: Path, voice: str = "") -> Path:
    """Edge-TTS uz, бесплатно, без ключа. Мужской Sardor для Motiva."""
    import edge_tts

    dest.parent.mkdir(parents=True, exist_ok=True)
    voice = voice or TTS_VOICE_MALE
    # Edge режет длинные куски — бьем по предложениям, клеим ffmpeg-ом
    communicate = edge_tts.Communicate(text, voice)
    try:
        await communicate.save(str(dest))
    except Exception as exc:
        raise FreeReelError(f"Edge-TTS xato: {exc}") from exc
    if not dest.exists() or dest.stat().st_size < 500:
        raise FreeReelError("Edge-TTS bo'sh audio")
    return dest


def _audio_duration(path: Path) -> float:
    from media import duration_seconds

    d = duration_seconds(path)
    return max(2.0, min(d or 6.0, 15.0))


def image_audio_to_clip(img: Path, audio: Path, dest: Path) -> Path:
    """Фото + аудио -> движущийся 9:16 клип (медленный зум, Ken Burns)."""
    import subprocess

    from media import duration_seconds, has_ffmpeg

    if not has_ffmpeg():
        raise FreeReelError("ffmpeg yo'q")
    dur = _audio_duration(audio)
    # zoompan: лёгкий наезд за весь клип, 30fps
    vf = (
        "scale=1440:2560:force_original_aspect_ratio=increase,"
        "crop=1440:2560,"
        f"zoompan=z='min(zoom+0.0008,1.15)':d={int(dur * 30)}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':fps=30,"
        "scale=720:1280:force_original_aspect_ratio=decrease,"
        "pad=720:1280:(ow-iw)/2:(oh-ih)/2:black,"
        "format=yuv420p"
    )
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(img),
        "-i", str(audio),
        "-vf", vf,
        "-map", "0:v:0", "-map", "1:a:0",
        "-t", f"{dur:.1f}",
        "-c:v", "libx264", "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart",
        "-shortest",
        str(dest),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if r.returncode != 0 or not dest.exists() or dest.stat().st_size < 1000:
        raise FreeReelError(f"ffmpeg clip failed: {(r.stderr or '')[-500:]}")
    logger.info("clip %s %.1fs", dest.name, duration_seconds(dest))
    return dest


async def generate_free_reel_video(
    beats: dict[str, str],
    dest: Path,
    *,
    reference_image: Path | None = None,
    voice_id: str | None = None,
    seed_base: int | None = None,
) -> Path:
    """5 битов: картинка Pollinations + озвучка Edge-TTS + склейка. Совместимо с pipeline."""
    from media import concat_videos, duration_seconds

    dest.parent.mkdir(parents=True, exist_ok=True)
    keys = [k for k in (f"beat{i}" for i in range(1, 6)) if beats.get(k)]
    if len(keys) < 3:
        raise FreeReelError("ssenariyda beat yetarli emas")
    spoken = extract_spoken(beats)
    base_seed = seed_base if seed_base is not None else int(time.time()) % 100000

    segments: list[Path] = []
    for i, key in enumerate(keys):
        img = dest.with_name(f"{dest.stem}_{key}_free.jpg")
        aud = dest.with_name(f"{dest.stem}_{key}_free.mp3")
        seg = dest.with_name(f"{dest.stem}_{key}_free.mp4")
        if not img.exists() or img.stat().st_size < 5000:
            await asyncio.to_thread(fetch_image, beats[key], img, base_seed + i * 777)
        await tts_uz(spoken.get(key, ""), aud)
        await asyncio.to_thread(image_audio_to_clip, img, aud, seg)
        segments.append(seg)

    await asyncio.to_thread(concat_videos, segments, dest)
    logger.info("free reel %s (%.1fs)", dest, duration_seconds(dest))
    return dest


# Алиас под контракт pipeline (как generate_thirty_second_video)
async def generate_thirty_second_video(
    beats: dict[str, str],
    dest: Path,
    *,
    reference_image: Path | None = None,
    voice_id: str | None = None,
) -> Path:
    return await generate_free_reel_video(beats, dest, reference_image=reference_image, voice_id=voice_id)


async def invent_script_free(topic: str | None = None, avoid: list[str] | None = None) -> dict:
    """Сценарий: пробуем Gemini-Lite (бесплатный), иначе локальный шаблон из persona."""
    avoid = avoid or []
    # 1) пробуем дешёвую текстовую модель (3.1-flash-lite свободен 10/500)
    for model in ("models/gemini-2.5-flash-lite", "models/gemini-2.0-flash-lite"):
        try:
            from google import genai

            from gemini_video import _parse_llm_json, _beat_visual, VEO_CLIP_SECONDS
            from persona import load_persona

            key = (config.GEMINI_API_KEY or "").strip()
            if not key:
                break
            client = genai.Client(api_key=key)
            p = load_persona()
            sys = (
                "Sen O'zbekiston Instagram Reels uchun viral ssenarist san. Faqat JSON. "
                "Og'zaki nutq va caption — FAQAT o'zbek lotin. Ruscha YO'Q."
            )
            usr = (
                f"Mavzu: {topic or 'yangi davrni o\'zing tanla (Toshkent 2100, Mars, Misr, SSSR)'}.\n"
                f"Oxirgilari (takrorlama): {', '.join(avoid[:10]) or 'yo\'q'}.\n"
                'JSON: {"idea":"1 qator","hook":"6-10 so\'z shok","era":"English","setting":"English",'
                '"spoken1":"..","spoken2":"..","spoken3":"..","spoken4":"..","spoken5":"..","caption":"2-4 gap + CTA + #sayohat #toshkent #motivstileai"}'
            )
            resp = await asyncio.to_thread(client.models.generate_content, model, [sys, usr])
            data = _parse_llm_json(getattr(resp, "text", "") or "")
            name = str(p.get("name") or "Motiv")
            era = str(data.get("era") or "Tashkent future")
            setting = str(data.get("setting") or "cinematic light")
            for i in range(1, 6):
                line = str(data.get(f"spoken{i}") or data.get("hook") or "").strip()
                data[f"spoken{i}"] = line
                data[f"beat{i}"] = _beat_visual(i, line, era, setting, name)
            data["video_prompt"] = __import__("json").dumps(
                {f"beat{i}": data[f"beat{i}"] for i in range(1, 6)}, ensure_ascii=False
            )
            logger.info("script via %s ok", model)
            return data
        except Exception as exc:
            logger.warning("script %s failed: %s", model, str(exc)[:200])
            continue
    # 2) локальный fallback — без LLM вообще
    from persona import load_persona

    p = load_persona()
    bank = [t for t in (p.get("viral_topics") or []) if t not in avoid] or (p.get("viral_topics") or ["Toshkent 2100"])
    idea = topic or random.choice(bank)
    hook = f"{idea} — buni ko'rmasang, ko'p narsani yo'qotasan!"
    sp = [
        hook,
        f"{idea}. Atrofda g'ayrioddiy manzara, havo boshqa, odamlar boshqa.",
        "Lekin eng qizig'i — bu yerda ham o'zimizning mehmondo'stlik saqlangan.",
        "Kelajak qancha o'zgarmasin, milliyligimiz yo'qolmaydi.",
        str(p.get("cta") or "Saqla. Keyin qayerga uchay? Kommentga yoz."),
    ]
    data: dict = {"idea": idea, "hook": hook, "era": idea, "setting": "cinematic photorealistic",
                  "caption": f"{idea}! {p.get('cta')} #sayohat #toshkent #motivstileai"}
    name = str(p.get("name") or "Motiv")
    from gemini_video import _beat_visual

    for i, line in enumerate(sp, 1):
        data[f"spoken{i}"] = line
        data[f"beat{i}"] = _beat_visual(i, line, idea, "cinematic photorealistic", name)
    data["spoken"] = " ".join(sp)
    data["video_prompt"] = __import__("json").dumps({f"beat{i}": data[f"beat{i}"] for i in range(1, 6)}, ensure_ascii=False)
    return data


def next_video_path(post_id: int) -> Path:
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    return VIDEO_DIR / f"post_{post_id}_free.mp4"
