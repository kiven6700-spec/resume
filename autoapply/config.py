from copy import deepcopy
from pathlib import Path

import yaml

DEFAULTS = {
    "resume_path": "resume.pdf",
    "profile": {},
    "search": {
        "keywords": [],
        "countries": ["MY", "SG"],
        "locations": {"MY": "Kuala Lumpur", "SG": "Singapore"},
        "pages_per_keyword": 2,
    },
    "filters": {
        "min_score": 45,
        "title_must_include_any": [],
        "title_exclude": ["intern", "internship"],
        "company_exclude": [],
        "max_years_required": None,
        "min_salary": None,
    },
    "extra_skills": [],
    "answers": [],
    "sources": {"mycareersfuture": True, "jobstreet": True, "linkedin": False},
    "limits": {
        "max_applications_per_run": 15,
        "max_applications_per_day": 30,
        "delay_seconds": [8, 20],
    },
    "browser": {"mode": "local", "headless": False, "profile_dir": "~/.autoapply/browser-profile",
                "session_file": "session.json"},
    "cover_letter_template": "",
    "db_path": "applications.db",
}


def _merge(base: dict, override: dict) -> dict:
    out = deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str | Path) -> dict:
    path = Path(path)
    if not path.exists():
        raise SystemExit(f"Config not found: {path}. Copy config.example.yaml to config.yaml and edit it.")
    with open(path, encoding="utf-8") as f:
        user = yaml.safe_load(f) or {}
    cfg = _merge(DEFAULTS, user)
    cfg["_base_dir"] = str(path.resolve().parent)
    return cfg


def resolve(cfg: dict, p: str) -> Path:
    p = Path(p).expanduser()
    return p if p.is_absolute() else Path(cfg["_base_dir"]) / p
