# 小諸市イベント統合API（非公式）

> ⚠️ **非公式APIです。こもろ観光局・小諸市公式のサービスではありません。**
> 最新・正確な情報は必ず [公式サイト](https://www.komoro-tour.jp) でご確認ください。

---

## 概要

こもろ観光局のイベント情報を集約し、JSON形式で提供する非公式APIです。
地元Webサイト運営者・観光アプリ開発者・個人開発者の利用を想定しています。

## エンドポイント

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/api/events` | イベント一覧（month/category/limit/offset対応） |
| GET | `/api/events/upcoming` | 直近7日以内のイベント |
| GET | `/api/events/{event_id}` | 個別イベント詳細 |
| GET | `/api/categories` | カテゴリ一覧と件数 |
| GET | `/api/health` | ヘルスチェック |

## クエリパラメータ

```
GET /api/events?month=2026-07          # 月指定
GET /api/events?category=祭り          # カテゴリ絞り込み
GET /api/events?limit=10&offset=0      # ページネーション
GET /api/events/upcoming?days=14       # 直近14日
```

## レスポンス形式

```json
{
  "success": true,
  "data": {
    "events": [
      {
        "id": "event-20260711-a1b2c3",
        "title": "第54回 こもろ市民まつり「みこし」",
        "date": "2026-07-11",
        "time": "13:15～20:50",
        "location": "小諸市内（大手門公園など）",
        "description": "子どもみこしなど...",
        "category": "祭り",
        "url": "https://www.komoro-tour.jp/...",
        "source": "こもろ観光局"
      }
    ],
    "total": 1
  },
  "updated_at": "2026-06-27T10:00:00Z",
  "disclaimer": "非公式APIです。最新情報は公式サイトで確認してください。"
}
```

## ローカル実行

```bash
# 依存関係インストール
pip install -r requirements.txt

# スクレイピング実行（データ取得）
python scraper/scraper.py

# 詳細ページも取得する場合
python scraper/scraper.py --detail

# APIサーバー起動
uvicorn api.main:app --reload --port 8000
```

ブラウザで http://localhost:8000/docs を開くとSwagger UIが使えます。

## Vercelへのデプロイ

```bash
npm i -g vercel
vercel deploy
```

## ディレクトリ構成

```
komoro-event-api/
├── api/
│   └── main.py          # FastAPI アプリ
├── scraper/
│   └── scraper.py       # スクレイパー
├── data/
│   └── events.json      # イベントデータ（自動生成）
├── requirements.txt
├── vercel.json
└── README.md
```

## 利用規約

- 非商用・個人利用推奨
- 大量アクセス禁止（1秒以上のインターバルを設けてください）
- データの正確性は保証しません。必ず公式サイトで最終確認を
- こもろ観光局への敬意を忘れずに

## データソース

- メイン: https://www.komoro-tour.jp/blog/category/event/

## ライセンス

MIT License — ただしスクレイピング対象サイトの利用規約に従ってください。

---

*Powered by FastAPI + BeautifulSoup4 | 非公式プロジェクト*