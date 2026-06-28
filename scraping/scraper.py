"""
イベントスクレイパー
- こもろ観光局: https://www.komoro-tour.jp/blog/category/event/
- 軽井沢ナビ:   https://www.slow-style.com/event/ （小諸エリア）
"""

import re
import json
import time
import hashlib
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from geocode import enrich_event
from events_util import filter_active_events, is_active_event

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent
BASE_URL = "https://www.komoro-tour.jp"
EVENT_LIST_URL = f"{BASE_URL}/blog/category/event/"
DATA_DIR = ROOT_DIR / "data"
EVENTS_FILE = DATA_DIR / "events.json"

# ──────────────────────────────────────────────────────────────
# User-Agent ポリシー
#   RFC 7231 に則り、Bot名 / バージョン / 目的 / 連絡先 を明示する。
#   "Mozilla/5.0 ..." のような偽装文字列は使用しない。
#   サイト管理者がログを見たとき、何者がアクセスしているか
#   すぐ判別できることを最優先とする。
# ──────────────────────────────────────────────────────────────
BOT_NAME    = "KomoroEventBot"
BOT_VERSION = "1.0"
BOT_PURPOSE = "Aggregating public event info from komoro-tour.jp for an unofficial open API"
BOT_CONTACT = "https://github.com/your-repo/komoro-event-api"   # ← 公開後に実URLへ変更

HEADERS = {
    "User-Agent": f"{BOT_NAME}/{BOT_VERSION} ({BOT_PURPOSE}; +{BOT_CONTACT})",
    "Accept-Language": "ja,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
    # クロール間隔をサーバーに伝えるヒント（非標準だが慣習的に使われる）
    "X-Robots-Tag": "noindex",
}

CATEGORY_KEYWORDS = {
    "祭り": ["まつり", "祭り", "みこし", "神輿", "花火"],
    "コンサート": ["コンサート", "音楽", "ライブ", "演奏"],
    "スポーツ": ["マラソン", "ランニング", "スポーツ", "競技"],
    "展示": ["展示", "展覧", "ギャラリー", "美術"],
    "食": ["グルメ", "食", "マルシェ", "市場", "フード"],
    "自然": ["紅葉", "桜", "花", "自然", "ハイキング"],
    "文化": ["伝統", "文化", "歴史", "体験"],
}


def make_event_id(title: str, event_date: str) -> str:
    """タイトルと日付からユニークIDを生成"""
    raw = f"{event_date}-{title}"
    digest = hashlib.md5(raw.encode()).hexdigest()[:6]
    date_part = event_date.replace("-", "") if event_date else "00000000"
    return f"event-{date_part}-{digest}"


def detect_category(text: str) -> str:
    """テキストからカテゴリを推定"""
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return category
    return "その他"


def parse_date_from_text(text: str) -> Optional[str]:
    """
    日本語テキストから日付を抽出。
    例: "2026年7月11日", "7/11", "令和8年7月11日"
    """
    # 西暦パターン
    m = re.search(r"(\d{4})[年/\-](\d{1,2})[月/\-](\d{1,2})", text)
    if m:
        y, mo, d = m.groups()
        try:
            return date(int(y), int(mo), int(d)).isoformat()
        except ValueError:
            pass

    # 月/日のみ（現在年を補完）
    m = re.search(r"(\d{1,2})[月/](\d{1,2})", text)
    if m:
        mo, d = m.groups()
        year = datetime.now().year
        try:
            candidate = date(year, int(mo), int(d))
            # 過去3ヶ月以上前なら翌年と判断
            if (candidate - date.today()).days < -90:
                candidate = date(year + 1, int(mo), int(d))
            return candidate.isoformat()
        except ValueError:
            pass

    return None


def parse_time_from_text(text: str) -> Optional[str]:
    """テキストから時間帯を抽出"""
    m = re.search(r"(\d{1,2}[:：]\d{2})\s*[〜～~\-–]\s*(\d{1,2}[:：]\d{2})", text)
    if m:
        start, end = m.groups()
        return f"{start}～{end}"
    m = re.search(r"(\d{1,2}[:：]\d{2})", text)
    if m:
        return m.group(1)
    return None


def parse_location_from_text(text: str) -> Optional[str]:
    """テキストから開催場所を抽出"""
    patterns = [
        r"(?:会場|場所|開催場所)[：:]\s*([^\n。、]+)",
        r"([^\n]+(?:公園|広場|ホール|会館|体育館|グラウンド|商店街|通り)[^\n]*)",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()[:50]
    return "小諸市内"



# ──────────────────────────────────────────────────────────────
# クロール制御
# ──────────────────────────────────────────────────────────────
CRAWL_INTERVAL_SEC = 1.5   # リクエスト間の最小待機秒数
_last_request_time: float = 0.0


def polite_get(url: str, timeout: int = 15) -> requests.Response:
    """
    礼儀正しいHTTP GETラッパー。

    - CRAWL_INTERVAL_SEC 以上のインターバルを強制
    - 送信するUser-Agentをログに記録（透明性の担保）
    - 4xx/5xx は raise_for_status() で呼び出し側へ委譲
    """
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < CRAWL_INTERVAL_SEC:
        time.sleep(CRAWL_INTERVAL_SEC - elapsed)
    logger.debug(f"  → GET {url}")
    logger.debug(f"     User-Agent: {HEADERS['User-Agent']}")
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    _last_request_time = time.time()
    resp.raise_for_status()
    return resp

def fetch_article_detail(url: str) -> dict:
    """個別記事ページから詳細を取得"""
    try:
        resp = polite_get(url, timeout=10)
        soup = BeautifulSoup(resp.text, "lxml")

        # 本文を取得（一般的なWordPressのクラス名に対応）
        body_el = (
            soup.find("div", class_=re.compile(r"entry[-_]content|post[-_]content|article[-_]body"))
            or soup.find("article")
        )
        body_text = body_el.get_text(" ", strip=True) if body_el else ""

        return {
            "date": parse_date_from_text(body_text),
            "time": parse_time_from_text(body_text),
            "location": parse_location_from_text(body_text),
            "description": body_text[:200].strip() if body_text else None,
        }
    except Exception as e:
        logger.warning(f"詳細取得失敗 {url}: {e}")
        return {}


def fetch_event_list(url: str = EVENT_LIST_URL) -> list[dict]:
    """
    イベント一覧ページから記事リストを取得。

    komoro-tour.jp の実際のHTML構造:
      <article>
        <a href="https://www.komoro-tour.jp/blog/id_XXXXX/">
          <p class="date"><time datetime="2026-06-26">...</time></p>
          <div class="inner">
            <h1 class="tit">タイトル</h1>
            <ul class="tags"><li>#タグ</li>...</ul>
            <div class="body"><p>本文抜粋...</p></div>
          </div>
        </a>
      </article>
    """
    logger.info(f"取得中: {url}")
    try:
        resp = polite_get(url, timeout=15)
    except requests.RequestException as e:
        logger.error(f"一覧ページ取得失敗: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    events = []

    for article in soup.find_all("article"):
        # URL: article直下のaタグ
        link_el = article.find("a", href=True)
        if not link_el:
            continue
        article_url = link_el["href"]

        # タイトル: h1.tit
        title_el = article.find("h1", class_="tit")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)

        # 投稿日: time[datetime]
        time_el = article.find("time")
        post_date = None
        if time_el and time_el.get("datetime"):
            try:
                post_date = dateparser.parse(time_el["datetime"]).date().isoformat()
            except Exception:
                pass

        # 本文抜粋: div.body p
        body_el = article.find("div", class_="body")
        excerpt = body_el.get_text(" ", strip=True) if body_el else ""

        # タグ: ul.tags li
        tags_el = article.find("ul", class_="tags")
        tags = [li.get_text(strip=True).lstrip("#") for li in tags_el.find_all("li")] if tags_el else []

        # イベント日付: タイトル・本文から抽出、なければ投稿日
        event_date = parse_date_from_text(title + " " + excerpt) or post_date

        event = {
            "title": title,
            "url": article_url,
            "date": event_date,
            "time": parse_time_from_text(title + " " + excerpt),
            "location": parse_location_from_text(excerpt) if excerpt else "小諸市内",
            "description": excerpt[:200] if excerpt else None,
            "category": detect_category(title + " " + excerpt),
            "tags": tags,
            "source": "こもろ観光局",
        }
        event["id"] = make_event_id(title, event_date or "")
        events.append(event)
        logger.info(f"  記事取得: {title}")

    logger.info(f"合計 {len(events)} 件取得")
    return events

def fetch_month_page(year: int, month: int) -> list[dict]:
    """月別アーカイブページから取得"""
    url = f"{EVENT_LIST_URL}?m={year}{month:02d}"
    return fetch_event_list(url)


def save_events(events: list[dict]) -> None:
    """イベントデータをJSONに保存（既存データとマージ）"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    existing: dict[str, dict] = {}
    if EVENTS_FILE.exists():
        with open(EVENTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            existing = {e["id"]: e for e in data.get("events", [])}

    added = 0
    updated = 0
    for event in events:
        enriched = enrich_event(event)
        if not is_active_event(enriched):
            continue
        eid = enriched["id"]
        if eid not in existing:
            existing[eid] = enriched
            added += 1
            logger.info(f"  新規追加: {enriched['title']}")
            continue

        prev = existing[eid]
        # 軽井沢ナビ由来は毎回上書き更新
        if enriched.get("source") == "軽井沢ナビ":
            existing[eid] = enriched
            updated += 1
            logger.info(f"  更新: {enriched['title']}")
            continue

        for key in ("lat", "lng", "location_label", "geocode_confidence", "location", "time", "description"):
            if not prev.get(key) and enriched.get(key):
                prev[key] = enriched[key]
        existing[eid] = prev

    before_count = len(existing)
    sorted_events = sorted(
        filter_active_events(list(existing.values())),
        key=lambda e: e.get("date") or "9999-99-99",
    )
    removed = before_count - len(sorted_events)

    if added == 0 and updated == 0 and removed == 0:
        logger.info("新規イベントなし・更新スキップ")
        return

    output = {
        "events": sorted_events,
        "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total": len(sorted_events),
        "disclaimer": "非公式APIです。最新情報は公式サイト（https://www.komoro-tour.jp）で確認してください。",
    }

    with open(EVENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info(
        f"保存完了: {EVENTS_FILE} ({len(sorted_events)} 件, +{added} / ~{updated} / -{removed})"
    )


def run_scrape(fetch_detail: bool = False) -> None:
    """メイン実行: 一覧取得 → 保存"""
    events = fetch_event_list()

    if fetch_detail and events:
        logger.info("詳細ページから追加情報を取得中...")
        for event in events:
            if event.get("url"):
                detail = fetch_article_detail(event["url"])
                # 一覧で取れなかった情報のみ補完
                for key in ("date", "time", "location", "description"):
                    if not event.get(key) and detail.get(key):
                        event[key] = detail[key]

    from .scraper_slow_style import fetch_slow_style_events

    logger.info("軽井沢ナビ（Slow-Style）から小諸イベントを取得中...")
    slow_style_events = fetch_slow_style_events()
    events.extend(slow_style_events)

    save_events(events)


if __name__ == "__main__":
    import sys
    detail_mode = "--detail" in sys.argv
    run_scrape(fetch_detail=detail_mode)
