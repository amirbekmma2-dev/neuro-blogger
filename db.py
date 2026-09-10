import aiosqlite
from datetime import datetime, timezone

from config import DB_PATH, ensure_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    topic TEXT,
    idea TEXT,
    hook TEXT,
    video_prompt TEXT,
    caption TEXT,
    video_path TEXT,
    ig_media_id TEXT,
    error TEXT
);
CREATE TABLE IF NOT EXISTS kv (
    k TEXT PRIMARY KEY,
    v TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def init_db() -> None:
    ensure_dirs()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()


async def create_post(topic: str | None, status: str = "generating") -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO posts (created_at, status, topic) VALUES (?, ?, ?)",
            (_now(), status, topic),
        )
        await db.commit()
        return int(cur.lastrowid)


async def update_post(post_id: int, **fields) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [post_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE posts SET {cols} WHERE id=?", vals)
        await db.commit()


async def get_post(post_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM posts WHERE id=?", (post_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def list_posts(limit: int = 10) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM posts ORDER BY id DESC LIMIT ?", (limit,)
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def counts() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT status, COUNT(*) FROM posts GROUP BY status"
        )
        rows = await cur.fetchall()
        data = {k: v for k, v in rows}
        cur = await db.execute(
            "SELECT created_at FROM posts WHERE status='posted'"
        )
        rows = await cur.fetchall()
        from schedule import TASHKENT, now_tashkent

        today = now_tashkent().date()
        posted_today = 0
        for (stamp,) in rows:
            dt = _parse_utc(stamp)
            if dt and dt.astimezone(TASHKENT).date() == today:
                posted_today += 1
        data["posted_today"] = posted_today
        latest = None
        for (stamp,) in rows:
            dt = _parse_utc(stamp)
            if dt and (latest is None or dt > latest):
                latest = dt
        data["last_posted_at"] = latest.isoformat() if latest else None
        return data


def _parse_utc(stamp: str | None) -> datetime | None:
    if not stamp:
        return None
    raw = stamp.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


async def kv_get(key: str) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT v FROM kv WHERE k=?", (key,))
        row = await cur.fetchone()
        return str(row[0]) if row else None


async def kv_set(key: str, value: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO kv(k, v, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(k) DO UPDATE SET v=excluded.v, updated_at=excluded.updated_at",
            (key, value, _now()),
        )
        await db.commit()
