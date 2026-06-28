"""
軽井沢ナビ（Slow-Style.com）イベントスクレイパー
対象: https://www.slow-style.com/event/ （小諸エリアのみ）
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .scraper import detect_category, polite_get

logger = logging.getLogger(__name__)

BASE_URL = "https://www.slow-style.com"
EVENT_LIST_URL = f"{BASE_URL}/event/"
KOMORO_AREA_URL = f"{BASE_URL}/event/area/komoro/"

SLOW_STYLE_CATEGORY_MAP = {
    "お祭り": "祭り",
    "音楽": "コンサート",
    "コンサート": "コンサート",
    "スポーツ": "スポーツ",
    "展示": "展示",
    "お店の催し": "文化",
    "趣味の集い": "文化",
    "子供": "その他",
    "ペット": "その他",
    "ブライダル": "その他",
    "その他": "その他",
}


def make_slow_style_id(event_path: str) -> str:
    """URL パス /event/4001/ から安定 ID を生成"""
    m = re.search(r"/event/(\d+)/?", event_path)
    if m:
        return f"ss-{m.group(1)}"
    return f"ss-unknown-{abs(hash(event_path)) % 10**6}"


def map_category(raw_category: str, title: str, description: str) -> str:
    mapped = SLOW_STYLE_CATEGORY_MAP.get(raw_category.strip())
    if mapped:
        return mapped
    return detect_category(f"{title} {description}")


def parse_list_date(text: str) -> tuple[Optional[str], Optional[str]]:
    """一覧の日付ラベルから開始日・終了日 (ISO) を抽出"""
    text = text.strip()
    if not text:
        return None, None

    # 2026.06.26(金)～06.28(日)
    m = re.search(
        r"(\d{4})\.(\d{1,2})\.(\d{1,2}).*?[～~]\s*(\d{1,2})\.(\d{1,2})",
        text,
    )
    if m:
        y, mo, d, emo, ed = m.groups()
        start = f"{y}-{int(mo):02d}-{int(d):02d}"
        end = f"{y}-{int(emo):02d}-{int(ed):02d}"
        return start, end

    # 2026.06.28(日)
    m = re.search(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", text)
    if m:
        y, mo, d = m.groups()
        day = f"{y}-{int(mo):02d}-{int(d):02d}"
        return day, day

    return None, None


def _extract_event_urls(soup: BeautifulSoup) -> list[dict]:
    """一覧 HTML から小諸エリアのイベント概要を抽出"""
    items: list[dict] = []
    seen: set[str] = set()

    for li in soup.select("li.event-info__normal-item, li.event-info__recommend-item"):
        area_el = li.select_one(".event-area__label")
        area = area_el.get_text(strip=True) if area_el else ""
        if area != "小諸":
            continue

        link_el = li.select_one("a[href*='/event/']")
        if not link_el:
            continue
        href = link_el.get("href", "")
        if not re.search(r"/event/\d+/", href):
            continue
        if href in seen:
            continue
        seen.add(href)

        title_el = li.select_one("h3.section__sub-title, h3")
        title = title_el.get_text(strip=True) if title_el else ""
        date_el = li.select_one(".term-date__lable, .term-date__label")
        date_text = date_el.get_text(strip=True) if date_el else ""
        cat_el = li.select_one(".event-cate__label")
        category_raw = cat_el.get_text(strip=True) if cat_el else ""

        desc_el = li.select_one(".event-info__text, .event-info__description")
        excerpt = desc_el.get_text(" ", strip=True) if desc_el else ""

        start, end = parse_list_date(date_text)
        items.append({
            "path": href,
            "url": urljoin(BASE_URL, href),
            "title": title,
            "date": start,
            "end_date": end,
            "category_raw": category_raw,
            "excerpt": excerpt[:200] if excerpt else None,
        })

    return items


def fetch_komoro_list_pages() -> list[dict]:
    """小諸エリア一覧 + 全体一覧（小諸フィルタ）をページ送りで取得"""
    summaries: dict[str, dict] = {}
    list_urls = [KOMORO_AREA_URL]

    # 全体一覧も走査（小諸以外エリア混在のため _extract でフィルタ）
    for page in range(1, 6):
        suffix = f"?page={page}" if page > 1 else ""
        list_urls.append(f"{EVENT_LIST_URL}{suffix}")

    for url in list_urls:
        logger.info(f"[Slow-Style] 一覧取得: {url}")
        try:
            resp = polite_get(url, timeout=20)
        except Exception as e:
            logger.warning(f"一覧取得失敗 {url}: {e}")
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        for item in _extract_event_urls(soup):
            summaries[item["path"]] = item

        # 小諸エリア URL は1ページのみ想定
        if url.startswith(KOMORO_AREA_URL.rstrip("/")):
            continue
        # 全体一覧: 小諸が0件なら以降ページ不要
        if not soup.select("li.event-info__normal-item"):
            break

    logger.info(f"[Slow-Style] 小諸イベント {len(summaries)} 件検出")
    return list(summaries.values())


def _parse_json_ld_event(soup: BeautifulSoup) -> Optional[dict]:
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text()
        if not raw or "Event" not in raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if item.get("@type") == "Event":
                return item
    return None


def _location_from_json_ld(loc: dict) -> str:
    if not loc:
        return "小諸市内"
    name = (loc.get("name") or "").strip()
    addr = loc.get("address") or {}
    parts = [
        name,
        addr.get("streetAddress", ""),
        addr.get("addressLocality", ""),
    ]
    text = " ".join(p for p in parts if p).strip()
    return text or "小諸市内"


def fetch_event_detail(summary: dict) -> dict:
    """詳細ページ（JSON-LD）からイベント dict を組み立てる"""
    url = summary["url"]
    try:
        resp = polite_get(url, timeout=20)
    except Exception as e:
        logger.warning(f"詳細取得失敗 {url}: {e}")
        return _summary_to_event(summary)

    soup = BeautifulSoup(resp.text, "html.parser")
    ld = _parse_json_ld_event(soup)

    title = summary["title"]
    event_date = summary.get("date")
    end_date = summary.get("end_date")
    description = summary.get("excerpt")
    location = "小諸市内"
    lat = lng = None
    detail_url = url

    if ld:
        title = ld.get("name") or title
        event_date = ld.get("startDate") or event_date
        end_date = ld.get("endDate") or end_date
        description = (ld.get("description") or description or "")[:200] or None
        detail_url = ld.get("url") or url
        loc = ld.get("location") or {}
        location = _location_from_json_ld(loc)
        geo = loc.get("geo") or {}
        try:
            if geo.get("latitude") is not None:
                lat = float(geo["latitude"])
            if geo.get("longitude") is not None:
                lng = float(geo["longitude"])
        except (TypeError, ValueError):
            lat = lng = None

    category_raw = summary.get("category_raw", "")
    event = {
        "id": make_slow_style_id(summary["path"]),
        "title": title,
        "url": detail_url,
        "date": event_date,
        "end_date": end_date if end_date and end_date != event_date else None,
        "time": None,
        "location": location,
        "description": description,
        "category": map_category(category_raw, title, description or ""),
        "tags": [category_raw] if category_raw else [],
        "source": "軽井沢ナビ",
    }
    if lat is not None and lng is not None:
        event["lat"] = lat
        event["lng"] = lng
        event["location_label"] = location
        event["geocode_confidence"] = "source"

    return event


def _summary_to_event(summary: dict) -> dict:
    category_raw = summary.get("category_raw", "")
    title = summary.get("title", "")
    description = summary.get("excerpt")
    return {
        "id": make_slow_style_id(summary["path"]),
        "title": title,
        "url": summary["url"],
        "date": summary.get("date"),
        "end_date": summary.get("end_date"),
        "time": None,
        "location": "小諸市内",
        "description": description,
        "category": map_category(category_raw, title, description or ""),
        "tags": [category_raw] if category_raw else [],
        "source": "軽井沢ナビ",
    }


def fetch_slow_style_events() -> list[dict]:
    """小諸市の Slow-Style イベントをすべて取得"""
    summaries = fetch_komoro_list_pages()
    events: list[dict] = []
    for summary in summaries:
        event = fetch_event_detail(summary)
        events.append(event)
        logger.info(f"  [Slow-Style] {event['title']}")
    return events
