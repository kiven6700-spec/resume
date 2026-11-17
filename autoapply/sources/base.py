import re
import time

from ..browser import pause
from ..forms import fill_form
from ..models import Job

NEXT_RE = re.compile(r"^\s*(continue|next|review( your application)?|proceed|save and continue)\s*$", re.I)
SUBMIT_RE = re.compile(r"^\s*(submit( application| my application)?|send application|confirm( and)? apply|apply)\s*$", re.I)
SUCCESS_RE = re.compile(
    r"application (has been |was )?(sent|submitted)|successfully (applied|submitted)|"
    r"you('ve| have) (successfully )?applied|thank(s| you) for applying|your application is on its way", re.I)
ERROR_SEL = '[role="alert"], [aria-invalid="true"], .artdeco-inline-feedback--error, [data-automation*="error" i]'


class Source:
    name = "base"
    needs_browser_search = False
    login_urls: list[str] = []

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def search(self, page=None) -> list[Job]:
        raise NotImplementedError

    def apply(self, page, job: Job, resume, dry_run: bool) -> tuple[str, str]:
        """Return (status, note). status in applied|dry_run_ok|needs_manual|external|login_required|failed|low_score"""
        raise NotImplementedError

    # ---- shared helpers -------------------------------------------------
    @staticmethod
    def _button(page, scope: str | None, pattern: re.Pattern):
        root = page.locator(scope).first if scope else page
        for role in ("button", "link"):
            loc = root.get_by_role(role, name=pattern)
            for i in range(loc.count()):
                b = loc.nth(i)
                try:
                    if b.is_visible() and b.is_enabled():
                        return b
                except Exception:
                    pass
        return None

    @staticmethod
    def _page_has_success(page) -> bool:
        try:
            return bool(SUCCESS_RE.search(page.locator("body").inner_text(timeout=5000)))
        except Exception:
            return False

    def run_wizard(self, page, resume, dry_run: bool, scope: str | None = None, job=None, max_steps: int = 12):
        """Walk a multi-step application form: fill -> Next ... -> Submit."""
        last_snapshot = None
        stalls = 0
        for _ in range(max_steps):
            pause(self.cfg, short=True)
            if self._page_has_success(page):
                return "applied", ""
            unanswered = fill_form(page, scope, self.cfg, resume, job)
            if unanswered:
                return "needs_manual", "Unanswered: " + " | ".join(unanswered[:5])

            submit = self._button(page, scope, SUBMIT_RE)
            nxt = self._button(page, scope, NEXT_RE)
            if submit and not nxt:
                if dry_run:
                    return "dry_run_ok", "reached submit button (not clicked)"
                submit.click()
                time.sleep(4)
                if self._page_has_success(page):
                    return "applied", ""
                # LinkedIn/others sometimes close the modal on success without text
                if scope and page.locator(scope).count() == 0:
                    return "applied", "modal closed after submit"
                continue
            if not nxt:
                return "failed", "no Next/Submit button found"

            nxt.click()
            time.sleep(2)
            snap = (page.url, len(page.content()))
            if snap == last_snapshot:
                stalls += 1
                if stalls >= 2:
                    errs = page.locator(ERROR_SEL).all_inner_texts()
                    return "needs_manual", "Stuck on a step: " + " | ".join(e.strip() for e in errs if e.strip())[:300]
            else:
                stalls = 0
            last_snapshot = snap
        return "failed", "too many steps"
