"""SQLite log of every job seen/applied so nothing is applied to twice."""
import csv
import sqlite3
from datetime import datetime, date

from .models import Job


class Tracker:
    def __init__(self, path):
        self.db = sqlite3.connect(str(path))
        self.db.execute("""CREATE TABLE IF NOT EXISTS applications (
            key TEXT PRIMARY KEY, source TEXT, country TEXT, title TEXT, company TEXT, url TEXT,
            score REAL, status TEXT, note TEXT, updated_at TEXT)""")
        self.db.commit()

    def status(self, key: str) -> str | None:
        row = self.db.execute("SELECT status FROM applications WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def already_handled(self, key: str) -> bool:
        # retry jobs that only failed or were skipped earlier; never re-apply
        return self.status(key) in {"applied", "rejected_by_user", "external"}

    def record(self, job: Job, status: str, note: str = ""):
        self.db.execute(
            "INSERT OR REPLACE INTO applications VALUES (?,?,?,?,?,?,?,?,?,?)",
            (job.key, job.source, job.country, job.title, job.company, job.url, job.score,
             status, note[:500], datetime.now().isoformat(timespec="seconds")))
        self.db.commit()

    def applied_today(self) -> int:
        return self.db.execute(
            "SELECT COUNT(*) FROM applications WHERE status='applied' AND updated_at LIKE ?",
            (date.today().isoformat() + "%",)).fetchone()[0]

    def summary(self) -> list[tuple]:
        return self.db.execute(
            "SELECT status, COUNT(*) FROM applications GROUP BY status ORDER BY 2 DESC").fetchall()

    def export_csv(self, out_path):
        cur = self.db.execute("SELECT * FROM applications ORDER BY updated_at DESC")
        cols = [d[0] for d in cur.description]
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(cur.fetchall())
