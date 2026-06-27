"""
小諸市イベント統合API
FastAPI実装
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ── パス設定 ──────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
EVENTS_FILE = Path(__file__).parent / "events.json"

# ── アプリ初期化 ──────────────────────────────────────────
app = FastAPI(
    title="小諸市イベント統合API（非公式）",
    description=(
        "こもろ観光局のイベント情報を集約した非公式APIです。\n\n"
        "- 公式サイト: https://www.komoro-tour.jp\n"
        "- 大量アクセス禁止・非商用利用推奨\n"
        "- 最新情報は必ず公式サイトでご確認ください"
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

DISCLAIMER = "非公式APIです。最新情報は公式サイト（https://www.komoro-tour.jp）で確認してください。"


# ── ユーティリティ ────────────────────────────────────────

def load_events() -> dict:
    """JSONファイルからイベントデータを読み込む"""
    if not EVENTS_FILE.exists():
        return {"events": [], "updated_at": None, "total": 0}
    with open(EVENTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def success_response(data: dict, updated_at: Optional[str] = None) -> dict:
    return {
        "success": True,
        "data": data,
        "updated_at": updated_at,
        "disclaimer": DISCLAIMER,
    }


def filter_by_month(events: list[dict], month: str) -> list[dict]:
    """month='2026-07' 形式でフィルタ"""
    return [e for e in events if (e.get("date") or "").startswith(month)]


def filter_upcoming(events: list[dict], days: int = 7) -> list[dict]:
    """今日から指定日数以内のイベントを返す"""
    today = date.today()
    limit = today + timedelta(days=days)
    result = []
    for e in events:
        d_str = e.get("date")
        if not d_str:
            continue
        try:
            d = date.fromisoformat(d_str)
            if today <= d <= limit:
                result.append(e)
        except ValueError:
            pass
    return result


# ── エンドポイント ────────────────────────────────────────

@app.get("/", tags=["root"])
def root():
    return {
        "message": "小諸市イベント統合API（非公式）",
        "endpoints": {
            "全イベント": "/api/events",
            "月指定": "/api/events?month=2026-07",
            "直近7日": "/api/events/upcoming",
            "個別詳細": "/api/events/{event_id}",
            "Swagger UI": "/docs",
        },
        "disclaimer": DISCLAIMER,
    }


@app.get("/api/events", tags=["events"])
def get_events(
    month: Optional[str] = Query(
        None,
        description="月指定フィルタ（例: 2026-07）",
        pattern=r"^\d{4}-\d{2}$",
    ),
    category: Optional[str] = Query(None, description="カテゴリフィルタ（例: 祭り）"),
    limit: int = Query(50, ge=1, le=200, description="最大取得件数"),
    offset: int = Query(0, ge=0, description="オフセット"),
):
    """
    イベント一覧を取得します。

    - **month**: `2026-07` 形式で月絞り込み
    - **category**: カテゴリ絞り込み（祭り / コンサート / スポーツ / 展示 / 食 / 自然 / 文化 / その他）
    - **limit / offset**: ページネーション
    """
    store = load_events()
    events: list[dict] = store.get("events", [])

    if month:
        events = filter_by_month(events, month)

    if category:
        events = [e for e in events if e.get("category") == category]

    total = len(events)
    paged = events[offset : offset + limit]

    return success_response(
        {
            "events": paged,
            "total": total,
            "limit": limit,
            "offset": offset,
        },
        updated_at=store.get("updated_at"),
    )


@app.get("/api/events/upcoming", tags=["events"])
def get_upcoming_events(
    days: int = Query(7, ge=1, le=30, description="今日から何日以内か"),
):
    """
    直近N日以内（デフォルト7日）のイベントを返します。
    """
    store = load_events()
    events = filter_upcoming(store.get("events", []), days=days)

    return success_response(
        {"events": events, "total": len(events), "days": days},
        updated_at=store.get("updated_at"),
    )


@app.get("/api/events/{event_id}", tags=["events"])
def get_event_detail(event_id: str):
    """
    個別イベントの詳細を返します。
    """
    store = load_events()
    for event in store.get("events", []):
        if event.get("id") == event_id:
            return success_response({"event": event}, updated_at=store.get("updated_at"))

    raise HTTPException(status_code=404, detail=f"イベントが見つかりません: {event_id}")


@app.get("/api/categories", tags=["meta"])
def get_categories():
    """利用可能なカテゴリ一覧と件数を返します。"""
    store = load_events()
    counts: dict[str, int] = {}
    for e in store.get("events", []):
        cat = e.get("category", "その他")
        counts[cat] = counts.get(cat, 0) + 1

    return success_response(
        {"categories": [{"name": k, "count": v} for k, v in sorted(counts.items())]},
        updated_at=store.get("updated_at"),
    )


@app.get("/api/health", tags=["meta"])
def health():
    """ヘルスチェック"""
    store = load_events()
    return {
        "status": "ok",
        "events_count": store.get("total", len(store.get("events", []))),
        "data_updated_at": store.get("updated_at"),
        "server_time": datetime.utcnow().isoformat() + "Z",
    }