"""Score how well a job fits the resume (0-100) and apply hard filters."""
import math
import re
from collections import Counter

from .models import Job
from .resume import SKILL_BANK, Resume, find_skills

STOPWORDS = set("""a an the and or of to in for with on at by from as is are be will you your we our this that
it its their they have has can must should able work working job role team candidate candidates experience
years year strong good excellent skills skill knowledge requirements responsibilities including such other
within across using use well ensure provide support new any all more least related relevant etc e g i ie
company position preferred plus minimum required responsible duties apply""".split())


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z][a-z0-9+#.]{1,}", text.lower()) if t not in STOPWORDS]


def _cosine(a: str, b: str) -> float:
    ca, cb = Counter(_tokens(a)), Counter(_tokens(b))
    if not ca or not cb:
        return 0.0
    dot = sum(ca[t] * cb[t] for t in ca.keys() & cb.keys())
    na = math.sqrt(sum(v * v for v in ca.values()))
    nb = math.sqrt(sum(v * v for v in cb.values()))
    return dot / (na * nb)


def strip_html(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


def score_job(job: Job, resume: Resume, cfg: dict) -> Job:
    text = f"{job.title}\n{job.description}"
    bank = list(dict.fromkeys(SKILL_BANK + [s.lower() for s in cfg.get("extra_skills", [])]))
    job_skills = [s for s in find_skills(text, bank) if s not in {"english"}]
    have = set(resume.skills)
    matched = [s for s in job_skills if s in have]
    missing = [s for s in job_skills if s not in have]

    # smoothed coverage: a job that names only 1-2 skills shouldn't look like a perfect fit
    skill_cov = (len(matched) + 0.8) / (len(job_skills) + 2)
    # cosine on raw text is usually 0.05-0.4; rescale so 0.35 ~ full marks
    sim = min(_cosine(resume.text, text) / 0.35, 1.0)

    keywords = [k.lower() for k in cfg["search"]["keywords"]]
    title = job.title.lower()
    title_hit = 1.0 if any(k in title for k in keywords) else (
        0.5 if any(w in title for k in keywords for w in k.split() if len(w) > 3) else 0.0)

    score = 100 * (0.5 * skill_cov + 0.3 * sim + 0.2 * title_hit)

    # experience gap penalty
    if job.min_years and resume.years_experience is not None and job.min_years > resume.years_experience:
        score -= min(25, 8 * (job.min_years - resume.years_experience))

    job.score = round(max(score, 0.0), 1)
    job.matched_skills = matched
    job.missing_skills = missing
    return job


def passes_filters(job: Job, cfg: dict) -> tuple[bool, str]:
    f = cfg["filters"]
    title = job.title.lower()
    if any(x.lower() in title for x in f.get("title_exclude") or []):
        return False, "title excluded"
    must = [x.lower() for x in f.get("title_must_include_any") or []]
    if must and not any(x in title for x in must):
        return False, "title missing required word"
    if any(x.lower() in job.company.lower() for x in f.get("company_exclude") or []):
        return False, "company excluded"
    if f.get("max_years_required") is not None and job.min_years and job.min_years > f["max_years_required"]:
        return False, f"needs {job.min_years} yrs"
    if job.score < f.get("min_score", 0):
        return False, f"score {job.score} < {f['min_score']}"
    return True, ""
