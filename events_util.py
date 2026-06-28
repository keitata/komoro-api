"""イベントの日付判定（API 返却・保存用）"""

from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Optional

# 地図表示開始: 開始日の何日前から（community-reports-front と同じ）
DISPLAY_LEAD_DAYS = 30


def _parse_date(value: str | None) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _parse_time_range(time_str: str | None) -> tuple[str, str]:
    """community-reports-front komoroEvent.parseTimeRange と同じ"""
    if not time_str:
        return "09:00", "17:00"
    m = re.search(
        r"(\d{1,2})[:：](\d{2})\s*[〜～~\-–]\s*(\d{1,2})[:：](\d{2})",
        time_str,
    )
    if m:
        h1, mi1, h2, mi2 = m.groups()
        return f"{int(h1):02d}:{mi1}", f"{int(h2):02d}:{mi2}"
    m = re.search(r"(\d{1,2})[:：](\d{2})", time_str)
    if m:
        h, mi = m.groups()
        return f"{int(h):02d}:{mi}", "17:00"
    return "09:00", "17:00"


def _combine(date_str: date, hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime.combine(date_str, time(h, m))


def event_start_date(event: dict) -> Optional[date]:
    return _parse_date(event.get("date"))


def event_end_date(event: dict) -> Optional[date]:
    return _parse_date(event.get("end_date") or event.get("date"))


def event_datetime_bounds(event: dict) -> Optional[tuple[datetime, datetime]]:
    start_d = event_start_date(event)
    if start_d is None:
        return None
    end_d = event_end_date(event) or start_d
    start_t, end_t = _parse_time_range(event.get("time"))
    return _combine(start_d, start_t), _combine(end_d, end_t)


def _days_until_start(now: datetime, start_at: datetime) -> int:
    start = start_at.date()
    today = now.date()
    return (start - today).days


def is_active_event(event: dict, today: Optional[date] = None) -> bool:
    """終了日が今日以降（日付のみ・保存時の粗い除外）"""
    today = today or date.today()
    end = event_end_date(event)
    if end is None:
        return False
    return end >= today


def is_listable_event(
    event: dict, now: Optional[datetime] = None,
) -> bool:
    """API 一覧に載せるイベントか（表示期間内のみ）。

    community-reports-front の isOfficialVisibleOnMap と同じ基準:
    - 終了日時を過ぎていない
    - 開始日が DISPLAY_LEAD_DAYS 日以内（開始1か月前から表示）
    """
    now = now or datetime.now()
    bounds = event_datetime_bounds(event)
    if bounds is None:
        return False
    start_at, end_at = bounds
    if now > end_at:
        return False
    return _days_until_start(now, start_at) <= DISPLAY_LEAD_DAYS


def filter_listable_events(
    events: list[dict], now: Optional[datetime] = None,
) -> list[dict]:
    return [e for e in events if is_listable_event(e, now)]


def filter_active_events(
    events: list[dict], today: Optional[date] = None,
) -> list[dict]:
    return [e for e in events if is_active_event(e, today)]
