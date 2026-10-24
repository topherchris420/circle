"""Launch CIRCLE's local simulation workbench. No account or network service required."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import shutil
import sys
import tempfile
from urllib.parse import unquote, urlsplit
import webbrowser
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ASSETS = ROOT / "models" / "workbench_assets"


@contextmanager
def exclusive_directory(root: Path):
    """OS-owned lock is released on crashes; works on Windows and Unix."""
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".workbench.lock").open("a+b") as handle:
        if handle.seek(0, 2) == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError("Another workbench is using this output directory. Close it or choose a different --output.") from exc
        try:
            yield
        finally:
            if sys.platform == "win32":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def make_server(workbench, port: int = 8765) -> ThreadingHTTPServer:
    from models.workbench import BusyError, scenarios
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        server_version = "CIRCLE"

        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def log_message(self, format, *args):
            pass

        def response_headers(self, status: int, content_type: str, length: int, filename: str | None = None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()

        def send_json(self, data: dict | list, status: int = 200):
            body = json.dumps(data, allow_nan=False).encode("utf-8")
            self.response_headers(status, "application/json; charset=utf-8", len(body))
            self.wfile.write(body)

        def allowed(self, mutation: bool = False) -> bool:
            port = self.server.server_address[1]
            hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
            if self.headers.get("Host") not in hosts:
                self.send_json({"error": "Open the workbench using its localhost address."}, 403)
                return False
            origin = self.headers.get("Origin")
            if (origin and origin not in {f"http://{host}" for host in hosts}) or self.headers.get("Sec-Fetch-Site") == "cross-site":
                self.send_json({"error": "Cross-site requests are not allowed."}, 403)
                return False
            if mutation and not secrets.compare_digest(self.headers.get("X-Circle-Token", ""), token):
                self.send_json({"error": "Refresh the workbench before starting or stopping a session."}, 403)
                return False
            return True

        def send_file(self, path: Path, content_type: str, filename: str | None = None):
            with path.open("rb") as handle:
                self.response_headers(200, content_type, path.stat().st_size, filename)
                shutil.copyfileobj(handle, self.wfile)

        def do_GET(self):
            if not self.allowed():
                return
            route = unquote(urlsplit(self.path).path)
            try:
                if route == "/api/config":
                    self.send_json({"token": token, "scenarios": scenarios(), "output": str(workbench.root)})
                elif route == "/api/runs":
                    self.send_json(workbench.history(compact=True))
                elif route in ("/", "/app.css", "/app.js"):
                    filename, mime = {"/": ("index.html", "text/html"), "/app.css": ("app.css", "text/css"),
                                      "/app.js": ("app.js", "text/javascript")}[route]
                    self.send_file(ASSETS / filename, mime + "; charset=utf-8")
                elif route == "/example":
                    self.send_file(ROOT / "diagrams/circle-physiology-session.html", "text/html; charset=utf-8")
                elif route.startswith("/api/runs/"):
                    self.send_json(workbench.get(route.removeprefix("/api/runs/")))
                elif route.startswith("/runs/"):
                    _, _, run_id, name = route.split("/", 3)
                    if name == "bundle.zip":
                        manifest = workbench.artifact(run_id, "manifest.json")
                        names = list(json.loads(manifest.read_text())["artifacts"]) + ["manifest.json", "audit.json"]
                        # Spool large bundles to disk instead of duplicating them in RAM.
                        with tempfile.SpooledTemporaryFile(max_size=1024 * 1024) as bundle:
                            with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
                                for item in names:
                                    path = workbench.artifact(run_id, item)
                                    # arcname is the contained relative path, never a manifest-supplied traversal.
                                    arcname = "audit.json" if item == "audit.json" else path.resolve().relative_to(manifest.parent.resolve()).as_posix()
                                    archive.write(path, arcname)
                            size = bundle.tell()
                            bundle.seek(0)
                            self.response_headers(200, "application/zip", size, f"circle-{run_id[:8]}.zip")
                            shutil.copyfileobj(bundle, self.wfile)
                    else:
                        path = workbench.artifact(run_id, name)
                        mime = "text/html; charset=utf-8" if name == "report.html" else "application/octet-stream"
                        self.send_file(path, mime, None if name == "report.html" else path.name)
                else:
                    self.send_json({"error": "Page not found."}, 404)
            except (FileNotFoundError, ValueError, KeyError):
                self.send_json({"error": "This session or artifact could not be found."}, 404)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except OSError:
                self.send_json({"error": "Could not read the saved session. Check the output folder and try again."}, 500)

        def do_POST(self):
            if not self.allowed(mutation=True):
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    raise ValueError("The request must contain a small JSON settings object.")
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ValueError("Send settings as application/json.")
                data = json.loads(self.rfile.read(length))
                route = urlsplit(self.path).path
                if route == "/api/runs":
                    self.send_json(workbench.start(data), 202)
                elif route.startswith("/api/runs/") and route.endswith("/cancel"):
                    self.send_json(workbench.cancel(route.split("/")[3]))
                else:
                    self.send_json({"error": "Action not found."}, 404)
            except BusyError as exc:
                self.send_json({"error": str(exc)}, 409)
            except (ValueError, UnicodeError) as exc:
                self.send_json({"error": str(exc)}, 400)
            except FileNotFoundError:
                self.send_json({"error": "Session not found."}, 404)
            except OSError:
                self.send_json({"error": "Could not save the session. Check disk space and output-folder permissions."}, 500)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765, help="Local port (default 8765)")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/workbench", help="Saved session directory")
    parser.add_argument("--no-browser", action="store_true", help="Print the address without opening a browser")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    try:
        from models.workbench import Workbench
    except ImportError as exc:
        print(f"CIRCLE needs its Python dependencies ({exc}).\nRun: {sys.executable} -m pip install -r requirements.txt", file=sys.stderr)
        return 1
    try:
        with exclusive_directory(args.output):
            workbench = Workbench(args.output)
            try:
                server = make_server(workbench, args.port)
                try:
                    url = f"http://127.0.0.1:{args.port}"
                    print(f"CIRCLE workbench: {url}\nSessions: {workbench.root}\nSimulation only. Press Ctrl+C to stop.", flush=True)
                    if not args.no_browser:
                        webbrowser.open(url)
                    server.serve_forever(poll_interval=0.25)
                finally:
                    server.server_close()
            finally:
                print("Finishing the current stage before closing…", flush=True)
                workbench.close()
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError) as exc:
        print(f"Cannot start CIRCLE: {exc}\nIf the port is busy, try --port 8766.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
