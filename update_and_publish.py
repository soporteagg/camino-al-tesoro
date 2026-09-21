"""
Re-descarga http://10.20.28.59:8080/pub/Camino_al_Tesoro.html, regenera index.html
en este directorio y, si el contenido cambio, hace commit + push a GitHub para que
GitHub Pages quede actualizado. Pensado para correr cada 15 minutos via Task Scheduler.
"""
import os
import re
import subprocess
import sys
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "http://10.20.28.59:8080/pub/Camino_al_Tesoro.html"
REPO_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(REPO_DIR, "assets")
INDEX_PATH = os.path.join(REPO_DIR, "index.html")
LOG_PATH = os.path.join(REPO_DIR, "update.log")

FONTS_CSS_NAME = "fonts.css"
FONTS_CSS_URL = (
    "https://fonts.googleapis.com/css2?"
    "family=Montserrat:wght@700;800;900&family=Poppins:wght@400;500;600&display=swap"
)


def log(msg):
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(cmd, **kwargs):
    return subprocess.run(cmd, cwd=REPO_DIR, capture_output=True, text=True, **kwargs)


def ensure_fonts_css(session):
    """Vendor the Google Fonts CSS + ttf files once; skip if already present."""
    css_path = os.path.join(ASSETS_DIR, FONTS_CSS_NAME)
    if os.path.exists(css_path):
        return
    os.makedirs(ASSETS_DIR, exist_ok=True)
    resp = session.get(FONTS_CSS_URL, timeout=20)
    resp.raise_for_status()
    css_text = resp.text

    def repl(m):
        raw = m.group(1).strip("'\"")
        abs_url = urljoin(FONTS_CSS_URL, raw)
        font_resp = session.get(abs_url, timeout=20)
        font_resp.raise_for_status()
        name = os.path.basename(abs_url.split("?")[0])
        with open(os.path.join(ASSETS_DIR, name), "wb") as f:
            f.write(font_resp.content)
        return f"url('{name}')"

    new_css = re.sub(r"url\(([^)]+)\)", repl, css_text)
    with open(css_path, "w", encoding="utf-8") as f:
        f.write(new_css)
    log("Vendored fonts.css + font files")


def build_index_html(session):
    resp = session.get(BASE_URL, timeout=20)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding
    html = resp.text

    # Strip the full DNI ("s" field) embedded in the ranking data before it ever
    # touches disk or git — it's not shown in the UI, only masked digits ("d") are.
    html = re.sub(r',?"s":"[^"]*"', "", html)

    soup = BeautifulSoup(html, "html.parser")

    # Point the Google Fonts <link> at the locally vendored copy.
    for link in soup.find_all("link", href=True):
        href = link["href"]
        if "fonts.googleapis.com" in href:
            link["href"] = f"assets/{FONTS_CSS_NAME}"

    return str(soup)


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (mirror-script)"})

    try:
        ensure_fonts_css(session)
        new_html = build_index_html(session)
    except Exception as e:
        log(f"ERROR fetching/building page: {e}")
        sys.exit(1)

    old_html = ""
    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            old_html = f.read()

    if new_html == old_html:
        log("No changes, nothing to push.")
        return

    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        f.write(new_html)
    log("index.html updated locally.")

    run(["git", "add", "index.html", "assets"])
    commit = run(
        [
            "git",
            "commit",
            "-m",
            f"Auto-update Camino al Tesoro ({datetime.now().strftime('%Y-%m-%d %H:%M')})",
        ]
    )
    if commit.returncode != 0:
        log(f"Nothing to commit or commit failed: {commit.stdout} {commit.stderr}")
        return
    log(f"Committed: {commit.stdout.strip()}")

    push = run(["git", "push", "origin", "main"])
    if push.returncode != 0:
        log(f"ERROR pushing to GitHub: {push.stdout} {push.stderr}")
        sys.exit(1)
    log("Pushed to GitHub successfully.")


if __name__ == "__main__":
    main()
