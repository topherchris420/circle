"""Check that a deployed CIRCLE website is really the CIRCLE website, complete and current.

Usage:
    python tools/check_live_site.py [URL] [--expect-commit SHA] [--wait SECONDS]

URL defaults to the public site, https://topherchris420.github.io/circle/. The check fetches every
published page, then every same-site script, stylesheet, image, and frame each page references, and
reports anything that is not a non-empty 200. It also recognises the failure seen on 2026-11-16: with
the repository's Pages source left on "Deploy from a branch", GitHub's own Jekyll build of README.md
raced the Actions deployment and replaced the site while every workflow stayed green.

With --expect-commit, the site's circle-deploy.json (written by the Pages workflow) must name that
commit, which catches a deployment that was overwritten or never went live. With --wait, failures are
retried until they clear or the time runs out, to allow for CDN propagation after a deploy.

Standard library only, so it runs on a bare CI runner. Exit status 0 means no problems.
"""

from __future__ import annotations

import argparse
from html.parser import HTMLParser
import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

DEFAULT_URL = "https://topherchris420.github.io/circle/"
# Every HTML entrypoint the site publishes ("" is the site root, index.html).
PAGES = ("", "workbench.html", "first-light.html", "first-light-phantom.html")
# What makes each page the CIRCLE build rather than something else at the same URL: its <title> starts
# with TITLE_PREFIX and it loads these resources (a directory listing or README that merely names them
# does not count).
TITLE_PREFIX = "CIRCLE \u00b7"
SIGNATURES = {
    "": ("site.css", "site.js", "demo-data.js"),
    "workbench.html": ("resonance.css", "resonance.js", "demo-shim.js", "demo-data.js"),
    "first-light.html": ("first-light.css", "first-light-core.js", "first-light.js"),
    "first-light-phantom.html": (),
}
STAMP = "circle-deploy.json"
USER_AGENT = "circle-site-check (+https://github.com/topherchris420/circle)"


class _References(HTMLParser):
    """Collect the URLs a page loads: scripts, stylesheets, images, media, and frames (not links)."""

    def __init__(self):
        super().__init__()
        self.urls: list[str] = []
        self.title = ""
        self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        attrs = dict(attrs)
        if tag in ("script", "img", "iframe", "source", "audio", "video") and attrs.get("src"):
            self.urls.append(attrs["src"])
        elif tag == "link" and attrs.get("href"):
            rel = (attrs.get("rel") or "").lower().split()
            if {"stylesheet", "icon", "preload", "modulepreload", "manifest"} & set(rel):
                self.urls.append(attrs["href"])


def _fetch(url: str, timeout: float) -> tuple[int, bytes, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Cache-Control": "no-cache"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, response.read(), response.headers.get("Content-Type", "")
    except HTTPError as error:
        return error.code, error.read() if error.fp else b"", error.headers.get("Content-Type", "")


def _same_site(base: str, url: str) -> bool:
    target, root = urlsplit(url), urlsplit(base)
    return (target.scheme, target.netloc) == (root.scheme, root.netloc) and target.path.startswith(root.path)


def check_site(base_url: str, expected_commit: str | None = None, timeout: float = 20) -> list[str]:
    """Return a list of human-readable problems with the site at base_url; empty means healthy."""
    base = base_url if base_url.endswith("/") else base_url + "/"
    problems: list[str] = []
    assets: dict[str, str] = {}
    try:
        for page in PAGES:
            url = urljoin(base, page)
            label = "/" + page if page else "/ (index.html)"
            status, body, content_type = _fetch(url, timeout)
            if status != 200:
                problems.append(f"{label}: HTTP {status} at {url}")
                continue
            html = body.decode("utf-8", "replace")
            if 'name="generator" content="Jekyll' in html or "markdown-body" in html:
                problems.append(
                    f"{label}: GitHub's Jekyll rendering of README.md is being served instead of the CIRCLE "
                    "site. The Pages source is 'Deploy from a branch', so a branch build raced the Actions "
                    "deployment and won. Set Settings > Pages > Source to 'GitHub Actions', then re-run "
                    "'Demo (GitHub Pages)'.")
                continue
            if "html" not in content_type:
                problems.append(f"{label}: served as {content_type or 'no content type'}, not HTML")
            parser = _References()
            parser.feed(html)
            title = " ".join(parser.title.split())
            loaded = {reference.split("?")[0].split("#")[0].rsplit("/", 1)[-1] for reference in parser.urls}
            missing = [name for name in SIGNATURES[page] if name not in loaded]
            if not title.startswith(TITLE_PREFIX) or missing:
                found = f"title {title!r}" + (f", does not load {', '.join(missing)}" if missing else "")
                problems.append(f"{label}: not the CIRCLE build ({found})")
                continue
            for reference in parser.urls:
                if reference.startswith(("data:", "blob:", "#")):
                    continue
                target = urljoin(url, reference).split("#")[0]
                if not _same_site(base, target):
                    problems.append(f"{label}: loads an external resource, {target}")
                    continue
                assets.setdefault(target, label)
        for target, label in sorted(assets.items()):
            status, body, _ = _fetch(target, timeout)
            name = target[len(base):] or target
            if status != 200:
                problems.append(f"{label}: asset {name} is HTTP {status}")
            elif not body:
                problems.append(f"{label}: asset {name} is empty")
        if expected_commit:
            status, body, _ = _fetch(urljoin(base, STAMP), timeout)
            if status != 200:
                problems.append(f"{STAMP}: HTTP {status}; the deployment is not one the Pages workflow made")
            else:
                try:
                    deployed = json.loads(body).get("commit")
                except (ValueError, AttributeError):
                    deployed = None
                if deployed != expected_commit:
                    problems.append(f"{STAMP}: the live site is commit {deployed}, expected {expected_commit}")
    except (URLError, OSError) as error:
        problems.append(f"{base}: unreachable ({getattr(error, 'reason', error)})")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("url", nargs="?", default=DEFAULT_URL)
    parser.add_argument("--expect-commit", help="the commit the live site must have been built from")
    parser.add_argument("--wait", type=float, default=0, help="seconds to keep retrying while problems remain")
    parser.add_argument("--interval", type=float, default=30, help="seconds between retries")
    args = parser.parse_args(argv)

    deadline = time.monotonic() + args.wait
    attempt = 1
    while True:
        problems = check_site(args.url, args.expect_commit)
        if not problems or time.monotonic() + args.interval > deadline:
            break
        print(f"attempt {attempt}: {len(problems)} problem(s); retrying in {args.interval:g} s", flush=True)
        time.sleep(args.interval)
        attempt += 1

    if problems:
        print(f"FAIL {args.url}")
        for problem in problems:
            print(f"  - {problem}")
            if os.environ.get("GITHUB_ACTIONS") == "true":
                print(f"::error title=CIRCLE website::{problem}")
        return 1
    commit = f" at {args.expect_commit}" if args.expect_commit else ""
    print(f"OK {args.url}: {len(PAGES)} pages and their assets are live{commit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
