"""Print daily shadow-VLM trace distributions; captions intentionally never appear."""
from __future__ import annotations
import collections, json
from datetime import datetime
from core.sandbox import get_paths

def main() -> None:
    rows = []
    path = get_paths().visual_trace_log()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try: rows.append(json.loads(line))
            except json.JSONDecodeError: pass
    groups = collections.defaultdict(list)
    for row in rows: groups[datetime.fromtimestamp(row.get("ts", 0)).date().isoformat()].append(row)
    for day, items in sorted(groups.items()):
        print(day, json.dumps({
            "scene": collections.Counter(x.get("scene") for x in items if x.get("scene")).most_common(),
            "activity": collections.Counter(x.get("activity") for x in items if x.get("activity")).most_common(),
            "dropped": collections.Counter(x.get("dropped") for x in items if x.get("dropped")).most_common(),
            "confidence_histogram": collections.Counter(int(x.get("confidence", 0) * 10) / 10 for x in items if "confidence" in x).most_common(),
        }, ensure_ascii=False))

if __name__ == "__main__": main()
