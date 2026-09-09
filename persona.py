import json
from pathlib import Path

from config import PERSONA_FILE

DEFAULT = {
    "name": "Motiv",
    "ig_handle": "motivstile.ai",
    "niche": "sport ovqatlanish: protein, kreatin, osh vs chicken, zal oldidan ovqat",
    "language": "uz",
    "tone": "ko'cha uslubi, o'tkir, hazil bilan, suvsiz, 1-soniyada ushlaydi",
    "audience": "O'zbekiston, 16-30 yosh, zalga chiqadigan yigitlar",
    "character_prompt": (
        "Photorealistic vertical 9:16 cinematic portrait of a young Uzbek man, "
        "about 23, short dark hair, athletic, holding a protein shaker in a bright "
        "Tashkent apartment kitchen with chicken and rice on the counter, natural "
        "window light, street-smart confident look into camera, no text, no watermark, no logo"
    ),
    "hashtags": [
        "#sportovqat",
        "#protein",
        "#fitnes",
        "#ozbekiston",
        "#toshkent",
        "#zal",
        "#kreatin",
        "#sportpitanie",
        "#gym",
        "#motivstileai",
    ],
    "cta": "Saqla. To'g'rimi? Kommentga yoz.",
    "voice_id": "rex",
    "viral_topics": [
        "Palov yeb zalga chiqasan — shuning uchun qorin ketmaydi",
        "Protein shakerni suv o'rniga sut bilan ichish — pulni yoqish",
        "6 ta tuxum ertalab: afsona vs haqiqat",
        "Kreatin buyrakni buzadi degan yolg'on",
        "Arzon tovuq + guruch = eng qimmat sportpit emas",
        "Zaldan keyin 2 soat och yurish — muskullarni yeysan",
        "Somsa + choyxona vs meal prep",
        "1 banka energetik = 1 soat zalni yo'q qilish",
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
