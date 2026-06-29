"""
イベント開催場所テキストから緯度経度を推定する。
観光スポットデータと既知の地名キーワードを優先マッチする。
マッチしない場合は座標を付けない（小諸中心などの仮座標は使わない）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).parent / "data"
SPOTS_FILE = DATA_DIR / "spots_test.json"

# スポットデータにないがイベントでよく出る地名
EXTRA_LOCATIONS: list[tuple[list[str], float, float, str]] = [
    (["佐久平・岩村田", "岩村田"], 36.2711, 138.4782, "佐久平・岩村田"),
    (["北軽井沢"], 36.4560, 138.6550, "北軽井沢"),
    (["旧軽井沢"], 36.3550, 138.6330, "旧軽井沢"),
    (["新軽井沢", "南軽井沢"], 36.3480, 138.5980, "新軽井沢"),
    (["中軽井沢"], 36.3840, 138.5680, "中軽井沢"),
    (["軽井沢"], 36.3428, 138.6350, "軽井沢"),
    (["中込・野沢", "中込", "野沢"], 36.2660, 138.5180, "中込・野沢"),
    (["御代田"], 36.4120, 138.5020, "御代田"),
    (["佐久"], 36.2480, 138.4760, "佐久市"),
    (["追分"], 36.4560, 138.6010, "追分"),
    (["東御"], 36.3550, 138.4950, "東御市"),
    (["小諸市内", "小諸"], 36.3315, 138.4261, "小諸市"),
    (["小諸駅", "駅前", "大手門", "せせらぎ", "まちタネ", "まちたね", "停車場"], 36.3315, 138.4261, "小諸駅前"),
    (["健速神社"], 36.3292, 138.4285, "健速神社"),
    (["みはらし"], 36.3420, 138.4180, "みはらし交流館"),
    (["高峰", "高原"], 36.3550, 138.4050, "高峰高原"),
    (["スタラス"], 36.3280, 138.4300, "スタラス小諸"),
    (["美術館", "高原美術館"], 36.3400, 138.4120, "小諸高原美術館"),
    (["市役所", "公民館"], 36.3270, 138.4230, "小諸市役所付近"),
]

UNRELIABLE_CONFIDENCE = frozenset({"fallback", "default", "unresolved"})


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


def _location_candidates(text: str) -> list[str]:
    """全文と空白区切りの各部分を、長い順に試す。"""
    seen: set[str] = set()
    parts: list[str] = []
    for part in [text, *text.split()]:
        part = part.strip()
        if part and part not in seen:
            seen.add(part)
            parts.append(part)
    return sorted(parts, key=len, reverse=True)


def _match_location_text(text: str) -> Optional[tuple[float, float, str, int]]:
    best: Optional[tuple[float, float, str, int]] = None
    for keywords, lat, lng, label in _keyword_entries():
        for kw in keywords:
            if not kw:
                continue
            if text == kw:
                score = len(kw) + 1000
            elif len(kw) >= 3 and kw in text:
                score = len(kw)
            else:
                continue
            if best is None or score > best[3]:
                best = (lat, lng, label, score)
    return best


def _unresolved(location_text: str) -> dict:
    label = location_text.strip() or None
    return {
        "lat": None,
        "lng": None,
        "location_label": label,
        "geocode_confidence": "unresolved",
    }


def geocode_location(location: Optional[str]) -> dict:
    """開催場所文字列から lat/lng を推定する。特定できなければ座標なし。"""
    text = (location or "").strip()
    if not text:
        return _unresolved("")

    best: Optional[tuple[float, float, str, int]] = None
    for candidate in _location_candidates(text):
        match = _match_location_text(candidate)
        if match and (best is None or match[3] > best[3]):
            best = match

    if best:
        lat, lng, label, _ = best
        return {
            "lat": lat,
            "lng": lng,
            "location_label": label,
            "geocode_confidence": "matched",
        }

    return _unresolved(text)


def _location_text(event: dict) -> str:
    """ジオコード入力。location_label は出力なので含めない。"""
    parts = [
        event.get("location") or "",
        event.get("area") or "",
    ]
    return " ".join(p for p in parts if p).strip()


def has_map_coordinates(event: dict) -> bool:
    """地図表示に使える座標があるか。"""
    lat, lng = event.get("lat"), event.get("lng")
    if lat is None or lng is None:
        return False
    conf = event.get("geocode_confidence")
    if conf in UNRELIABLE_CONFIDENCE:
        return False
    return True


def clear_unreliable_coordinates(event: dict) -> dict:
    """旧 fallback/default 座標を除去してから再ジオコードする。"""
    cleaned = dict(event)
    conf = cleaned.get("geocode_confidence")
    if conf in UNRELIABLE_CONFIDENCE:
        cleaned["lat"] = None
        cleaned["lng"] = None
        cleaned.pop("location_label", None)
    return cleaned


def _needs_regeocode(event: dict) -> bool:
    conf = event.get("geocode_confidence")
    if conf == "source":
        return False
    if conf == "matched":
        return False
    return True


def enrich_event(event: dict) -> dict:
    """イベント dict に座標フィールドを付与する。"""
    enriched = clear_unreliable_coordinates(event)
    if not _needs_regeocode(enriched):
        enriched.setdefault("location_label", enriched.get("location") or "")
        return enriched
    geo = geocode_location(_location_text(enriched))
    enriched.update(geo)
    return enriched
