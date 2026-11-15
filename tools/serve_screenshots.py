"""Launch the workbench with a completed session for screenshot capture."""
from __future__ import annotations

import argparse
import http.client
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.run_workbench import make_server
from models.workbench import Workbench


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs" / "screenshot-workbench")
    parser.add_argument("--hold", type=float, default=600.0, help="seconds to keep serving")
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    workbench = Workbench(args.output)
    # Seed a completed session synchronously so the first page load has content.
    settings = {"scenario": "clean", "seed": 7, "arm": "active", "compare": True,
               "feedback": {"modalities": ["audio", "visual"], "max_gain": 0.5, "breath_bpm": 6.0},
               "consent": {"audio": True}}
    record = workbench.start(settings)
    workbench.worker.join()
    final = workbench.get(record["id"])
    print("seeded run:", final["status"], final.get("summary", {}).get("audit_valid"))

    server = make_server(workbench, args.port)
    print(f"serving on http://127.0.0.1:{args.port} for {args.hold}s", flush=True)
    import threading
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.25}, daemon=True)
    thread.start()
    try:
        deadline = time.time() + args.hold
        while time.time() < deadline:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        workbench.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
