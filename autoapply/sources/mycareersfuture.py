"""MyCareersFuture (Singapore government job portal). Search uses its public API;
applying requires a Singpass login done once via `python main.py login`."""
import requests

from ..matcher import strip_html
from ..models import Job
from .base import Source

API = "https://api.mycareersfuture.gov.sg/v2"
HEADERS = {"content-type": "application/json", "user-agent": "Mozilla/5.0 (job-autoapply)"}


class MyCareersFuture(Source):
    name = "mycareersfuture"
    login_urls = ["https://www.mycareersfuture.gov.sg/"]

    def search(self, page=None) -> list[Job]:
        if "SG" not in self.cfg["search"]["countries"]:
            return []
        jobs = {}
        for kw in self.cfg["search"]["keywords"]:
            for p in range(self.cfg["search"]["pages_per_keyword"]):
                r = requests.post(f"{API}/search", params={"limit": 20, "page": p}, headers=HEADERS,
                                  json={"search": kw, "sortBy": ["new_posting_date"]}, timeout=30)
                r.raise_for_status()
                results = r.json().get("results", [])
                for it in results:
                    sal = it.get("salary") or {}
                    jobs[it["uuid"]] = Job(
                        source=self.name, job_id=it["uuid"], title=it["title"],
                        company=(it.get("postedCompany") or {}).get("name", ""),
                        location="Singapore", country="SG",
                        url=it["metadata"]["jobDetailsUrl"],
                        salary=f"SGD {sal.get('minimum')}-{sal.get('maximum')}" if sal.get("minimum") else "",
                        description=" ".join(s["skill"] for s in it.get("skills", [])),
                    )
                if len(results) < 20:
                    break
        return list(jobs.values())

    def enrich(self, job: Job) -> Job:
        r = requests.get(f"{API}/jobs/{job.job_id}", headers=HEADERS, timeout=30)
        if r.ok:
            d = r.json()
            skills = " ".join(s["skill"] for s in d.get("skills", []))
            job.description = strip_html(d.get("description", "")) + "\nSkills: " + skills
            job.min_years = d.get("minimumYearsExperience")
        return job

    def apply(self, page, job, resume, dry_run):
        page.goto(job.url, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        body = page.locator("body").inner_text()
        if "You have applied" in body or "Applied on" in body:
            return "applied", "already applied earlier"
        btn = page.get_by_role("button", name="Apply Now").or_(page.get_by_role("link", name="Apply Now")).first
        try:
            btn.wait_for(state="visible", timeout=8000)
        except Exception:
            return "failed", "Apply Now button not found"
        btn.click()
        page.wait_for_timeout(3000)
        if "singpass" in page.url.lower() or "login" in page.url.lower():
            return "login_required", "Run `python main.py login` and sign in with Singpass"
        return self.run_wizard(page, resume, dry_run, job=job)
