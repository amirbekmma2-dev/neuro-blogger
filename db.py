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
"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def init_db() -> None:
    ensure_dirs()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(SCHEMA)
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
        today = datetime.now().strftime("%Y-%m-%d")
        cur = await db.execute(
            "SELECT COUNT(*) FROM posts WHERE status='posted' AND created_at LIKE ?",
            (f"{today}%",),
        )
        posted_today = (await cur.fetchone())[0]
        data["posted_today"] = posted_today
        return data
