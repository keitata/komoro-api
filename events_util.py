"""イベントの日付判定（終了済み除外）"""

from __future__ import annotations

from datetime import date
from typing import Optional


def event_end_date(event: dict) -> Optional[date]:
    """終了日を返す。end_date がなければ date（単日）を使う。"""
    raw = event.get("end_date") or event.get("date")
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def is_active_event(event: dict, today: Optional[date] = None) -> bool:
    """今日以降まだ終わっていないイベントか（終了日 >= 今日）"""
    end = event_end_date(event)
    if end is None:
        return False
    return end >= (today or date.today())


def filter_active_events(events: list[dict], today: Optional[date] = None) -> list[dict]:
    """終了済み・日付不明を除いたリストを返す"""
    return [e for e in events if is_active_event(e, today)]
