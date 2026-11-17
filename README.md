# job-autoapply (Malaysia & Singapore)

Reads your resume, finds matching jobs on **MyCareersFuture (SG)**, **JobStreet (MY + SG)** and
optionally **LinkedIn Easy Apply**, ranks them by fit, and applies through each site's own
application form. Any question it can't answer from your config gets skipped instead of guessed.

## Setup
```bash
pip install -r requirements.txt
playwright install chromium
cp config.example.yaml config.yaml     # then edit it: profile, keywords, answers
```
Put your resume next to `config.yaml` (PDF, DOCX or TXT) and set `resume_path`.

## Use
```bash
python main.py resume            # check which skills/experience were detected
python main.py login             # log in once: Singpass (MCF), JobStreet MY/SG, LinkedIn
python main.py search            # ranked matches -> matches.csv (nothing is submitted)
python main.py apply --dry-run   # fills forms, stops before Submit
python main.py apply             # asks y/n per job
python main.py apply --auto      # no prompts (respects daily limits)
python main.py report            # status counts -> applications.csv
python main.py import-cookies f.json   # cloud: cookies exported from your Chrome
python main.py export-session    # cloud: base64 for the AUTOAPPLY_SESSION_B64 secret
```
Options: `--source jobstreet mycareersfuture`, `--limit 5`, `-c other_config.yaml`.

## Run it fully in the cloud (GitHub Actions, free)
Nothing runs on your PC except a one-time cookie export. Each run gets a fresh headless Chrome in the cloud.

1. **Create a PRIVATE GitHub repo** and push this folder to it. Add `config.yaml` and your resume.
   The repo must be private because both contain your personal details.
   (Or keep `config.yaml` out of git and paste it into the secret `AUTOAPPLY_CONFIG_YAML`.)
2. **Export your logins from your own Chrome.** Install the *Cookie-Editor* extension. Log in to
   each site, open Cookie-Editor, then **Export → JSON** and save it to a file:
   - `my.jobstreet.com` → `jobstreet_my.cookies.json`
   - `sg.jobstreet.com` → `jobstreet_sg.cookies.json`
   - `www.mycareersfuture.gov.sg` (after the Singpass login) → `mcf.cookies.json`
   - `www.linkedin.com` (only if you enable LinkedIn) → `linkedin.cookies.json`
3. Turn them into one session secret:
   ```bash
   python main.py import-cookies *.cookies.json
   python main.py export-session        # copy the long output
   ```
   In the GitHub repo, open **Settings → Secrets and variables → Actions → New secret**.
   Name it `AUTOAPPLY_SESSION_B64` and paste the output. Treat it like a password, then delete the cookie files.
4. **Actions tab → "Auto-apply jobs" → Run workflow → mode `dry-run`.** This fills forms but never submits.
   Download the run's artifact to see `matches.csv`, `applications.csv` and screenshots of any step that failed.
5. When the dry-runs look right, open **Settings → Secrets and variables → Actions → Variables** and set
   `AUTOAPPLY_SCHEDULED_MODE` = `apply`. It then applies for real on weekdays at about 09:15 and 14:45 MY/SG time.
   Change the times with the `cron:` lines in `.github/workflows/autoapply.yml`.

After each run, `applications.db` and `applications.csv` are committed back to the repo, so no job is applied to twice.

**When logins expire** (the log shows `login_required`, and the run skips that site and carries on with the others),
export that site's cookies again and repeat step 3. JobStreet usually lasts weeks. Singpass (MyCareersFuture) lasts
only hours to days, so in practice MCF jobs in the cloud get listed in `matches.csv` and you apply to them yourself.
GitHub runners use data-centre IP addresses, so LinkedIn is the most likely site to challenge or restrict the account.

## How it works
1. **Resume parsing** (`autoapply/resume.py`): extracts text, about 200 known skills plus your `extra_skills`, contact details and years of experience.
2. **Search** (`autoapply/sources/`): MyCareersFuture and JobStreet are searched through their JSON search endpoints. LinkedIn is searched in the browser.
3. **Scoring** (`autoapply/matcher.py`): 0-100 score = 50% skill coverage + 30% text similarity + 20% title match, minus a penalty when the job asks for more years than you have. Filters in `config.yaml` remove the rest.
4. **Applying**: a saved browser profile (your login) opens each job. The generic form filler (`autoapply/forms.py`) reads every field label and answers from `profile` + `answers`. It picks your latest resume and writes the cover letter from `cover_letter_template`, then clicks Continue until Submit.
5. **Tracking** (`applications.db`): never applies twice. Statuses: `applied`, `needs_manual` (unknown question, with the question text saved), `external` (company website), `filtered`, `failed`, `login_required`, `rejected_by_user`.

**Tip:** after each run, check `report` for `needs_manual` questions. Add answers for them under
`answers:` and the next run will handle those jobs.

## Notes and limits
- JobStreet: only **Quick apply** jobs are auto-submitted. Upload your resume to your JobStreet profile first.
- MyCareersFuture needs a Singpass login, which you do by hand in `login`. Sessions expire, so log in again when you see `login_required`.
- **LinkedIn prohibits automation and restricts accounts that use it.** It's disabled by default. If you enable it, keep the limits low.
- Job sites change their page layouts. If applying stops working, the selectors in `autoapply/sources/*.py` need updating. Always run `--dry-run` first.
- Local mode: keep `headless: false` so you can watch it and solve any CAPTCHA. In cloud mode a CAPTCHA can't be solved, so that job is marked `failed`, with a screenshot.
- Applying to many poorly matching jobs hurts your reputation with recruiters. Keep `min_score` reasonably high.
