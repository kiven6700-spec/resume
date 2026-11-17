#!/usr/bin/env python3
"""Auto-apply to jobs in Malaysia & Singapore based on your resume.

  python main.py resume              # show what was extracted from your resume
  python main.py login               # log in to job sites once (session is saved)
  python main.py search              # find & rank matching jobs, no applying
  python main.py apply --dry-run     # go through application forms but don't submit
  python main.py apply               # apply, asking y/n for each job
  python main.py apply --auto        # apply without asking
  python main.py report              # summary + applications.csv

Cloud (GitHub Actions):
  python main.py import-cookies linkedin.json jobstreet_my.json ...   # cookies from your Chrome
  python main.py export-session      # prints base64 for the AUTOAPPLY_SESSION_B64 secret
"""
import argparse
import csv
import sys
import time

import base64

from autoapply.browser import (close_browser, cookies_to_storage_state, is_cloud, open_browser,
                               pause, screenshot, session_path)
from autoapply.config import load_config, resolve
from autoapply.matcher import passes_filters, score_job
from autoapply.resume import parse_resume
from autoapply.sources import ALL_SOURCES
from autoapply.tracker import Tracker


def load_resume(cfg):
    r = parse_resume(resolve(cfg, cfg["resume_path"]), cfg["extra_skills"])
    drop = {x.lower() for x in cfg.get("exclude_skills") or []}
    r.skills = [s for s in r.skills if s not in drop]
    yrs = cfg.get("profile", {}).get("years_experience")
    if yrs is not None:
        r.years_experience = yrs
    return r


def enabled_sources(cfg, only=None):
    names = [n for n, on in cfg["sources"].items() if on and n in ALL_SOURCES]
    if only:
        names = [n for n in names if n in only]
    return [ALL_SOURCES[n](cfg) for n in names]


def cmd_resume(cfg, args):
    r = load_resume(cfg)
    print(f"Resume: {r.path}\nEmail: {r.email or '-'}\nPhone: {r.phone or '-'}")
    print(f"Years of experience used for matching: {r.years_experience}")
    print(f"Skills found ({len(r.skills)}): {', '.join(r.skills)}")
    print("\nMissing a skill? Add it under `extra_skills:` in config.yaml.")


def cmd_login(cfg, args):
    pw, ctx = open_browser({**cfg, "browser": {**cfg["browser"], "headless": False}})
    for src in enabled_sources(cfg, args.source):
        for url in src.login_urls:
            ctx.new_page().goto(url)
    print("Log in on each tab (Singpass for MyCareersFuture, your JobStreet / LinkedIn account).")
    print("Also make sure your resume is uploaded in your JobStreet profile.")
    input("Press Enter here when done to save the session... ")
    close_browser(cfg, pw, ctx)


def cmd_import_cookies(cfg, args):
    if not args.files:
        raise SystemExit("Usage: python main.py import-cookies cookies1.json [cookies2.json ...]")
    out = session_path(cfg)
    n = cookies_to_storage_state(args.files, out)
    print(f"Saved {n} cookies to {out}. Next: python main.py export-session")


def cmd_export_session(cfg, args):
    p = session_path(cfg)
    if not p.exists():
        raise SystemExit(f"{p} not found. Run import-cookies first.")
    print(base64.b64encode(p.read_bytes()).decode())


def find_matches(cfg, resume, tracker, args, page=None):
    matches = []
    for src in enabled_sources(cfg, args.source):
        if src.needs_browser_search and page is None:
            print(f"- {src.name}: searched during `apply` only (needs the browser)")
            continue
        print(f"- searching {src.name} ...")
        try:
            jobs = src.search(page)
        except Exception as e:
            print(f"  {src.name} search error: {e}")
            continue
        print(f"  {len(jobs)} jobs found")
        for job in jobs:
            if tracker.already_handled(job.key):
                continue
            score_job(job, resume, cfg)
            # quick prefilter, then fetch full description where it's cheap (MCF API)
            if job.score < cfg["filters"]["min_score"] - 20:
                continue
            if hasattr(src, "enrich"):
                src.enrich(job)
                time.sleep(0.3)
                score_job(job, resume, cfg)
            ok, _ = passes_filters(job, cfg)
            # jobstreet/linkedin only have a teaser here; final check happens on the full page
            if ok or (not hasattr(src, "enrich") and job.score >= cfg["filters"]["min_score"] - 15):
                matches.append((src, job))
    matches.sort(key=lambda m: m[1].score, reverse=True)
    return matches


def cmd_search(cfg, args):
    resume = load_resume(cfg)
    tracker = Tracker(resolve(cfg, cfg["db_path"]))
    matches = find_matches(cfg, resume, tracker, args)
    print(f"\n{len(matches)} matching jobs:\n")
    for _, j in matches[:60]:
        print(" ", j.short())
        print(f"      {j.url}")
        if j.matched_skills:
            print(f"      matched: {', '.join(j.matched_skills[:8])}")
    out = resolve(cfg, "matches.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["score", "source", "country", "title", "company", "location", "salary", "url", "matched", "missing"])
        for _, j in matches:
            w.writerow([j.score, j.source, j.country, j.title, j.company, j.location, j.salary, j.url,
                        "; ".join(j.matched_skills), "; ".join(j.missing_skills)])
    print(f"\nSaved to {out}")


def cmd_apply(cfg, args):
    resume = load_resume(cfg)
    tracker = Tracker(resolve(cfg, cfg["db_path"]))
    lim = cfg["limits"]
    run_cap = args.limit or lim["max_applications_per_run"]
    left_today = lim["max_applications_per_day"] - tracker.applied_today()
    if left_today <= 0 and not args.dry_run:
        print("Daily application limit reached. Try again tomorrow or raise limits.max_applications_per_day.")
        return

    pw, ctx = open_browser(cfg)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    done = 0
    try:
        matches = find_matches(cfg, resume, tracker, args, page)
        print(f"\n{len(matches)} candidate jobs. Mode: {'DRY RUN' if args.dry_run else ('AUTO' if args.auto else 'REVIEW')}\n")
        blocked = set()   # sources whose login expired this run
        for src, job in matches:
            if src.name in blocked:
                continue
            if done >= run_cap or (not args.dry_run and done >= left_today):
                print("Limit reached for this run.")
                break
            try:
                if hasattr(src, "read_description"):
                    full = src.read_description(page, job)
                    if full:
                        job.description = full
                        score_job(job, resume, cfg)
                ok, why = passes_filters(job, cfg)
                if not ok:
                    print(f"skip  {job.short()}  ({why})")
                    tracker.record(job, "filtered", why)
                    continue

                print(f"\n>>> {job.short()}\n    {job.url}")
                print(f"    matched: {', '.join(job.matched_skills[:10]) or '-'}")
                if job.missing_skills:
                    print(f"    missing: {', '.join(job.missing_skills[:10])}")
                if not args.auto and not args.dry_run and not is_cloud(cfg):
                    a = input("    Apply? [y]es / [n]o / [q]uit: ").strip().lower()
                    if a == "q":
                        break
                    if a != "y":
                        tracker.record(job, "rejected_by_user")
                        continue

                status, note = src.apply(page, job, resume, args.dry_run)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                status, note = "failed", f"{e.__class__.__name__}: {e}"[:300]
            print(f"    -> {status} {note}")
            if status in ("failed", "needs_manual", "login_required"):
                screenshot(cfg, page, f"{status}_{job.source}_{job.company}_{job.title}")
            if status != "dry_run_ok":
                tracker.record(job, status, note)
            if status == "login_required":
                print(f"    {src.name}: not logged in -> skipping it for this run. "
                      "Refresh its cookies (import-cookies) or run `login` locally.")
                blocked.add(src.name)
                continue
            if status in ("applied", "dry_run_ok"):
                done += 1
            pause(cfg)
    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        close_browser(cfg, pw, ctx)
    print(f"\nFinished. {'Reached submit on' if args.dry_run else 'Applied to'} {done} job(s).")
    if not args.dry_run:
        print("Jobs marked needs_manual / external are in `python main.py report`.")


def cmd_report(cfg, args):
    tracker = Tracker(resolve(cfg, cfg["db_path"]))
    for status, n in tracker.summary():
        print(f"{status:18} {n}")
    out = resolve(cfg, "applications.csv")
    tracker.export_csv(out)
    print(f"\nFull log exported to {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["resume", "login", "search", "apply", "report",
                                        "import-cookies", "export-session"])
    ap.add_argument("files", nargs="*", help="cookie JSON files (import-cookies)")
    ap.add_argument("-c", "--config", default="config.yaml")
    ap.add_argument("--source", nargs="*", choices=list(ALL_SOURCES), help="only use these sources")
    ap.add_argument("--dry-run", action="store_true", help="fill forms but never click submit")
    ap.add_argument("--auto", action="store_true", help="don't ask before each application")
    ap.add_argument("--limit", type=int, help="max applications this run")
    args = ap.parse_args()
    cfg = load_config(args.config)
    {"resume": cmd_resume, "login": cmd_login, "search": cmd_search,
     "apply": cmd_apply, "report": cmd_report,
     "import-cookies": cmd_import_cookies, "export-session": cmd_export_session}[args.command](cfg, args)


if __name__ == "__main__":
    sys.exit(main())
