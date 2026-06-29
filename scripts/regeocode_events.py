"""events.json の座標を geocode.py の最新ルールで一括更新する。"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from geocode import enrich_event, has_map_coordinates
from events_util import filter_active_events, filter_listable_events

EVENTS_FILE = ROOT / "data" / "events.json"


def main() -> None:
    data = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
    events = data.get("events", [])
    enriched = [enrich_event(e) for e in events]
    active = filter_listable_events(filter_active_events(enriched))

    with_coords = sum(1 for e in active if has_map_coordinates(e))
    print(f"events: {len(events)} -> active/listable: {len(active)}, with coords: {with_coords}")

    output = {
        **data,
        "events": sorted(active, key=lambda e: e.get("date") or "9999-99-99"),
        "total": len(active),
        "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    EVENTS_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {EVENTS_FILE}")


if __name__ == "__main__":
    main()
