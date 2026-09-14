"""Генерация Reels через Gemini: сценарий (gemini-3.6-flash) + видео (Veo 3.1).

Заменяет grok_api как источник видео. Grok-файл оставлен как запасной.
Veo нативно генерит звук/речь, поэтому spoken-реплики идут прямо в промпт.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

import config
from config import CHARACTER_FILE, VIDEO_BEATS, VIDEO_DIR
from persona import load_persona

logger = logging.getLogger(__name__)

VEO_CLIP_SECONDS = 8


class GeminiError(RuntimeError):
    pass


def _api_key() -> str:
    return (config.GEMINI_API_KEY or "").strip()


def gemini_ready() -> bool:
    return bool(_api_key())


def _client():
    from google import genai

    key = _api_key()
    if not key:
        raise GeminiError("GEMINI_API_KEY yo'q. .env_gemini yoki Render env ga qo'y.")
    return genai.Client(api_key=key)


def _text_model() -> str:
    return (config.GEMINI_TEXT_MODEL or "models/gemini-3.6-flash").strip()


def _veo_model() -> str:
    return (config.VEO_MODEL or "models/veo-3.1-fast-generate-preview").strip()


def _parse_llm_json(raw: str) -> dict:
    text = (raw or "").strip()
    start = text.find("{")
    if start < 0:
        raise GeminiError(f"LLM JSON qaytarmadi: {text[:400]}")
    try:
        obj, _end = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError as exc:
        raise GeminiError(f"LLM JSON qaytarmadi: {text[:400]}") from exc
    if not isinstance(obj, dict):
        raise GeminiError(f"LLM JSON object emas: {text[:200]}")
    return obj


def _beat_visual(n: int, spoken: str, era: str, setting: str, name: str) -> str:
    if n == 1:
        action = "First frame stops the scroll: he arrives in this era and looks into camera."
    elif n == VIDEO_BEATS:
        action = "Seamless continuation. Ends looking into camera for the CTA."
    else:
        action = "Seamless continuation. Walks deeper into the scene, one clear camera move."
    line = spoken.strip().strip('"')
    return (
        f"Photorealistic vertical 9:16 Instagram Reels, {era}. {setting}. "
        f"{name}, a young Uzbek man with short dark hair, sharp eyes, dark wool coat "
        f"and black beanie, is the only human. {action} "
        f'He speaks fluent conversational Uzbek, saying exactly: "{line}". '
        f"Native dialogue audio with ambient sounds of the place. "
        f"No on-screen text, no subtitles, no logos, no watermark."
    )


def _invent_script_sync(topic: str | None, avoid: list[str]) -> dict:
    p = load_persona()
    tags = " ".join(p.get("hashtags") or [])
    bank = p.get("viral_topics") or []
    bank_txt = "\n".join(f"- {t}" for t in bank)
    skip = "\n".join(f"- {x}" for x in avoid[:40])
    chosen = topic or (
        "o'zing yangi davrni tanla: o'tmish YOKI kelajak "
        "(Yunoniston, Misr, SSSR, Toshkent 2000, Toshkent 2100, Mars…). takrorlama"
    )
    system = (
        "Sen O'zbekiston Instagram Reels uchun viral ssenarist san. "
        "Faqat JSON qaytar, markdown yo'q. "
        "Og'zaki nutq va caption — FAQAT o'zbek tili, lotin alifbosi (o' / g'). "
        "Ruscha gap YO'Q. Inglizcha faqat era va setting maydonlarida. "
        f"Video {VEO_CLIP_SECONDS * VIDEO_BEATS} soniya, FAQAT Instagram Reels 9:16 vertical. "
        f"{VIDEO_BEATS} ta beat, BIR davr, BIR odam. "
        "Har safar YANGI davr va yangi detal — takrorlama. "
        "Davrni O'ZING tanla — ba'zan o'tmish, ba'zan kelajak."
    )
    beats_json = ",\n".join(
        f'  "spoken{i}": "{8 * (i - 1)}-{8 * i}s, ~18-28 so\'z"'
        for i in range(1, VIDEO_BEATS + 1)
    )
    user = f"""Akaunt: @{p.get('ig_handle')}  personaj: {p.get('name')} — vaqt sayohatchisi
Nisha: {p.get('niche')}
Tomoshabin: {p.get('audience')}
Ohang: {p.get('tone')}
CTA: {p.get('cta')}
Hashtaglar: {tags}
Davr banki:
{bank_txt}
Oxirgi chiqqanlar (takrorlama):
{skip or "- yo'q"}
Berilgan mavzu: {chosen}

{VEO_CLIP_SECONDS * VIDEO_BEATS} soniyalik Instagram Reels 9:16, {VIDEO_BEATS} beat. Suv yo'q. Bir davr. Yuz o'zgarmaydi. Har kuni 8 xil qiziq sayohat.

JSON:
{{
  "idea": "o'zbekcha 1 qator, qayerga uchgani",
  "hook": "birinchi og'zaki gap, 6-10 so'z, shok",
  "era": "English, 6-10 words, place and year",
  "setting": "English visual setting, one sentence, no people description",
{beats_json},
  "caption": "o'zbekcha 2-4 qisqa gap + CTA + hashtaglar, lotin"
}}
"""
    client = _client()
    try:
        resp = client.models.generate_content(
            model=_text_model(), contents=[system, user]
        )
    except Exception as exc:
        raise GeminiError(f"Gemini ssenariy xato: {exc}") from exc
    data = _parse_llm_json(getattr(resp, "text", "") or "")
    for key in ("idea", "hook", "caption"):
        if not data.get(key):
            raise GeminiError(f"Ssenariyda {key} yo'q")
    hook = data["hook"].strip().strip('"')
    era = (data.get("era") or "a vivid historical or future place").strip()
    setting = (data.get("setting") or "cinematic natural light, photorealistic").strip()
    name = str(p.get("name") or "Motiv")
    spoken_lines = []
    for i in range(1, VIDEO_BEATS + 1):
        line = (data.get(f"spoken{i}") or "").strip().strip('"')
        if not line:
            line = hook if i == 1 else str(p.get("cta") or hook)
        spoken_lines.append(line)
        data[f"spoken{i}"] = line
        data[f"beat{i}"] = _beat_visual(i, line, era, setting, name)
    data["hook"] = hook
    data["spoken"] = " ".join(spoken_lines)
    data["video_prompt"] = json.dumps(
        {f"beat{i}": data[f"beat{i}"] for i in range(1, VIDEO_BEATS + 1)},
        ensure_ascii=False,
    )
    return data


async def invent_script(topic: str | None = None, avoid: list[str] | None = None) -> dict:
    return await asyncio.to_thread(_invent_script_sync, topic, avoid or [])


def parse_beats(video_prompt: str) -> dict[str, str]:
    """Тот же контракт, что у grok_api.parse_beats (JSON или plain text)."""
    raw = (video_prompt or "").strip()
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
            beats = {
                k: str(data[k])
                for k in (f"beat{i}" for i in range(1, VIDEO_BEATS + 1))
                if data.get(k)
            }
            if len(beats) >= 3:
                return beats
        except json.JSONDecodeError:
            pass
    cont = "Continue in the same place with the same person. "
    out = {"beat1": raw}
    for i in range(2, VIDEO_BEATS + 1):
        out[f"beat{i}"] = cont + raw
    return out


def _ref_image_part(path: Path | None):
    if not path or not path.exists() or path.stat().st_size < 1000:
        return None
    from google.genai import types

    suf = path.suffix.lower()
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}.get(
        suf, "image/jpeg"
    )
    return types.VideoGenerationReferenceImage(
        image=types.Image(image_bytes=path.read_bytes(), mime_type=mime),
        reference_type="asset",
    )


def _generate_clip_sync(prompt: str, dest: Path, reference_image: Path | None) -> Path:
    from google.genai import types

    dest.parent.mkdir(parents=True, exist_ok=True)
    client = _client()
    ref = _ref_image_part(reference_image)
    kwargs: dict = {
        "aspect_ratio": "9:16",
        "resolution": "720p",
        "duration_seconds": VEO_CLIP_SECONDS,
        "number_of_videos": 1,
        "person_generation": "allow_adult",
        "generate_audio": True,
        "enhance_prompt": True,
    }
    if ref is not None:
        kwargs["reference_images"] = [ref]
    try:
        operation = client.models.generate_videos(
            model=_veo_model(),
            prompt=prompt,
            config=types.GenerateVideosConfig(**kwargs),
        )
    except Exception as exc:
        raise GeminiError(f"Veo start xato: {exc}") from exc
    deadline = time.monotonic() + 600
    while not operation.done:
        if time.monotonic() > deadline:
            raise GeminiError("Veo 10 minutda ulgurmadi")
        time.sleep(20)
        try:
            operation = client.operations.get(operation)
        except Exception as exc:
            raise GeminiError(f"Veo poll xato: {exc}") from exc
    if getattr(operation, "error", None):
        raise GeminiError(f"Veo error: {operation.error}")
    videos = (operation.response.generated_videos or []) if operation.response else []
    if not videos:
        raise GeminiError(f"Veo bo'sh javob: {operation}")
    try:
        videos[0].video.save(str(dest))
    except Exception as exc:
        raise GeminiError(f"Veo save xato: {exc}") from exc
    if not dest.exists() or dest.stat().st_size < 1000:
        raise GeminiError("Veo fayl saqlanmadi")
    logger.info("veo clip saved %s (%s bytes)", dest, dest.stat().st_size)
    return dest


async def generate_video(prompt: str, dest: Path, reference_image: Path | None = None) -> Path:
    # Одна попытка с лицом, при ошибке reference — чистый text-to-video.
    try:
        return await asyncio.to_thread(_generate_clip_sync, prompt, dest, reference_image)
    except GeminiError as exc:
        if reference_image and "reference" in str(exc).lower():
            logger.warning("veo ref failed, retry text-only: %s", exc)
            return await asyncio.to_thread(_generate_clip_sync, prompt, dest, None)
        raise


async def generate_reel_video(
    beats: dict[str, str],
    dest: Path,
    *,
    reference_image: Path | None = None,
    voice_id: str | None = None,
) -> Path:
    """N клипов по 8с через Veo + склейка. voice_id игнорируется (у Veo свой звук)."""
    from media import concat_copy, duration_seconds, extract_last_frame, normalize_clip

    dest.parent.mkdir(parents=True, exist_ok=True)
    keys = [k for k in (f"beat{i}" for i in range(1, VIDEO_BEATS + 1)) if beats.get(k)]
    if len(keys) < 3:
        raise GeminiError("ssenariyda beat yetarli emas")

    face = reference_image
    if (face is None or not face.exists()) and CHARACTER_FILE.exists():
        face = CHARACTER_FILE

    segments: list[Path] = []
    for i, key in enumerate(keys):
        raw = dest.with_name(f"{dest.stem}_{key}.mp4")
        seg = dest.with_name(f"{dest.stem}_{key}_seg.mp4")
        logger.info("veo shot %s/%s %s", i + 1, len(keys), key)
        await generate_video(beats[key], raw, reference_image=face)
        await asyncio.to_thread(normalize_clip, raw, seg, VEO_CLIP_SECONDS)
        logger.info("%s normalized %.1fs", key, duration_seconds(seg))
        segments.append(seg)
        frame = dest.with_name(f"{dest.stem}_{key}_last.jpg")
        await asyncio.to_thread(extract_last_frame, seg, frame)

    await asyncio.to_thread(concat_copy, segments, dest)
    logger.info("reel assembled %s (%.1fs)", dest, duration_seconds(dest))
    return dest


# Совместимость: pipeline ждёт generate_thirty_second_video(...)
async def generate_thirty_second_video(
    beats: dict[str, str],
    dest: Path,
    *,
    reference_image: Path | None = None,
    voice_id: str | None = None,
) -> Path:
    return await generate_reel_video(
        beats, dest, reference_image=reference_image, voice_id=voice_id
    )


def next_video_path(post_id: int) -> Path:
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    return VIDEO_DIR / f"post_{post_id}.mp4"
