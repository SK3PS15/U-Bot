import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import settings


TZ = ZoneInfo(settings.timezone)


def compute_next(rem_row) -> datetime | None:
    repeat_type = rem_row["repeat_type"] or "none"
    if repeat_type == "none":
        return None

    current = datetime.strptime(rem_row["fire_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
    data = {}
    if rem_row["repeat_json"]:
        try:
            data = json.loads(rem_row["repeat_json"])
        except Exception:
            data = {}

    if repeat_type == "daily":
        return current + timedelta(days=1)
    if repeat_type == "weekly":
        return current + timedelta(days=7)
    if repeat_type == "monthly":
        year, month = current.year, current.month + 1
        if month > 12:
            month = 1
            year += 1
        day = min(current.day, 28)
        return current.replace(year=year, month=month, day=day)
    if repeat_type == "interval":
        seconds = int(data.get("seconds", 3600))
        return current + timedelta(seconds=seconds)
    if repeat_type == "weekdays":
        days = data.get("days", [])
        for delta in range(1, 15):
            nxt = current + timedelta(days=delta)
            if nxt.isoweekday() in days:
                return nxt
    return None
