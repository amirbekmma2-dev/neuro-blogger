"""Instagram Reels peak windows for Tashkent (UTC+5).

Baseline = public Reels research for 16–35 (morning scroll, lunch,
after school/work, prime 19–22). After the account is professional
we overlay hours from Instagram insights (views), so slots follow
what actually flies on THIS account.
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

TASHKENT = timezone(timedelta(hours=5))

# Weekday: commute / lunch / after school / prime time
WEEKDAY_SLOTS = [
    (7, 40),
    (9, 10),
    (12, 20),
    (14, 40),
    (17, 20),
    (19, 0),
    (20, 30),
    (22, 0),
]
# Weekend: later morning, same evening peak
WEEKEND_SLOTS = [
    (9, 30),
    (11, 0),
    (13, 0),
    (15, 30),
    (17, 30),
    (19, 0),
    (20, 30),
    (22, 0),
]


def now_tashkent() -> datetime:
    return datetime.now(TASHKENT)


def _slots_for(dt: datetime, learned: list[tuple[int, int]] | None) -> list[tuple[int, int]]:
    if learned and len(learned) >= 4:
        return learned[:8]
    if dt.weekday() >= 5:
        return list(WEEKEND_SLOTS)
    return list(WEEKDAY_SLOTS)


def format_slots(slots: list[tuple[int, int]]) -> str:
    return " ".join(f"{h:02d}:{m:02d}" for h, m in slots)


def parse_slots(raw: str | None) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    if not raw:
        return out
    for part in raw.split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        hs, ms = part.split(":", 1)
        try:
            h, m = int(hs), int(ms)
        except ValueError:
            continue
        if 0 <= h <= 23 and 0 <= m <= 59:
            out.append((h, m))
    return out


def slots_to_str(slots: list[tuple[int, int]]) -> str:
    return ",".join(f"{h:02d}:{m:02d}" for h, m in slots)


def _aware(now: datetime | None) -> datetime:
    now = now or now_tashkent()
    if now.tzinfo is None:
        now = now.replace(tzinfo=TASHKENT)
    return now.astimezone(TASHKENT)


def slot_at(day: datetime, hour: int, minute: int) -> datetime:
    day = _aware(day)
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0)


def prep_slot(
    *,
    learned: list[tuple[int, int]] | None = None,
    now: datetime | None = None,
    lead_min: int = 30,
) -> datetime | None:
    """Slot currently in the prep window: [slot-lead, slot).

    Example: post 22:00 → prep from 21:30 so the Reel is ready on time.
    """
    now = _aware(now)
    lead = timedelta(minutes=max(1, lead_min))
    for day_offset in range(0, 2):
        day = now + timedelta(days=day_offset)
        for h, m in _slots_for(day, learned):
            cand = slot_at(day, h, m)
            start = cand - lead
            if start <= now < cand:
                return cand
    return None


def late_slot(
    *,
    learned: list[tuple[int, int]] | None = None,
    now: datetime | None = None,
    grace_min: int = 45,
) -> datetime | None:
    """Slot that already started, still OK to finish a late reel."""
    now = _aware(now)
    for h, m in _slots_for(now, learned):
        cand = slot_at(now, h, m)
        delta = (now - cand).total_seconds()
        if 0 <= delta <= grace_min * 60:
            return cand
    return None


def due_slot(
    *,
    learned: list[tuple[int, int]] | None = None,
    now: datetime | None = None,
    grace_min: int = 18,
) -> datetime | None:
    """Slot that should be posted now.

    A weekday/weekend slot stays due from its time until the next slot
    (same calendar day). Render free restarts used to miss the 18-minute
    grace and then sleep until the following peak.
    """
    now = now or now_tashkent()
    if now.tzinfo is None:
        now = now.replace(tzinfo=TASHKENT)
    now = now.astimezone(TASHKENT)
    prev = None
    for h, m in _slots_for(now, learned):
        cand = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if cand <= now:
            prev = cand
    if prev is None or prev.date() != now.date():
        for h, m in _slots_for(now, learned):
            cand = now.replace(hour=h, minute=m, second=0, microsecond=0)
            delta = (now - cand).total_seconds()
            if 0 <= delta <= grace_min * 60:
                return cand
        return None
    nxt = next_slot(learned=learned, after=prev)
    if prev <= now < nxt:
        return prev
    return None


def next_slot(
    *,
    learned: list[tuple[int, int]] | None = None,
    after: datetime | None = None,
) -> datetime:
    after = after or now_tashkent()
    if after.tzinfo is None:
        after = after.replace(tzinfo=TASHKENT)
    after = after.astimezone(TASHKENT)
    for day_offset in range(0, 3):
        day = (after + timedelta(days=day_offset)).replace(second=0, microsecond=0)
        for h, m in _slots_for(day, learned):
            cand = day.replace(hour=h, minute=m)
            if cand > after + timedelta(seconds=20):
                return cand
    h, m = WEEKDAY_SLOTS[0]
    nxt = (after + timedelta(days=1)).replace(hour=h, minute=m, second=0, microsecond=0)
    return nxt


def hours_from_insights(items: list[dict]) -> list[tuple[int, int]] | None:
    """Weight creation hours by views; return up to 8 HH:MM slots."""
    weights: Counter[int] = Counter()
    used = 0
    for item in items:
        node = item.get("node") if isinstance(item, dict) else None
        if not isinstance(node, dict):
            node = item if isinstance(item, dict) else {}
        ts = (
            node.get("creation_time")
            or node.get("taken_at")
            or node.get("timestamp")
            or (node.get("media") or {}).get("taken_at")
        )
        metrics = node.get("inline_insights_node") or node.get("metrics") or {}
        if isinstance(metrics, dict) and "metrics" in metrics:
            metrics = metrics.get("metrics") or {}
        views = 0
        if isinstance(metrics, dict):
            views = int(
                metrics.get("video_views")
                or metrics.get("impressions")
                or metrics.get("reach")
                or metrics.get("views")
                or 0
            )
        if ts is None:
            continue
        try:
            ts_i = int(ts)
        except (TypeError, ValueError):
            continue
        if ts_i > 10_000_000_000:
            ts_i //= 1000
        hour = datetime.fromtimestamp(ts_i, tz=TASHKENT).hour
        weights[hour] += max(views, 1)
        used += 1
    if used < 4:
        logger.info("insights too few (%s), keep default slots", used)
        return None
    top = [h for h, _ in weights.most_common(8)]
    top.sort()
    # Snap to :00 inside the winning hours (Reels still in that window)
    slots = [(h, 0) for h in top]
    logger.info("learned peak hours Tashkent: %s (n=%s)", format_slots(slots), used)
    return slots
