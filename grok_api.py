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
    VIDEO_DURATION,
    VIDEO_EXTEND_MODEL,
    VIDEO_MODEL,
    VIDEO_RESOLUTION,
    VIDEO_DIR,
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


def parse_beats(video_prompt: str) -> dict[str, str]:
    raw = (video_prompt or "").strip()
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
            if data.get("beat1") and data.get("beat2") and data.get("beat3"):
                return {
                    "beat1": str(data["beat1"]),
                    "beat2": str(data["beat2"]),
                    "beat3": str(data["beat3"]),
                }
        except json.JSONDecodeError:
            pass
    return {
        "beat1": raw,
        "beat2": "Continue seamlessly from the last frame. Same person, same era. " + raw,
        "beat3": "Continue seamlessly from the last frame. Same person looks into camera. " + raw,
    }


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
        "Ruscha va inglizcha gap YO'Q (inglizcha faqat beat1/beat2/beat3). "
        "Video 30 soniya: 3 ta 10 soniyalik beat. "
        "Davrni O'ZING tanla — ba'zan o'tmish, ba'zan kelajak. Qiziq bo'lsin."
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

30 soniyalik Reels (Explore):
1) 0-10s hook + yetib kelish: birinchi kadr scrollni to'xtatadi
2) 10-20s dunyo ichida yurish, bitta aniq detal
3) 20-30s twist + CTA
Suv yo'q. Bir davr. Qiziq.

JSON:
{{
  "idea": "o'zbekcha 1 qator, qayerga uchgani",
  "hook": "birinchi og'zaki gap, 6-10 so'z, shok",
  "spoken1": "0-10s o'zbekcha, ~20-30 so'z",
  "spoken2": "10-20s o'zbekcha, ~20-30 so'z",
  "spoken3": "20-30s o'zbekcha + CTA, ~20-30 so'z",
  "beat1": "English visual, present tense, vertical 9:16, photorealistic, ONE 10-second shot. First frame stops the scroll. The person from <IMAGE_1> is the only human, time traveler arriving in this era. They speak fluent conversational Uzbek saying exactly: <spoken1>. Voice from <AUDIO_0>. No on-screen text, no subtitles, no logos, no watermark.",
  "beat2": "English visual, continue from last frame, 10 seconds. Same person from <IMAGE_1> walks deeper into the era. They speak fluent Uzbek saying exactly: <spoken2>. Voice from <AUDIO_0>. No text, no logos.",
  "beat3": "English visual, continue from last frame, 10 seconds. Same person from <IMAGE_1> ends looking into camera. They speak fluent Uzbek saying exactly: <spoken3>. Voice from <AUDIO_0>. No text, no logos.",
  "caption": "o'zbekcha 2-4 qisqa gap + CTA + hashtaglar, lotin"
}}
"""
    raw = await chat_text(system, user)
    match = _JSON_RE.search(raw)
    if not match:
        raise GrokError(f"LLM JSON qaytarmadi: {raw[:400]}")
    data = json.loads(match.group(0))
    for key in ("idea", "hook", "caption", "beat1", "beat2", "beat3"):
        if not data.get(key):
            raise GrokError(f"Ssenariyda {key} yo'q")
    hook = data["hook"].strip().strip('"')
    s1 = (data.get("spoken1") or hook).strip().strip('"')
    s2 = (data.get("spoken2") or "").strip().strip('"')
    s3 = (data.get("spoken3") or (p.get("cta") or "")).strip().strip('"')
    spoken = " ".join(x for x in (s1, s2, s3) if x)
    data["hook"] = hook
    data["spoken"] = spoken
    for beat_key, line in (("beat1", s1), ("beat2", s2), ("beat3", s3)):
        text = data[beat_key].strip()
        if line and line not in text:
            text = text.rstrip(".") + f' They speak fluent Uzbek, exact lines: "{line}".'
        data[beat_key] = text
    data["video_prompt"] = json.dumps(
        {"beat1": data["beat1"], "beat2": data["beat2"], "beat3": data["beat3"]},
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
    if reference_image and reference_image.exists():
        body["reference_images"] = [{"url": _file_data_uri(reference_image)}]
    if voice_id:
        body["reference_audios"] = [{"voice_id": voice_id}]

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{XAI_BASE}/videos/generations", headers=_headers(), json=body)
        if r.status_code >= 400 and voice_id:
            logger.warning("video with voice failed %s, retry without voice", r.text[:300])
            body.pop("reference_audios", None)
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
    from media import concat_videos, duration_seconds, extract_last_seconds

    dest.parent.mkdir(parents=True, exist_ok=True)
    b1 = dest.with_name(dest.stem + "_b1.mp4")
    b20 = dest.with_name(dest.stem + "_b20.mp4")
    tail = dest.with_name(dest.stem + "_tail.mp4")
    b3full = dest.with_name(dest.stem + "_b3full.mp4")
    new10 = dest.with_name(dest.stem + "_new10.mp4")

    path1, url1 = await generate_video_ex(
        beats["beat1"],
        b1,
        reference_image=reference_image,
        duration=10,
        voice_id=voice_id,
    )
    logger.info("beat1 %.1fs", duration_seconds(path1))

    try:
        path20, _url20 = await extend_video(
            beats["beat2"], b20, source_url=url1, source_path=path1, duration=10
        )
    except GrokError:
        logger.exception("extend #1 via url failed, data-uri")
        path20, _url20 = await extend_video(
            beats["beat2"], b20, source_path=path1, duration=10
        )

    if duration_seconds(path20) < 15:
        twenty = dest.with_name(dest.stem + "_twenty.mp4")
        await asyncio.to_thread(concat_videos, [path1, path20], twenty)
        path20 = twenty

    await asyncio.to_thread(extract_last_seconds, path20, tail, 10)
    path3, _url3 = await extend_video(
        beats["beat3"], b3full, source_path=tail, duration=10
    )
    if duration_seconds(path3) < 15:
        await asyncio.to_thread(extract_last_seconds, path3, new10, min(10, int(duration_seconds(path3) or 10)))
        await asyncio.to_thread(concat_videos, [path20, path3], dest)
    else:
        await asyncio.to_thread(extract_last_seconds, path3, new10, 10)
        await asyncio.to_thread(concat_videos, [path20, new10], dest)
    logger.info("30s reel assembled %s (%.1fs)", dest, duration_seconds(dest))
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
