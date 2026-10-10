#!/usr/bin/env python3
"""Regenerate docs/screenshots/ from the demo, in light and dark.

Needs the demo running (`python3 server/demo.py`) and Playwright with Google Chrome:
    pip install playwright        # a developer tool, not in requirements.txt
Then:  python3 scripts/screenshots/capture.py         (DEV_PORT if the demo runs on another port)

Every image shows the invented example person and invented companies. Look at each one before committing.
"""
import os
import pathlib

from playwright.sync_api import sync_playwright

PORT = os.environ.get("DEV_PORT", "8791")
HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent.parent / "docs" / "screenshots"
BASE = f"http://127.0.0.1:{PORT}"

SHOTS = [
    # name, url, viewport, extra wait in ms
    ("dashboard", f"{BASE}/#jobs", (1440, 1000), 1500),
    ("outreach", f"{BASE}/#outreach", (1440, 1000), 1500),
    ("extension", None, (1440, 900), 2500),
]


def main():
    scene = (HERE / "extension-scene.html").read_text().replace("__PORT__", PORT)
    scene_path = HERE / ".scene.html"
    scene_path.write_text(scene)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome")
            for theme in ("light", "dark"):
                for name, url, (w, h), wait in SHOTS:
                    page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=2, color_scheme=theme)
                    page.goto(url or scene_path.as_uri())
                    page.wait_for_timeout(wait)
                    out = OUT / f"{name}-{theme}.png"
                    page.screenshot(path=str(out))
                    page.close()
                    print("wrote", out.relative_to(OUT.parent.parent))
            browser.close()
    finally:
        scene_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
