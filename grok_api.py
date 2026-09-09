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


def _file_data_uri(path: Path) -> str:
    raw = path.read_bytes()
    mime = "image/jpeg"
    suf = path.suffix.lower()
    if suf == ".png":
        mime = "image/png"
    elif suf == ".webp":
        mime = "image/webp"
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


async def invent_script(topic: str | None = None, avoid: list[str] | None = None) -> dict:
    p = load_persona()
    tags = " ".join(p.get("hashtags") or [])
    bank = p.get("viral_topics") or []
    bank_txt = "\n".join(f"- {t}" for t in bank)
    skip = "\n".join(f"- {x}" for x in (avoid or [])[:12])
    chosen = topic or "o'zing yangi viral sport-ovqat g'oyasini tanla (bankdan yoki yangi), takrorlama"
    system = (
        "Sen O'zbekiston Instagram Reels uchun viral ssenarist san. "
        "Faqat JSON qaytar, markdown yo'q. "
        "Og'zaki nutq va caption — FAQAT o'zbek tili, lotin alifbosi (o' / g'). "
        "Ruscha va inglizcha gap YO'Q (inglizcha faqat video_prompt). "
        "Video 15 soniya: odam to'liq 2-3 qisqa gap aytadi, 30-40 so'z atrofida."
    )
    user = f"""Akaunt: @{p.get('ig_handle')}  personaj: {p.get('name')}
Nisha: {p.get('niche')}
Tomoshabin: {p.get('audience')}
Ohang: {p.get('tone')}
CTA: {p.get('cta')}
Hashtaglar: {tags}
Mavzu banki:
{bank_txt}
Oxirgi chiqqanlar (takrorlama):
{skip or "- yo'q"}
Berilgan mavzu: {chosen}

15 soniyalik Reels formulasi (Explore/top uchun):
1) 0-2s hook: ayblash, raqam, taqiqlangan ovqat, «to'xta»
2) 2-11s bitta aniq foyda: nima qilish/nemani tashlash, Toshkent hayoti (palov, somsa, choyxona, arzon tovuq, tuxum, zal)
3) 11-15s CTA: saqla + kommentga savol
Suv yo'q. Bitta fikr. Bahslashish.

JSON:
{{
  "idea": "o'zbekcha 1 qator",
  "hook": "birinchi og'zaki gap, 6-10 so'z, shok",
  "spoken": "to'liq o'zbekcha monolog 15 soniyaga, 2-3 gap, hook bilan boshlanadi, oxirida CTA",
  "video_prompt": "English visual, present tense, vertical 9:16, photorealistic, ONE continuous 15-second shot. First frame stops the scroll (food slam, extreme close-up). The person from <IMAGE_1> is the only human. They speak fluent conversational Uzbek (not Russian, not English) saying exactly: <spoken>. Voice from <AUDIO_0>. Simple camera move, kitchen or gym or Tashkent food table. No on-screen text, no subtitles, no logos, no watermark.",
  "caption": "o'zbekcha 2-4 qisqa gap + CTA + hashtaglar, lotin"
}}
"""
    raw = await chat_text(system, user)
    match = _JSON_RE.search(raw)
    if not match:
        raise GrokError(f"LLM JSON qaytarmadi: {raw[:400]}")
    data = json.loads(match.group(0))
    for key in ("idea", "hook", "video_prompt", "caption"):
        if not data.get(key):
            raise GrokError(f"Ssenariyda {key} yo'q")
    hook = data["hook"].strip().strip('"')
    spoken = (data.get("spoken") or hook).strip().strip('"')
    data["hook"] = hook
    data["spoken"] = spoken
    if spoken not in data["video_prompt"]:
        data["video_prompt"] = (
            data["video_prompt"].rstrip(".")
            + f' They speak fluent Uzbek, exact lines: "{spoken}".'
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


async def generate_video(
    prompt: str,
    dest: Path,
    *,
    reference_image: Path | None = None,
    duration: int | None = None,
    resolution: str | None = None,
    voice_id: str | None = None,
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    duration = 15
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

    async with httpx.AsyncClient(timeout=30) as client:
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
    async with httpx.AsyncClient(timeout=180) as client:
        vid = await client.get(url, timeout=180)
        vid.raise_for_status()
        dest.write_bytes(vid.content)
    logger.info("video saved %s (%s bytes)", dest, dest.stat().st_size)
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
