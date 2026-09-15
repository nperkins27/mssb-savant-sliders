#!/usr/bin/env python3
"""Stamp the deployed pages' local script and stylesheet URLs with a hash of
each file (shared.js -> shared.js?v=1a2b3c4d5e).

GitHub Pages lets browsers reuse a file for up to 10 minutes, so without this
a visitor can get a new page with an old cached script, and anything the new
page expects from the new script is missing. With a content hash in the URL,
a changed file is a new URL, and a page always loads the scripts it was
deployed with.

Run by the workflow on the Pages artifact, after the data commit; the stamped
pages are never committed, so the site still works opened straight from disk.

Usage: python stamp_assets.py site
"""
import hashlib
import re
import sys
from pathlib import Path

# src="..." or href="..." on a <script> or <link>, pointing at a local .js or
# .css file with no query already (absolute URLs contain ":" and are skipped).
REFERENCE = re.compile(r'(<(?:script|link)\b[^>]*?\b(?:src|href)=")([^"?#:]+\.(?:js|css))(")')


def main() -> None:
    site = Path(sys.argv[1] if len(sys.argv) > 1 else "site")
    for page in sorted(site.glob("*.html")):
        text = page.read_text(encoding="utf-8")
        missing = []

        def stamp(m: re.Match) -> str:
            target = site / m.group(2)
            if not target.is_file():
                missing.append(m.group(2))
                return m.group(0)
            version = hashlib.sha256(target.read_bytes()).hexdigest()[:10]
            return f"{m.group(1)}{m.group(2)}?v={version}{m.group(3)}"

        stamped, count = REFERENCE.subn(stamp, text)
        page.write_text(stamped, encoding="utf-8", newline="\n")
        print(f"{page.name}: {count - len(missing)} stamped" + (f"; not found: {', '.join(missing)}" if missing else ""))
        if missing:
            raise SystemExit(f"ERROR: {page.name} references files that don't exist")


if __name__ == "__main__":
    main()
