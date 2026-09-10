from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from pathlib import Path

import httpx

from config import (
    CHARACTER_FILE,
    IMAGE_MODEL,
    LLM_MODEL,
    VIDEO_ASPECT,
    VIDEO_BEATS,
    VIDEO_DURATION,
    VIDEO_EXTEND_MODEL,
    VIDEO_MODEL,
    VIDEO_RESOLUTION,
    VIDEO_DIR,
    VIDEO_TOTAL_DURATION,
    VOICE_ID,
    XAI_BASE,
)
from grok_auth import bearer_token
from persona import load_persona

logger = logging.getLogger(__name__)

_JSON_RE = re.compile(r"\{.*\}", re.S)


class GrokError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    token = bearer_token()
    if not token:
        raise GrokError(
            "Grok ga ulanib bo'lmadi. grok login qil yoki console.x.ai dan XAI_API_KEY qo'y."
        )
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _file_data_uri(path: Path, mime: str | None = None) -> str:
    raw = path.read_bytes()
    suf = path.suffix.lower()
    if not mime:
        mime = {
            ".png": "image/png",
            ".webp": "image/webp",
            ".mp4": "video/mp4",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
        }.get(suf, "image/jpeg")
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


async def chat_text(system: str, user: str, model: str | None = None) -> str:
    payload = {
        "model": model or LLM_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.9,
    }
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{XAI_BASE}/chat/completions", headers=_headers(), json=payload)
        if r.status_code >= 400 and (model or LLM_MODEL) != "grok-4.5":
            logger.warning("LLM %s failed %s, fallback grok-4.5", payload["model"], r.status_code)
            payload["model"] = "grok-4.5"
            r = await client.post(
                f"{XAI_BASE}/chat/completions", headers=_headers(), json=payload
            )
        if r.status_code >= 400:
            raise GrokError(f"Grok LLM ошибка {r.status_code}: {r.text[:500]}")
        data = r.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as exc:
        raise GrokError(f"Странный ответ LLM: {data}") from exc


FACE_LOCK = (
    "IDENTITY LOCK: only one human — the exact same young Uzbek man as reference portrait "
    "<IMAGE_0>: same face, same head shape, same short dark hair, same sharp eyes, "
    "same dark wool coat and black beanie. Do not morph, recast, age, or change the face "
    "or head after this scene. Camera and world may move; the person stays identical."
)


def _parse_llm_json(raw: str) -> dict:
    text = (raw or "").strip()
    start = text.find("{")
    if start < 0:
        raise GrokError(f"LLM JSON qaytarmadi: {text[:400]}")
    try:
        obj, _end = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError as exc:
        raise GrokError(f"LLM JSON qaytarmadi: {text[:400]}") from exc
    if not isinstance(obj, dict):
        raise GrokError(f"LLM JSON object emas: {text[:200]}")
    return obj


def parse_beats(video_prompt: str) -> dict[str, str]:
    raw = (video_prompt or "").strip()
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
            beats = {k: str(data[k]) for k in (f"beat{i}" for i in range(1, VIDEO_BEATS + 1)) if data.get(k)}
            if len(beats) >= 3:
                return beats
        except json.JSONDecodeError:
            pass
    return {
        "beat1": raw,
        "beat2": "Continue from last frame. Same person, same face. " + raw,
        "beat3": "Continue from last frame. Same person, same face. " + raw,
        "beat4": "Continue from last frame. Same person, same face. " + raw,
        "beat5": "Continue from last frame. Same person, same face. " + raw,
        "beat6": "Continue from last frame. Same person looks into camera. " + raw,
    }


def _beat_visual(n: int, spoken: str, era: str, setting: str) -> str:
    if n == 1:
        action = (
            "First frame stops the scroll: he arrives in this era, looks into camera, then the world."
        )
    elif n == VIDEO_BEATS:
        action = (
            "Seamless continue from the previous last frame. Ends looking into camera for the CTA."
        )
    else:
        action = "Seamless continue from the previous last frame. Walk deeper, one clear camera move."
    line = spoken.strip().strip('"')
    return (
        f"Photorealistic vertical 9:16, {era}. {setting}. "
        f"The person from <IMAGE_0> is the only human. {action} "
        f'They speak fluent conversational Uzbek saying exactly: "{line}". '
        f"Voice from <AUDIO_0>. {FACE_LOCK} No on-screen text, no subtitles, no logos, no watermark."
    )


async def invent_script(topic: str | None = None, avoid: list[str] | None = None) -> dict:
    p = load_persona()
    tags = " ".join(p.get("hashtags") or [])
    bank = p.get("viral_topics") or []
    bank_txt = "\n".join(f"- {t}" for t in bank)
    skip = "\n".join(f"- {x}" for x in (avoid or [])[:12])
    chosen = topic or (
        "o'zing yangi davrni tanla: o'tmish YOKI kelajak "
        "(Yunoniston, Misr, SSSR, Toshkent 2000, Toshkent 2100, Mars…). takrorlama"
    )
    system = (
        "Sen O'zbekiston Instagram Reels uchun viral ssenarist san. "
        "Faqat JSON qaytar, markdown yo'q. "
        "Og'zaki nutq va caption — FAQAT o'zbek tili, lotin alifbosi (o' / g'). "
        "Ruscha gap YO'Q. Inglizcha faqat era va setting maydonlarida. "
        "Video 30 soniya: 3 ta 10 soniyalik beat, BIR davr, BIR odam. "
        "Davrni O'ZING tanla — ba'zan o'tmish, ba'zan kelajak."
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

30 soniyalik Reels, 3 beat x 10s. Suv yo'q. Bir davr. Yuz o'zgarmaydi.

JSON:
{{
  "idea": "o'zbekcha 1 qator, qayerga uchgani",
  "hook": "birinchi og'zaki gap, 6-10 so'z, shok",
  "era": "English, 6-10 words, place and year",
  "setting": "English visual setting, one sentence, no people description",
  "spoken1": "0-10s hook, ~18-28 so'z",
  "spoken2": "10-20s dunyo ichida, ~18-28 so'z",
  "spoken3": "20-30s twist + CTA kameraga, ~18-28 so'z",
  "caption": "o'zbekcha 2-4 qisqa gap + CTA + hashtaglar, lotin"
}}
"""
    raw = await chat_text(system, user)
    data = _parse_llm_json(raw)
    for key in ("idea", "hook", "caption"):
        if not data.get(key):
            raise GrokError(f"Ssenariyda {key} yo'q")
    hook = data["hook"].strip().strip('"')
    era = (data.get("era") or "a vivid historical or future place").strip()
    setting = (data.get("setting") or "cinematic natural light, photorealistic").strip()
    spoken_lines = []
    for i in range(1, VIDEO_BEATS + 1):
        line = (data.get(f"spoken{i}") or "").strip().strip('"')
        if not line:
            if i == 1:
                line = hook
            elif i == VIDEO_BEATS:
                line = str(p.get("cta") or hook)
            else:
                line = hook
        spoken_lines.append(line)
        data[f"spoken{i}"] = line
        data[f"beat{i}"] = _beat_visual(i, line, era, setting)
    data["hook"] = hook
    data["spoken"] = " ".join(spoken_lines)
    data["video_prompt"] = json.dumps(
        {f"beat{i}": data[f"beat{i}"] for i in range(1, VIDEO_BEATS + 1)},
        ensure_ascii=False,
    )
    return data


async def generate_image(prompt: str, dest: Path, aspect_ratio: str = "9:16") -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": IMAGE_MODEL,
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "resolution": "1k",
    }
    async with httpx.AsyncClient(timeout=180) as client:
        r = await client.post(f"{XAI_BASE}/images/generations", headers=_headers(), json=payload)
        if r.status_code >= 400:
            raise GrokError(f"Grok image ошибка {r.status_code}: {r.text[:500]}")
        data = r.json()
        url = data["data"][0]["url"]
        img = await client.get(url, timeout=120)
        img.raise_for_status()
        dest.write_bytes(img.content)
    logger.info("image saved %s (%s bytes)", dest, dest.stat().st_size)
    return dest


async def ensure_character() -> Path:
    if CHARACTER_FILE.exists() and CHARACTER_FILE.stat().st_size > 1000:
        return CHARACTER_FILE
    p = load_persona()
    return await generate_image(p["character_prompt"], CHARACTER_FILE)


async def _download_video(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=180) as client:
        vid = await client.get(url, timeout=180)
        vid.raise_for_status()
        dest.write_bytes(vid.content)
    logger.info("video saved %s (%s bytes)", dest, dest.stat().st_size)
    return dest


async def generate_video(
    prompt: str,
    dest: Path,
    *,
    reference_image: Path | None = None,
    duration: int | None = None,
    resolution: str | None = None,
    voice_id: str | None = None,
) -> Path:
    path, _url = await generate_video_ex(
        prompt,
        dest,
        reference_image=reference_image,
        duration=duration,
        resolution=resolution,
        voice_id=voice_id,
    )
    return path


async def generate_video_ex(
    prompt: str,
    dest: Path,
    *,
    reference_image: Path | None = None,
    first_frame: Path | None = None,
    duration: int | None = None,
    resolution: str | None = None,
    voice_id: str | None = None,
) -> tuple[Path, str]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    duration = VIDEO_DURATION if duration is None else duration
    resolution = resolution or VIDEO_RESOLUTION
    voice_id = (voice_id if voice_id is not None else VOICE_ID) or ""

    body: dict = {
        "model": VIDEO_MODEL,
        "prompt": prompt,
        "duration": duration,
        "aspect_ratio": VIDEO_ASPECT,
        "resolution": resolution,
    }
    if first_frame and first_frame.exists():
        body["image"] = {"url": _file_data_uri(first_frame, "image/jpeg")}
    if reference_image and reference_image.exists():
        body["reference_images"] = [{"url": _file_data_uri(reference_image)}]
    if voice_id:
        body["reference_audios"] = [{"voice_id": voice_id}]

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{XAI_BASE}/videos/generations", headers=_headers(), json=body)
        if r.status_code >= 400 and first_frame and reference_image:
            logger.warning("video image+ref failed %s, retry image only", r.text[:240])
            body.pop("reference_images", None)
            r = await client.post(f"{XAI_BASE}/videos/generations", headers=_headers(), json=body)
        if r.status_code >= 400 and voice_id:
            logger.warning("video with voice failed %s, retry without voice", r.text[:240])
            body.pop("reference_audios", None)
            if reference_image and reference_image.exists() and "reference_images" not in body:
                body["reference_images"] = [{"url": _file_data_uri(reference_image)}]
            r = await client.post(f"{XAI_BASE}/videos/generations", headers=_headers(), json=body)
        if r.status_code >= 400:
            raise GrokError(f"Grok video ошибка {r.status_code}: {r.text[:700]}")
        request_id = r.json().get("request_id")
        if not request_id:
            raise GrokError(f"Нет request_id: {r.text[:400]}")

    url = await _poll_video(request_id)
    await _download_video(url, dest)
    return dest, url


async def extend_video(
    prompt: str,
    dest: Path,
    *,
    source_url: str | None = None,
    source_path: Path | None = None,
    duration: int = 10,
) -> tuple[Path, str]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if source_url:
        video = {"url": source_url}
    elif source_path and source_path.exists():
        video = {"url": _file_data_uri(source_path)}
    else:
        raise GrokError("extend: manba video yo'q")

    body: dict = {
        "model": VIDEO_EXTEND_MODEL,
        "prompt": prompt,
        "duration": duration,
        "video": video,
    }
    async with httpx.AsyncClient(timeout=180) as client:
        r = await client.post(f"{XAI_BASE}/videos/extensions", headers=_headers(), json=body)
        if r.status_code >= 400 and source_path and source_path.exists() and source_url:
            logger.warning("extend url failed %s, retry data-uri", r.text[:300])
            body["video"] = {"url": _file_data_uri(source_path)}
            r = await client.post(
                f"{XAI_BASE}/videos/extensions", headers=_headers(), json=body
            )
        if r.status_code >= 400:
            raise GrokError(f"Grok extend ошибка {r.status_code}: {r.text[:700]}")
        request_id = r.json().get("request_id")
        if not request_id:
            raise GrokError(f"extend: нет request_id: {r.text[:400]}")

    url = await _poll_video(request_id)
    await _download_video(url, dest)
    return dest, url


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


async def generate_reel_video(
    beats: dict[str, str],
    dest: Path,
    *,
    reference_image: Path | None = None,
    voice_id: str | None = None,
) -> Path:
    """30s = 3×10s. Each shot after the first starts on the previous last frame
    and keeps the same character portrait so the head does not recast."""
    from media import concat_copy, duration_seconds, extract_last_frame, normalize_clip

    dest.parent.mkdir(parents=True, exist_ok=True)
    keys = [k for k in (f"beat{i}" for i in range(1, VIDEO_BEATS + 1)) if beats.get(k)]
    if len(keys) < 3:
        raise GrokError("ssenariyda beat yetarli emas")

    segments: list[Path] = []
    last_frame: Path | None = None
    for i, key in enumerate(keys):
        raw = dest.with_name(f"{dest.stem}_{key}.mp4")
        seg = dest.with_name(f"{dest.stem}_{key}_seg.mp4")
        logger.info("shot %s/%s %s", i + 1, len(keys), key)
        await generate_video_ex(
            beats[key],
            raw,
            reference_image=reference_image,
            first_frame=last_frame,
            duration=10,
            voice_id=voice_id,
        )
        await asyncio.to_thread(normalize_clip, raw, seg, 10)
        logger.info("%s normalized %.1fs", key, duration_seconds(seg))
        segments.append(seg)
        frame = dest.with_name(f"{dest.stem}_{key}_last.jpg")
        await asyncio.to_thread(extract_last_frame, seg, frame)
        last_frame = frame

    await asyncio.to_thread(concat_copy, segments, dest)
    logger.info(
        "%ss reel assembled %s (%.1fs)",
        VIDEO_TOTAL_DURATION,
        dest,
        duration_seconds(dest),
    )
    return dest


async def _poll_video(request_id: str, timeout_s: int = 600) -> str:
    deadline = asyncio.get_event_loop().time() + timeout_s
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            if asyncio.get_event_loop().time() > deadline:
                raise GrokError("Grok видео не успело за 10 минут")
            r = await client.get(f"{XAI_BASE}/videos/{request_id}", headers=_headers())
            if r.status_code >= 400:
                raise GrokError(f"Опрос видео {r.status_code}: {r.text[:400]}")
            data = r.json()
            status = data.get("status")
            if status == "done":
                url = (data.get("video") or {}).get("url")
                if not url:
                    raise GrokError(f"Готово, но нет url: {data}")
                return url
            if status in {"failed", "expired"}:
                raise GrokError(f"Генерация {status}: {data}")
            await asyncio.sleep(5)


def next_video_path(post_id: int) -> Path:
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    return VIDEO_DIR / f"post_{post_id}.mp4"
