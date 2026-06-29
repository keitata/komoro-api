"""
小諸市イベント統合API（非公式）
FastAPI実装
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from geocode import enrich_event  # 呼び出し: イベント系 GET の返却直前（lat/lng 付与）
from events_util import filter_listable_events, is_listable_event

# ── パス設定 ──────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent.parent
EVENTS_FILE = Path(__file__).parent / "data" / "events.json"
DATA_DIR    = Path(__file__).parent / "data"

# SPOTS_FILE       = DATA_DIR / "spots_test.json"
# RESTAURANTS_FILE = DATA_DIR / "restaurants_test.json"
# GARBAGE_FILE     = DATA_DIR / "garbage_test.json"
# CHILDCARE_FILE   = DATA_DIR / "childcare_test.json"

# ── 定数 ─────────────────────────────────────────────────
DISCLAIMER = "非公式APIです。最新情報は公式サイト（https://www.komoro-tour.jp）で確認してください。"

# ── アプリ初期化 ──────────────────────────────────────────
app = FastAPI(
    title="小諸市 非公式統合API",
    description=(
        "小諸市のイベント・観光・生活情報を集約した非公式APIです。\n\n"
        "- 公式サイト: https://www.komoro-tour.jp\n"
        "- 読み取り専用・認証不要・CORS開放\n"
        "- 大量アクセス禁止・非商用利用推奨"
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

# ── ユーティリティ ────────────────────────────────────────

def load_json(path: Path) -> dict:
    """JSON ファイルを読み込む。存在しなければ空 dict。
    呼び出し: load_events 等"""
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_events() -> dict:
    """data/events.json を読み込む。終了済み除外し、座標を enrich で正規化。"""
    data = load_json(EVENTS_FILE)
    if not data:
        return {"events": [], "updated_at": None, "total": 0}
    listed = filter_listable_events(data.get("events", []))
    normalized = [enrich_event(e) for e in listed]
    return {**data, "events": normalized, "total": len(normalized)}

def success_response(data: dict, updated_at: Optional[str] = None) -> dict:
    """API レスポンスの共通ラッパー（success / data / disclaimer）。
    呼び出し: すべての GET エンドポイントの返却直前"""
    return {
        "success": True,
        "data": data,
        "updated_at": updated_at,
        "disclaimer": DISCLAIMER,
    }

def filter_by_month(events: list[dict], month: str) -> list[dict]:
    """date が YYYY-MM で始まるイベントだけ残す。
    呼び出し: GET /api/events（month クエリ指定時）"""
    return [e for e in events if (e.get("date") or "").startswith(month)]

def filter_upcoming(events: list[dict], days: int = 7) -> list[dict]:
    """今日から days 日以内に開始する、かつ未終了のイベントだけ残す。
    呼び出し: GET /api/events/upcoming"""
    today = date.today()
    limit = today + timedelta(days=days)
    result = []
    for e in events:
        if not is_listable_event(e):
            continue
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


# ── トップページ ──────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, tags=["root"])
def root():
    """API トップページ（HTML）。エンドポイント一覧と統計を表示。
    呼び出し: ブラウザで GET /"""
    store = load_events()
    events_count = store.get("total", len(store.get("events", [])))
    last_updated = store.get("updated_at") or "未取得"
    last_updated_disp = last_updated[:10] if last_updated != "未取得" else "未取得"

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>小諸市 非公式統合API</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f8f9fa; color: #212529; }}
    header {{ background: #fff; border-bottom: 1px solid #e0e0e0; padding: 32px 48px; }}
    .badge {{ display: inline-block; background: #e8f4fd; color: #1a73e8; font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: 12px; margin-bottom: 12px; letter-spacing: 0.5px; }}
    h1 {{ font-size: 28px; font-weight: 700; margin-bottom: 8px; }}
    .subtitle {{ color: #555; font-size: 15px; margin-bottom: 16px; }}
    .base-url {{ display: inline-block; background: #f1f3f4; color: #333; font-family: monospace; font-size: 13px; padding: 6px 14px; border-radius: 6px; }}
    .links {{ display: flex; gap: 12px; margin-top: 20px; flex-wrap: wrap; }}
    .link-card {{ border: 1px solid #e0e0e0; border-radius: 8px; padding: 14px 20px; background: #fff; text-decoration: none; color: #333; min-width: 180px; transition: box-shadow .15s; }}
    .link-card:hover {{ box-shadow: 0 2px 8px rgba(0,0,0,.1); }}
    .link-card .card-title {{ font-weight: 600; font-size: 14px; margin-bottom: 4px; }}
    .link-card .card-desc {{ font-size: 12px; color: #777; }}
    main {{ max-width: 900px; margin: 0 auto; padding: 40px 48px; }}
    .stats {{ display: flex; gap: 24px; margin-bottom: 40px; flex-wrap: wrap; }}
    .stat {{ background: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 16px 24px; }}
    .stat-value {{ font-size: 24px; font-weight: 700; color: #1a73e8; }}
    .stat-label {{ font-size: 12px; color: #777; margin-top: 4px; }}
    .section-title {{ font-size: 13px; font-weight: 700; color: #777; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 1px solid #e0e0e0; }}
    .endpoint-group {{ margin-bottom: 36px; }}
    .group-label {{ font-size: 14px; font-weight: 600; color: #1a73e8; margin-bottom: 10px; }}
    .endpoint {{ display: flex; align-items: baseline; gap: 12px; padding: 10px 0; border-bottom: 1px solid #f0f0f0; }}
    .method {{ background: #e8f5e9; color: #2e7d32; font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 4px; font-family: monospace; flex-shrink: 0; }}
    .path {{ font-family: monospace; font-size: 14px; color: #1a73e8; text-decoration: none; flex-shrink: 0; }}
    .path:hover {{ text-decoration: underline; }}
    .desc {{ font-size: 13px; color: #555; }}
    .quickstart {{ background: #1e1e2e; border-radius: 8px; padding: 20px 24px; margin-bottom: 40px; }}
    .quickstart-label {{ font-size: 12px; color: #888; margin-bottom: 6px; }}
    .quickstart code {{ color: #a6e3a1; font-family: monospace; font-size: 13px; line-height: 1.8; display: block; }}
    footer {{ text-align: center; padding: 24px; font-size: 12px; color: #aaa; border-top: 1px solid #e0e0e0; margin-top: 40px; }}
    footer a {{ color: #888; }}
  </style>
</head>
<body>
  <header>
    <div class="badge">PUBLIC API</div>
    <h1>小諸市 非公式統合API</h1>
    <p class="subtitle">小諸市のイベント・観光・生活情報を集約した非公式API。読み取り専用・認証不要・CORS開放。</p>
    <div class="base-url">https://komoro-api.vercel.app</div>
    <div class="links">
      <a class="link-card" href="/docs">
        <div class="card-title">📘 APIリファレンス</div>
        <div class="card-desc">対話的に試せるSwagger UI</div>
      </a>
      <a class="link-card" href="/openapi.json">
        <div class="card-title">⚙️ OpenAPI (JSON)</div>
        <div class="card-desc">クライアント自動生成に使える仕様書</div>
      </a>
      <a class="link-card" href="/api/terms">
        <div class="card-title">📄 利用規約・免責事項</div>
        <div class="card-desc">非商用・データ保証範囲・API利用条件</div>
      </a>
    </div>
  </header>

  <main>
    <div class="stats">
      <div class="stat">
        <div class="stat-value">{events_count}</div>
        <div class="stat-label">登録イベント数</div>
      </div>
      <div class="stat">
        <div class="stat-value">毎日自動</div>
        <div class="stat-label">更新頻度</div>
      </div>
      <div class="stat">
        <div class="stat-value">{last_updated_disp}</div>
        <div class="stat-label">最終更新日</div>
      </div>
    </div>

    <div class="section-title">クイックスタート</div>
    <div class="quickstart">
      <div class="quickstart-label"># 7月のイベントを取得</div>
      <code>curl "https://komoro-api.vercel.app/api/events?month=2026-07"</code>
      <div class="quickstart-label" style="margin-top:12px;"># 直近7日のイベントを取得</div>
      <code>curl "https://komoro-api.vercel.app/api/events/upcoming"</code>
    </div>

    <div class="section-title">エンドポイント</div>

    <div class="endpoint-group">
      <div class="group-label">events — イベント情報</div>
      <div class="endpoint"><span class="method">GET</span><a class="path" href="/api/events">/api/events</a><span class="desc">イベント一覧（month / category / limit / offset）</span></div>
      <div class="endpoint"><span class="method">GET</span><a class="path" href="/api/events/upcoming">/api/events/upcoming</a><span class="desc">直近N日以内のイベント（days=7）</span></div>
      <div class="endpoint"><span class="method">GET</span><span class="path">/api/events/{{event_id}}</span><span class="desc">個別イベント詳細</span></div>
      <div class="endpoint"><span class="method">GET</span><a class="path" href="/api/categories">/api/categories</a><span class="desc">カテゴリ一覧と件数</span></div>
    </div>

    <!-- 一時無効: spots / restaurants / garbage / childcare
    <div class="endpoint-group">
      <div class="group-label">spots — 観光スポット</div>
      <div class="endpoint"><span class="method">GET</span><a class="path" href="/api/spots">/api/spots</a><span class="desc">観光スポット一覧（懐古園・動物園・温泉など）</span></div>
    </div>

    <div class="endpoint-group">
      <div class="group-label">restaurants — 飲食店</div>
      <div class="endpoint"><span class="method">GET</span><a class="path" href="/api/restaurants">/api/restaurants</a><span class="desc">飲食店一覧（category絞り込み可）</span></div>
    </div>

    <div class="endpoint-group">
      <div class="group-label">garbage — ゴミ収集日</div>
      <div class="endpoint"><span class="method">GET</span><a class="path" href="/api/garbage">/api/garbage</a><span class="desc">ゴミ収集日（area=大手地区 で地区絞り込み）</span></div>
    </div>

    <div class="endpoint-group">
      <div class="group-label">childcare — 子育て施設</div>
      <div class="endpoint"><span class="method">GET</span><a class="path" href="/api/childcare">/api/childcare</a><span class="desc">保育園・児童館・遊び場・子育て支援センター</span></div>
    </div>
    -->

    <div class="endpoint-group">
      <div class="group-label">meta</div>
      <div class="endpoint"><span class="method">GET</span><a class="path" href="/api/health">/api/health</a><span class="desc">ヘルスチェック</span></div>
      <div class="endpoint"><span class="method">GET</span><a class="path" href="/api/terms">/api/terms</a><span class="desc">利用規約・免責事項</span></div>
    </div>
  </main>

  <footer>
    データソース: <a href="https://www.komoro-tour.jp">こもろ観光局</a> ／
    非公式APIです。最新情報は必ず公式サイトでご確認ください。<br>
    お問い合わせ: <a href="mailto:sakurai.07111@gmail.com">sakurai.07111@gmail.com</a>
  </footer>
</body>
</html>"""


# ── イベント ──────────────────────────────────────────────

@app.get("/api/events", tags=["events"])
def get_events(
    month: Optional[str] = Query(None, description="月指定（例: 2026-07）", pattern=r"^\d{4}-\d{2}$"),
    category: Optional[str] = Query(None, description="カテゴリ（例: 祭り）"),
    limit: int = Query(50, ge=1, le=200, description="最大取得件数"),
    offset: int = Query(0, ge=0, description="オフセット"),
):
    """イベント一覧。座標は enrich_event で付与。
    呼び出し: GET /api/events（フロント komoroClient・管理画面の小諸APIタブ）"""
    store = load_events()
    events = store.get("events", [])
    if month:
        events = filter_by_month(events, month)
    if category:
        events = [e for e in events if e.get("category") == category]
    total = len(events)
    enriched = [enrich_event(e) for e in events[offset:offset + limit]]
    return success_response(
        {"events": enriched, "total": total, "limit": limit, "offset": offset},
        updated_at=store.get("updated_at"),
    )


@app.get("/api/events/upcoming", tags=["events"])
def get_upcoming_events(
    days: int = Query(7, ge=1, le=120, description="今日から何日以内か"),
):
    """直近 N 日以内のイベント一覧。
    呼び出し: GET /api/events/upcoming"""
    store = load_events()
    events = filter_upcoming(store.get("events", []), days=days)
    enriched = [enrich_event(e) for e in events]
    return success_response(
        {"events": enriched, "total": len(enriched), "days": days},
        updated_at=store.get("updated_at"),
    )


@app.get("/api/events/{event_id}", tags=["events"])
def get_event_detail(event_id: str):
    """イベント1件の詳細。
    呼び出し: GET /api/events/{event_id}"""
    store = load_events()
    for event in store.get("events", []):
        if event.get("id") == event_id:
            return success_response({"event": enrich_event(event)}, updated_at=store.get("updated_at"))
    # 終了済みまたは存在しない
    raw = load_json(EVENTS_FILE)
    for event in raw.get("events", []):
        if event.get("id") == event_id and not is_listable_event(event):
            raise HTTPException(status_code=404, detail=f"イベントは終了しました: {event_id}")
    raise HTTPException(status_code=404, detail=f"イベントが見つかりません: {event_id}")


@app.get("/api/categories", tags=["events"])
def get_categories():
    """カテゴリ名と件数の一覧。
    呼び出し: GET /api/categories"""
    store = load_events()
    counts: dict[str, int] = {}
    for e in store.get("events", []):
        cat = e.get("category", "その他")
        counts[cat] = counts.get(cat, 0) + 1
    return success_response(
        {"categories": [{"name": k, "count": v} for k, v in sorted(counts.items())]},
        updated_at=store.get("updated_at"),
    )


# ── 観光スポット（一時無効） ──────────────────────────────
#
# @app.get("/api/spots", tags=["spots"])
# def get_spots(
#     category: Optional[str] = Query(None, description="カテゴリ（例: 温泉）"),
# ):
#     """観光スポット一覧（spots_test.json）。
#     呼び出し: GET /api/spots"""
#     store = load_json(SPOTS_FILE)
#     spots = store.get("spots", [])
#     if category:
#         spots = [s for s in spots if s.get("category") == category]
#     return success_response({"spots": spots, "total": len(spots)}, updated_at=store.get("updated_at"))
#
#
# ── 飲食店（一時無効） ────────────────────────────────────
#
# @app.get("/api/restaurants", tags=["restaurants"])
# def get_restaurants(
#     category: Optional[str] = Query(None, description="カテゴリ（例: そば）"),
# ):
#     """飲食店一覧（restaurants_test.json）。
#     呼び出し: GET /api/restaurants"""
#     store = load_json(RESTAURANTS_FILE)
#     restaurants = store.get("restaurants", [])
#     if category:
#         restaurants = [r for r in restaurants if r.get("category") == category]
#     return success_response({"restaurants": restaurants, "total": len(restaurants)}, updated_at=store.get("updated_at"))
#
#
# ── ゴミ収集日（一時無効） ────────────────────────────────
#
# @app.get("/api/garbage", tags=["garbage"])
# def get_garbage(
#     area: Optional[str] = Query(None, description="地区名（例: 大手地区）"),
# ):
#     """ゴミ収集日（garbage_test.json）。area 未指定なら全地区。
#     呼び出し: GET /api/garbage"""
#     store = load_json(GARBAGE_FILE)
#     areas = store.get("areas", [])
#     if area:
#         areas = [a for a in areas if a.get("area_name") == area]
#         if not areas:
#             raise HTTPException(status_code=404, detail=f"地区が見つかりません: {area}")
#     return success_response({"areas": areas, "total": len(areas)}, updated_at=store.get("updated_at"))
#
#
# ── 子育て施設（一時無効） ────────────────────────────────
#
# @app.get("/api/childcare", tags=["childcare"])
# def get_childcare(
#     category: Optional[str] = Query(None, description="カテゴリ（例: 保育園）"),
# ):
#     """子育て施設一覧（childcare_test.json）。
#     呼び出し: GET /api/childcare"""
#     store = load_json(CHILDCARE_FILE)
#     facilities = store.get("facilities", [])
#     if category:
#         facilities = [f for f in facilities if f.get("category") == category]
#     return success_response({"facilities": facilities, "total": len(facilities)}, updated_at=store.get("updated_at"))


# ── メタ ──────────────────────────────────────────────────

@app.get("/api/health", tags=["meta"])
def health():
    """稼働確認・events.json の件数と更新日時。
    呼び出し: GET /api/health"""
    store = load_events()
    return {
        "status": "ok",
        "events_count": store.get("total", len(store.get("events", []))),
        "data_updated_at": store.get("updated_at"),
        "server_time": datetime.utcnow().isoformat() + "Z",
    }


@app.get("/api/terms", tags=["meta"])
def get_terms():
    """利用規約・免責事項（JSON）。
    呼び出し: GET /api/terms"""
    return {
        "title": "小諸市 非公式統合API 利用規約・免責事項",
        "last_updated": "2026-06-27",
        "terms": [
            {"section": "1. 非公式APIについて", "content": "本APIはこもろ観光局・小諸市の公式サービスではありません。個人が公開情報をもとに作成した非公式APIです。"},
            {"section": "2. 利用条件", "content": "非商用・個人利用を推奨します。商用利用の場合はこもろ観光局の許諾を得てください。"},
            {"section": "3. アクセス制限", "content": "大量アクセスは禁止します。リクエスト間隔は1秒以上を推奨します。"},
            {"section": "4. データの正確性", "content": "本APIのデータは自動取得のため、最新・正確な情報を保証しません。必ず公式サイト（https://www.komoro-tour.jp）で最終確認してください。"},
            {"section": "5. 免責事項", "content": "本APIの利用によって生じたいかなる損害についても、作成者は責任を負いません。"},
            {"section": "6. サービスの変更・停止", "content": "予告なくAPIの仕様変更・停止を行う場合があります。"},
        ],
        "data_source": {"name": "こもろ観光局", "url": "https://www.komoro-tour.jp"},
        "contact": "sakurai.07111@gmail.com",
    }