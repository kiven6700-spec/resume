"""LinkedIn Easy Apply (Malaysia / Singapore).

WARNING: LinkedIn's User Agreement forbids automated activity and actively restricts
accounts that use bots. This source is OFF by default. Enable at your own risk and keep
the daily limit low."""
import re
from urllib.parse import quote_plus

from ..models import Job
from .base import Source

COUNTRY_NAMES = {"MY": "Malaysia", "SG": "Singapore"}


class LinkedIn(Source):
    name = "linkedin"
    needs_browser_search = True
    login_urls = ["https://www.linkedin.com/login"]
    MODAL = 'div[role="dialog"]'

    def search(self, page=None) -> list[Job]:
        jobs = {}
        for country in self.cfg["search"]["countries"]:
            for kw in self.cfg["search"]["keywords"]:
                for p in range(self.cfg["search"]["pages_per_keyword"]):
                    url = (f"https://www.linkedin.com/jobs/search/?keywords={quote_plus(kw)}"
                           f"&location={quote_plus(COUNTRY_NAMES[country])}&f_AL=true&f_TPR=r604800&start={p*25}")
                    page.goto(url, wait_until="domcontentloaded")
                    page.wait_for_timeout(4000)
                    if "/login" in page.url or "authwall" in page.url:
                        print("  linkedin: not logged in, run `python main.py login`")
                        return []
                    cards = page.locator("li[data-occludable-job-id]")
                    n = cards.count()
                    for i in range(n):
                        c = cards.nth(i)
                        c.scroll_into_view_if_needed()
                        jid = c.get_attribute("data-occludable-job-id")
                        lines = [l.strip() for l in c.inner_text().split("\n") if l.strip()]
                        if not jid or len(lines) < 2:
                            continue
                        jobs[jid] = Job(source=self.name, job_id=jid, title=lines[0],
                                        company=lines[2] if len(lines) > 2 and lines[1] == lines[0] else lines[1],
                                        location=COUNTRY_NAMES[country], country=country,
                                        url=f"https://www.linkedin.com/jobs/view/{jid}/")
                    if n < 25:
                        break
        return list(jobs.values())

    def read_description(self, page, job: Job) -> str:
        page.goto(job.url, wait_until="domcontentloaded")
        page.wait_for_timeout(3500)
        for sel in ("#job-details", ".jobs-description__content", ".jobs-box__html-content"):
            loc = page.locator(sel).first
            if loc.count():
                return loc.inner_text()
        return ""

    def apply(self, page, job, resume, dry_run):
        btn = page.get_by_role("button", name=re.compile(r"easy apply", re.I)).first
        try:
            btn.wait_for(state="visible", timeout=8000)
        except Exception:
            if page.get_by_text(re.compile(r"Applied \d+", re.I)).count():
                return "applied", "already applied earlier"
            return "external", "No Easy Apply button"
        btn.click()
        page.wait_for_timeout(2500)
        # untick "follow company" so you don't follow every company you apply to
        follow = page.locator(f'{self.MODAL} input#follow-company-checkbox')
        if follow.count() and follow.is_checked():
            follow.uncheck(force=True)
        status, note = self.run_wizard(page, resume, dry_run, scope=self.MODAL, job=job)
        if status != "applied":
            self._discard(page)
        else:
            dismiss = page.get_by_role("button", name=re.compile(r"dismiss|done", re.I)).first
            if dismiss.count():
                dismiss.click()
        return status, note

    def _discard(self, page):
        try:
            page.locator(f'{self.MODAL} button[aria-label="Dismiss"]').first.click(timeout=3000)
            page.get_by_role("button", name=re.compile(r"discard", re.I)).first.click(timeout=3000)
        except Exception:
            pass
