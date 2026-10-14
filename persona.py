import json
from pathlib import Path

from config import PERSONA_FILE

DEFAULT = {
    "name": "Zamon",
    "ig_handle": "zamonlar.ai",
    "niche": (
        "tarixiy voqealar: Qadimgi Turkiston, Amir Temur, 1865-yil Toshkent, "
        "1937-yil Qora yillar, Qo'qon xonligi, antik dunyo va sirli tarix — agent o'zi davrni tanlaydi"
    ),
    "language": "uz",
    "tone": "kinematografik, dramatik, hayrat, hazil emas, 1-soniyada ushlaydi, suvsiz",
    "audience": "O'zbekiston, 16-45 yosh, Reels, tarix va sirli voqealarga qiziquvchilar",
    "character_prompt": (
        "Photorealistic vertical 9:16 cinematic portrait of a young Uzbek historian and time traveler, "
        "about 25, short dark hair, sharp eyes, clean-shaven, wearing a dark wool coat, "
        "standing in ancient historical setting, confident look into camera, natural light, "
        "this exact face and head are locked for every scene, "
        "no text, no watermark, no logo"
    ),
    "hashtags": [
        "#tarix",
        "#zamonlar",
        "#toshkent",
        "#ozbekiston",
        "#amirtemur",
        "#qorayillar",
        "#turkiston",
        "#reelsuz",
        "#sarguzasht",
        "#zamonlarai",
    ],
    "cta": "Saqla va obuna bo'l. Keyingi tarix qaysi? Kommentga yoz.",
    "voice_id": "rex",
    "viral_topics": [
        "1865-yil: Rossiya imperiyasi qo'shinlari Toshkent ostonasida",
        "1937-yil: Bir tamg'a, minglab taqdirlar va Qora yillar",
        "Amir Temurning qabri ochildi: ikki kundan keyin urush boshlandi",
        "1398-yil: Dehli yaqinida Amir Temur qarshisida jang",
        "1876-yil: Qo'qon xonligi tarix sahnasidan tushdi",
        "Vodiy qo'zg'oloni va erk uchun kurash",
        "Ibrohimbek: Turkiston kurashining oxirgi yirik qahramoni",
        "Registon maydoni XVII asrda: karvonlar va madrasalar",
        "Buxoro amirligi oxirgi kunlari va o'zgarishlar",
        "Xorazm qadimiy qal'alari va cho'l sirlari",
        "Qadimgi Samarqand: Ipak yo'lining yuragi",
        "Toshkentning eski darvozalari va qadimiy turmush",
        "1916-yil qo'zg'oloni: Turkistonda og'iz yopilmagan yillar",
        "Alisher Navoiy va Husayn Bayqaro davrida Hirot",
        "Ulughbek rasadxonasi va o'rta asr osmon sirlari",
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
