"""Read a resume (PDF / DOCX / TXT) and pull out skills, contact info and experience."""
import re
from dataclasses import dataclass, field
from pathlib import Path

# A broad skill bank covering tech, data, business, finance and engineering roles.
# Add your own niche skills via `extra_skills` in config.yaml.
SKILL_BANK = [
    # languages
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "golang", "rust", "kotlin", "swift",
    "php", "ruby", "scala", "r", "matlab", "sql", "bash", "dart", "vba",
    # web / mobile
    "react", "react native", "angular", "vue", "next.js", "node.js", "express", "django", "flask", "fastapi",
    "spring", "spring boot", ".net", "asp.net", "laravel", "flutter", "android", "ios", "html", "css",
    "tailwind", "graphql", "rest", "rest api", "microservices",
    # data / ai
    "machine learning", "deep learning", "nlp", "computer vision", "llm", "generative ai", "pytorch",
    "tensorflow", "scikit-learn", "pandas", "numpy", "spark", "pyspark", "hadoop", "airflow", "dbt",
    "kafka", "etl", "data warehouse", "data modeling", "power bi", "tableau", "looker", "excel",
    "statistics", "a/b testing", "data analysis", "data visualization", "snowflake", "databricks", "bigquery",
    # infra
    "aws", "azure", "gcp", "google cloud", "docker", "kubernetes", "terraform", "ansible", "jenkins",
    "ci/cd", "github actions", "linux", "devops", "sre", "networking", "cybersecurity", "siem",
    "postgresql", "mysql", "mongodb", "redis", "elasticsearch", "oracle", "sql server",
    # practices / tools
    "agile", "scrum", "jira", "git", "tdd", "unit testing", "selenium", "cypress", "playwright", "qa",
    "system design", "oop", "api", "sap", "salesforce", "erp", "crm",
    # business / finance / ops
    "project management", "product management", "stakeholder management", "business analysis",
    "financial analysis", "financial modelling", "accounting", "audit", "taxation", "ifrs", "mfrs",
    "budgeting", "forecasting", "procurement", "supply chain", "logistics", "inventory management",
    "digital marketing", "seo", "sem", "google analytics", "content marketing", "social media",
    "sales", "business development", "account management", "customer service", "recruitment",
    "human resources", "payroll", "compliance", "risk management", "aml", "kyc",
    # engineering
    "autocad", "solidworks", "plc", "scada", "lean", "six sigma", "quality assurance", "iso 9001",
    "mechanical engineering", "electrical engineering", "civil engineering", "process engineering",
    # languages spoken (very relevant in MY/SG)
    "english", "bahasa malaysia", "malay", "mandarin", "cantonese", "tamil", "japanese", "korean",
]


@dataclass
class Resume:
    path: Path
    text: str
    skills: list[str] = field(default_factory=list)
    email: str = ""
    phone: str = ""
    years_experience: int | None = None


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    if suffix == ".docx":
        import docx
        d = docx.Document(str(path))
        parts = [p.text for p in d.paragraphs]
        for t in d.tables:
            for row in t.rows:
                parts.extend(c.text for c in row.cells)
        return "\n".join(parts)
    return path.read_text(encoding="utf-8", errors="ignore")


def _skill_pattern(skill: str) -> re.Pattern:
    # word boundaries that also work for skills like "c++", "c#", ".net", "ci/cd"
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(skill) + r"(?![A-Za-z0-9])", re.IGNORECASE)


_PATTERNS: dict[str, re.Pattern] = {}


def find_skills(text: str, bank: list[str]) -> list[str]:
    found = []
    for s in bank:
        pat = _PATTERNS.setdefault(s, _skill_pattern(s))
        # single-letter "r" is too noisy unless written like "R," / "R programming"
        if s == "go":  # avoid "go-to", "go live", "on the go"
            if re.search(r"golang|(?<![A-Za-z])Go(?![A-Za-z-])(?!\s+(?:live|to|ahead|beyond)\b)", text):
                found.append(s)
            continue
        if s == "r":
            if re.search(r"(?<![A-Za-z])R(?:\s+programming|,|/|\s*\()", text):
                found.append(s)
            continue
        if pat.search(text):
            found.append(s)
    return found


def _estimate_years(text: str) -> int | None:
    m = re.findall(r"(\d{1,2})\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:\w+\s+){0,3}experience", text, re.I)
    if m:
        return max(int(x) for x in m)
    # fall back to the span of years mentioned (e.g. 2017 - Present)
    years = [int(y) for y in re.findall(r"\b(19[89]\d|20[0-4]\d)\b", text)]
    if re.search(r"present|current", text, re.I) and years:
        from datetime import date
        years.append(date.today().year)
    if len(years) >= 2:
        span = max(years) - min(years)
        return span if 0 < span < 45 else None
    return None


def parse_resume(path: str | Path, extra_skills: list[str] | None = None) -> Resume:
    path = Path(path)
    if not path.exists():
        raise SystemExit(f"Resume not found: {path}")
    text = extract_text(path)
    if len(text.strip()) < 50:
        raise SystemExit("Could not read text from the resume (is it a scanned image PDF? export it as a text PDF or DOCX).")
    bank = list(dict.fromkeys(SKILL_BANK + [s.lower() for s in (extra_skills or [])]))
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    phone = re.search(r"(?:\+?6[05][\s-]?)?\(?\d{2,3}\)?[\s-]?\d{3,4}[\s-]?\d{4}", text)
    return Resume(
        path=path,
        text=text,
        skills=find_skills(text, bank),
        email=email.group(0) if email else "",
        phone=phone.group(0) if phone else "",
        years_experience=_estimate_years(text),
    )
