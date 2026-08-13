from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dockline.evalrun import run_evals


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Dockline evals against Clearbay MCP")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--ids", nargs="*", default=None)
    args = parser.parse_args()
    payload = asyncio.run(run_evals(args.base_url, args.ids))
    out = Path("traces")
    out.mkdir(exist_ok=True)
    (out / "last.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    s = payload["summary"]
    print(f"{s['passed']}/{s['total']} passed  failed={s['failed_ids']}")
    for cat, n in s["by_category"].items():
        print(f"  {cat}: {n['pass']} pass / {n['fail']} fail")
    if s["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
