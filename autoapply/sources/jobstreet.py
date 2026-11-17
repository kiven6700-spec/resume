"""JobStreet Malaysia + Singapore (SEEK platform). Search via its JSON search endpoint,
apply via the in-site "Quick apply" flow. Jobs that redirect to a company website are
marked `external` and left for you to apply manually."""
import requests

from ..models import Job
from .base import Source

SITES = {
    "MY": ("https://my.jobstreet.com", "MY-Main", "en-MY"),
    "SG": ("https://sg.jobstreet.com", "SG-Main", "en-SG"),
}


class JobStreet(Source):
    name = "jobstreet"
    login_urls = ["https://my.jobstreet.com/oauth/login", "https://sg.jobstreet.com/oauth/login"]

    def search(self, page=None) -> list[Job]:
        jobs = {}
        for country in self.cfg["search"]["countries"]:
            if country not in SITES:
                continue
            base, site_key, locale = SITES[country]
            where = self.cfg["search"]["locations"].get(country, "")
            for kw in self.cfg["search"]["keywords"]:
                for p in range(1, self.cfg["search"]["pages_per_keyword"] + 1):
                    r = requests.get(f"{base}/api/jobsearch/v5/search", timeout=30,
                                     headers={"user-agent": "Mozilla/5.0"},
                                     params={"siteKey": site_key, "keywords": kw, "where": where,
                                             "page": p, "pageSize": 30, "locale": locale, "sortmode": "ListedDate"})
                    if not r.ok:
                        print(f"  jobstreet {country} search failed: HTTP {r.status_code}")
                        break
                    data = r.json().get("data", [])
                    for it in data:
                        loc = ", ".join(l.get("label", "") for l in it.get("locations", []))
                        jobs[it["id"]] = Job(
                            source=self.name, job_id=str(it["id"]), title=it["title"],
                            company=it.get("companyName") or (it.get("advertiser") or {}).get("description", ""),
                            location=loc, country=country, url=f"{base}/job/{it['id']}",
                            salary=it.get("salaryLabel", ""),
                            description="\n".join([it.get("teaser", "")] + it.get("bulletPoints", [])),
                        )
                    if len(data) < 30:
                        break
        return list(jobs.values())

    def read_description(self, page, job: Job) -> str:
        page.goto(job.url, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        loc = page.locator('[data-automation="jobAdDetails"]')
        return loc.inner_text() if loc.count() else ""

    def apply(self, page, job, resume, dry_run):
        # caller has already opened job.url via read_description()
        btn = page.locator('[data-automation="job-detail-apply"]').first
        try:
            btn.wait_for(state="visible", timeout=8000)
        except Exception:
            return "failed", "Apply button not found (job may be closed)"
        text = (btn.inner_text() or "").lower()
        if "quick apply" not in text:
            return "external", "Applies on company website"
        btn.click()
        page.wait_for_timeout(3000)
        if "/oauth/" in page.url or "login" in page.url:
            return "login_required", "Run `python main.py login` and sign in to JobStreet"
        return self.run_wizard(page, resume, dry_run, job=job)
