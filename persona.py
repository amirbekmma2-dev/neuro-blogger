import json
from pathlib import Path

from config import PERSONA_FILE

DEFAULT = {
    "name": "Motiv",
    "ig_handle": "motivstile.ai",
    "niche": (
        "vaqt sayohati: o'tmish (Yunoniston, Misr, SSSR, Toshkent 2000) "
        "va kelajak (Toshkent 2100, Mars) — agent o'zi davrni tanlaydi"
    ),
    "language": "uz",
    "tone": "ko'cha uslubi, hayrat, hazil, 1-soniyada ushlaydi, suvsiz",
    "audience": "O'zbekiston, 16-35 yosh, Reels, tarix va kelajakka qiziqadiganlar",
    "character_prompt": (
        "Photorealistic vertical 9:16 cinematic portrait of a young Uzbek man, "
        "about 25, short dark hair, sharp eyes, clean-shaven, wearing a dark wool coat and black beanie, "
        "standing as a time traveler, confident look into camera, natural light, "
        "this exact face and head are locked for every scene, "
        "no text, no watermark, no logo"
    ),
    "hashtags": [
        "#sayohat",
        "#tarix",
        "#kelajak",
        "#toshkent",
        "#ozbekiston",
        "#retro",
        "#sssr",
        "#motivstileai",
        "#reelsuz",
        "#vaqtsayohati",
    ],
    "cta": "Saqla. Keyin qayerga uchay? Kommentga yoz.",
    "voice_id": "rex",
    "viral_topics": [
        "Qadimgi Yunoniston: Afina bozori va olimpiada",
        "Qadimgi Misr: ehram oldida qum va fir'avn",
        "SSSR Toshkent 1980: tramvay, palto, qor",
        "Toshkent 2000: Abdulla Qahhor ko'chasi, qish",
        "Samarqand Ipak yo'li: Registon, karvon",
        "Buxoro o'rta asr: madrasa va choyxona",
        "Rim kolizey: gladiator changi",
        "Toshkent 2100: neon, uchuvchi taksi",
        "Mars koloniyasi: qizil qum, o'zbek bayrog'i",
        "Kelajak bozori: robot somsa pishiradi",
        "Chingizxon stepi: ot va bayroq",
        "Atlantida: suv osti shahar",
    ],
}


def load_persona() -> dict:
    if PERSONA_FILE.exists():
        data = json.loads(PERSONA_FILE.read_text(encoding="utf-8"))
        merged = dict(DEFAULT)
        merged.update(data)
        return merged
    PERSONA_FILE.parent.mkdir(parents=True, exist_ok=True)
    PERSONA_FILE.write_text(
        json.dumps(DEFAULT, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return dict(DEFAULT)


def save_persona(data: dict) -> None:
    PERSONA_FILE.parent.mkdir(parents=True, exist_ok=True)
    PERSONA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def format_persona(p: dict) -> str:
    tags = " ".join(p.get("hashtags") or [])
    return (
        f"Имя: {p.get('name')}\n"
        f"Аккаунт: @{p.get('ig_handle')}\n"
        f"Ниша: {p.get('niche')}\n"
        f"Тил: {p.get('language')}\n"
        f"Тон: {p.get('tone')}\n"
        f"Аудитория: {p.get('audience')}\n"
        f"CTA: {p.get('cta')}\n"
        f"Хэштеги: {tags}\n"
        f"Лицо: {p.get('character_prompt')}"
    )
