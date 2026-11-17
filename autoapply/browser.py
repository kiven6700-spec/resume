"""Browser handling.

local mode : persistent Chrome profile on your PC, you log in by hand (`python main.py login`).
cloud mode : headless Chromium on a cloud runner (GitHub Actions). Your logins come from a
             session file built from cookies exported from your own Chrome
             (`python main.py import-cookies`), or from the AUTOAPPLY_SESSION_B64 env var / secret.
"""
import base64
import json
import os
import random
import time
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36")


def is_cloud(cfg: dict) -> bool:
    return os.environ.get("AUTOAPPLY_CLOUD") == "1" or cfg["browser"].get("mode") == "cloud"


def session_path(cfg: dict) -> Path:
    from .config import resolve
    return resolve(cfg, cfg["browser"].get("session_file", "session.json"))


def _load_session(cfg: dict) -> str | None:
    """Session (cookies) from env secret first, then from the session file."""
    b64 = os.environ.get("AUTOAPPLY_SESSION_B64", "").strip()
    p = session_path(cfg)
    if b64:
        p.write_bytes(base64.b64decode(b64))
    return str(p) if p.exists() else None


def open_browser(cfg: dict):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("Playwright missing. Run: pip install playwright && playwright install chromium")
    pw = sync_playwright().start()
    common = dict(viewport={"width": 1366, "height": 900}, locale="en-SG",
                  timezone_id="Asia/Kuala_Lumpur")

    if is_cloud(cfg):
        state = _load_session(cfg)
        if not state:
            print("WARNING: no session found. Sites needing login will be marked login_required.\n"
                  "         Run `python main.py import-cookies <file>` and set the AUTOAPPLY_SESSION_B64 secret.")
        exe = os.environ.get("AUTOAPPLY_CHROME") or cfg["browser"].get("executable_path") or None
        browser = pw.chromium.launch(headless=True, executable_path=exe, args=["--no-sandbox"])
        ctx = browser.new_context(storage_state=state, user_agent=UA, **common)
    else:
        profile = Path(cfg["browser"]["profile_dir"]).expanduser()
        profile.mkdir(parents=True, exist_ok=True)
        ctx = pw.chromium.launch_persistent_context(
            str(profile), headless=cfg["browser"].get("headless", False),
            executable_path=cfg["browser"].get("executable_path") or None, **common)
    ctx.set_default_timeout(20000)
    return pw, ctx


def close_browser(cfg: dict, pw, ctx):
    """In cloud mode, write refreshed cookies back so sessions last longer."""
    try:
        if is_cloud(cfg):
            ctx.storage_state(path=str(session_path(cfg)))
        ctx.close()
    finally:
        pw.stop()


def screenshot(cfg: dict, page, name: str):
    from .config import resolve
    d = resolve(cfg, "screenshots")
    d.mkdir(exist_ok=True)
    safe = "".join(c if c.isalnum() else "_" for c in name)[:80]
    try:
        page.screenshot(path=str(d / f"{time.strftime('%Y%m%d-%H%M%S')}_{safe}.png"), full_page=True)
    except Exception:
        pass


# Cookie-Editor / EditThisCookie export -> Playwright storage_state
_SAMESITE = {"no_restriction": "None", "none": "None", "lax": "Lax", "strict": "Strict",
             "unspecified": "Lax", None: "Lax"}


def cookies_to_storage_state(cookie_files: list[str], out: Path) -> int:
    existing = json.loads(out.read_text()) if out.exists() else {"cookies": [], "origins": []}
    by_key = {(c["name"], c["domain"], c["path"]): c for c in existing["cookies"]}
    for f in cookie_files:
        data = json.loads(Path(f).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("cookies", [])
        for c in data:
            exp = c.get("expirationDate", c.get("expires", -1))
            ck = {
                "name": c["name"], "value": c["value"], "domain": c["domain"],
                "path": c.get("path", "/"),
                "expires": float(exp) if exp not in (None, "") and not c.get("session") else -1,
                "httpOnly": bool(c.get("httpOnly", False)), "secure": bool(c.get("secure", False)),
                "sameSite": _SAMESITE.get(str(c.get("sameSite")).lower() if c.get("sameSite") else None, "Lax"),
            }
            if ck["sameSite"] == "None":
                ck["secure"] = True
            by_key[(ck["name"], ck["domain"], ck["path"])] = ck
    existing["cookies"] = list(by_key.values())
    out.write_text(json.dumps(existing, indent=1))
    return len(existing["cookies"])


def pause(cfg: dict, short: bool = False):
    lo, hi = cfg["limits"]["delay_seconds"]
    if short:
        lo, hi = 1, 3
    time.sleep(random.uniform(lo, hi))


def click_first(page, selectors: list[str], timeout: int = 4000) -> bool:
    """Click the first visible element matching any selector. Returns True if clicked."""
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            loc.wait_for(state="visible", timeout=timeout)
            loc.click()
            return True
        except Exception:
            continue
    return False
