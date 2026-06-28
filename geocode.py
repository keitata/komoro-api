"""
小諸市内のイベント開催場所テキストから緯度経度を推定する。
観光スポットデータと既知の地名キーワードを優先マッチし、
見つからない場合は小諸市中心付近を返す。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).parent / "data"
SPOTS_FILE = DATA_DIR / "spots_test.json"

# 小諸駅前・市中心
DEFAULT_LAT = 36.3315
DEFAULT_LNG = 138.4261
DEFAULT_LABEL = "小諸市中心"

# スポットデータにないがイベントでよく出る地名
EXTRA_LOCATIONS: list[tuple[list[str], float, float, str]] = [
    (["小諸駅", "駅前", "大手門", "せせらぎ", "まちタネ", "まちたね", "停車場"], 36.3315, 138.4261, "小諸駅前"),
    (["健速神社"], 36.3292, 138.4285, "健速神社"),
    (["みはらし"], 36.3420, 138.4180, "みはらし交流館"),
    (["高峰", "高原"], 36.3550, 138.4050, "高峰高原"),
    (["スタラス"], 36.3280, 138.4300, "スタラス小諸"),
    (["美術館", "高原美術館"], 36.3400, 138.4120, "小諸高原美術館"),
    (["市役所", "公民館"], 36.3270, 138.4230, "小諸市役所付近"),
]


def _load_spot_keywords() -> list[tuple[list[str], float, float, str]]:
    entries: list[tuple[list[str], float, float, str]] = []
    if not SPOTS_FILE.exists():
        return entries
    with open(SPOTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    for spot in data.get("spots", []):
        lat = spot.get("lat")
        lng = spot.get("lng")
        if lat is None or lng is None:
            continue
        name = spot.get("name", "")
        keywords = [name]
        for tag in spot.get("tags", []):
            if tag and tag not in keywords:
                keywords.append(tag)
        short = name.split(" ")[-1] if name else ""
        if short and short not in keywords:
            keywords.append(short)
        entries.append((keywords, float(lat), float(lng), name))
    return entries


def _keyword_entries() -> list[tuple[list[str], float, float, str]]:
    entries = _load_spot_keywords()
    entries.extend(EXTRA_LOCATIONS)
    return sorted(entries, key=lambda e: -max(len(k) for k in e[0]))


def geocode_location(location: Optional[str]) -> dict:
    """開催場所文字列から lat/lng を推定する。"""
    text = (location or "").strip()
    if not text or text == "小諸市内":
        return {
            "lat": DEFAULT_LAT,
            "lng": DEFAULT_LNG,
            "location_label": DEFAULT_LABEL,
            "geocode_confidence": "default",
        }

    best: Optional[tuple[float, float, str, int]] = None
    for keywords, lat, lng, label in _keyword_entries():
        for kw in keywords:
            if len(kw) < 3:
                continue
            if kw in text:
                if best is None or len(kw) > best[3]:
                    best = (lat, lng, label, len(kw))

    if best:
        lat, lng, label, _ = best
        return {
            "lat": lat,
            "lng": lng,
            "location_label": label,
            "geocode_confidence": "matched",
        }

    return {
        "lat": DEFAULT_LAT,
        "lng": DEFAULT_LNG,
        "location_label": DEFAULT_LABEL,
        "geocode_confidence": "fallback",
    }


def enrich_event(event: dict) -> dict:
    """イベント dict に座標フィールドを付与する（既存 lat/lng があれば尊重）。"""
    enriched = dict(event)
    if enriched.get("lat") is not None and enriched.get("lng") is not None:
        enriched.setdefault("geocode_confidence", "stored")
        enriched.setdefault("location_label", enriched.get("location", DEFAULT_LABEL))
        return enriched
    geo = geocode_location(enriched.get("location"))
    enriched.update(geo)
    return enriched
