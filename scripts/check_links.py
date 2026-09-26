#!/usr/bin/env python3
"""Check that every external link in the learning content still resolves.

YouTube always answers 200, even for deleted videos, so videos are checked through its
oEmbed endpoint, which 404s for videos that no longer exist.

Usage: python3 scripts/check_links.py
"""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CONTENT = Path(__file__).resolve().parent.parent / "frontend" / "src" / "content"
URL = re.compile(r"https://[^\s'\"`<>)]+")
# Hosts that answer scripted requests with a bot challenge (403). Their pages load fine in a
# browser; they are reported, but not counted as broken.
BOT_PROTECTED = {"www.cloudflare.com"}
USER_AGENT = "Mozilla/5.0 (compatible; sso-lab-link-check; +https://github.com/jwjjj1983/sso-lab)"


def collect() -> list[str]:
    urls: set[str] = set()
    for path in CONTENT.glob("*.ts"):
        for url in URL.findall(path.read_text()):
            host = urllib.parse.urlsplit(url).hostname or ""
            if host == "example" or host.endswith(".example"):  # illustrative URLs in examples
                continue
            urls.add(url)
    return sorted(urls)


def check(url: str) -> tuple[str, str | None]:
    target = url
    if urllib.parse.urlsplit(url).hostname in ("www.youtube.com", "youtube.com", "youtu.be"):
        target = "https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(url, safe="")
    request = urllib.request.Request(target, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=20) as resp:  # noqa: S310 - https only
            return url, None if resp.status < 400 else f"HTTP {resp.status}"
    except urllib.error.HTTPError as err:
        if err.code == 403 and urllib.parse.urlsplit(url).hostname in BOT_PROTECTED:
            return url, "SKIP"
        return url, f"HTTP {err.code}"
    except Exception as err:
        return url, type(err).__name__


def main() -> int:
    urls = collect()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(check, urls))
    broken = [(url, error) for url, error in results if error and error != "SKIP"]
    for url, error in results:
        if error == "SKIP":
            print(f"skip    {url}  (bot protection; check by hand)")
        else:
            print(f"{'BROKEN' if error else 'ok':6}  {url}{f'  ({error})' if error else ''}")
    print(f"\n{len(urls) - len(broken)}/{len(urls)} links ok")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
