from dataclasses import dataclass, field


@dataclass
class Job:
    source: str          # "mycareersfuture" | "jobstreet" | "linkedin"
    job_id: str
    title: str
    company: str
    location: str
    url: str
    country: str = ""    # "MY" | "SG"
    description: str = ""
    salary: str = ""
    min_years: int | None = None
    score: float = 0.0
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.job_id}"

    def short(self) -> str:
        return f"[{self.score:5.1f}] {self.title} @ {self.company} ({self.location}, {self.source})"
