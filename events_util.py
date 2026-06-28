"""イベントの日付判定（API 返却・保存用）"""

from __future__ import annotations

from datetime import date
from typing import Optional

# 開始からこの日数を超えて仍在開中のイベントは一覧から除外（長期展示など）
MAX_ONGOING_DAYS = 30


def _parse_date(value: str | None) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def event_start_date(event: dict) -> Optional[date]:
    return _parse_date(event.get("date"))


def event_end_date(event: dict) -> Optional[date]:
    return _parse_date(event.get("end_date") or event.get("date"))


def is_active_event(event: dict, today: Optional[date] = None) -> bool:
    """終了日が今日以降（まだ終わっていない）"""
    today = today or date.today()
    end = event_end_date(event)
    if end is None:
        return False
    return end >= today


def is_listable_event(event: dict, today: Optional[date] = None) -> bool:
    """API 一覧に載せるイベントか（未終了・古い長期開催を除外）"""
    today = today or date.today()
    if not is_active_event(event, today):
        return False

    start = event_start_date(event)
    if start is None:
        return False

    if start >= today:
        return True

    days_since_start = (today - start).days
    return days_since_start <= MAX_ONGOING_DAYS


def filter_listable_events(
    events: list[dict], today: Optional[date] = None,
) -> list[dict]:
    return [e for e in events if is_listable_event(e, today)]


def filter_active_events(
    events: list[dict], today: Optional[date] = None,
) -> list[dict]:
    return [e for e in events if is_active_event(e, today)]
