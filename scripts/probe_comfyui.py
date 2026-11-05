"""Read-only development probe; no model downloads or generation submissions.

Run: uv run python scripts/probe_comfyui.py --endpoint http://127.0.0.1:8188
"""

from __future__ import annotations

import argparse
import json

from klaude_core.comfyui_probe import probe


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8188")
    args = parser.parse_args()
    try:
        result = probe(args.endpoint)
    except ValueError as error:
        print(json.dumps({"status": "unavailable", "message": str(error),
                          "generation_verified": False}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
