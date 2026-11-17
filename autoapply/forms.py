"""Generic filler for application forms / screening questions.

It reads every visible input/select/textarea/radio group, works out its question text,
and answers it from `profile` + `answers` in config.yaml. Anything required that it
cannot answer is returned so the caller can skip the job instead of guessing.
"""
import re

COLLECT_JS = r"""
(root) => {
  root = root || document;
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return (r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none') || el.type === 'radio' || el.type === 'checkbox'; };
  const labelOf = el => {
    let t = '';
    if (el.labels && el.labels.length) t = el.labels[0].innerText;
    if (!t && el.getAttribute('aria-labelledby'))
      t = el.getAttribute('aria-labelledby').split(' ').map(id => (document.getElementById(id)||{}).innerText||'').join(' ');
    if (!t) t = el.getAttribute('aria-label') || '';
    const fs = el.closest('fieldset'); const legend = fs && fs.querySelector('legend');
    if ((el.type === 'radio' || el.type === 'checkbox') && legend) t = legend.innerText + ' :: ' + t;
    if (!t && legend) t = legend.innerText;
    if (!t) { let p = el.parentElement; for (let i = 0; i < 4 && p && !t; i++, p = p.parentElement) {
      const lab = p.querySelector('label, [class*="label" i], [class*="question" i]'); if (lab && !lab.contains(el)) t = lab.innerText; } }
    if (!t) t = el.placeholder || el.name || '';
    return t.replace(/\s+/g, ' ').trim();
  };
  const out = []; let i = 0;
  root.querySelectorAll('input, select, textarea').forEach(el => {
    const type = (el.tagName === 'INPUT' ? (el.type || 'text') : el.tagName).toLowerCase();
    if (['hidden','submit','button','file','search','image','reset'].includes(type)) return;
    if (el.disabled || !vis(el)) return;
    el.setAttribute('data-aa-idx', String(i));
    out.push({ idx: i++, type, name: el.name || '', label: labelOf(el),
      required: el.required || el.getAttribute('aria-required') === 'true',
      value: (type === 'radio' || type === 'checkbox') ? (el.checked ? 'on' : '')
           : (el.tagName === 'SELECT' ? ((el.selectedIndex > 0 || (el.options[0] && !/^\s*(select|choose|please|--|$)/i.test(el.options[0].text))) && el.selectedIndex >= 0 ? el.value : '')
           : (el.value || '')),
      options: el.tagName === 'SELECT' ? Array.from(el.options).map(o => o.text.trim()) : [] });
  });
  return out;
}
"""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def cover_letter(cfg: dict, job) -> str:
    tpl = (cfg.get("cover_letter_template") or "").strip()
    if not tpl or job is None:
        return tpl
    p = cfg.get("profile", {})
    return tpl.format_map({**{k: v for k, v in p.items()}, "title": job.title, "company": job.company,
                           "skills": ", ".join(job.matched_skills[:6])})


def build_answer_book(cfg: dict, resume, job=None) -> list[tuple[list[str], str]]:
    p = cfg.get("profile", {})
    country = getattr(job, "country", None)

    def per_country(v):
        # values may be given per country, e.g. {MY: 3000, SG: 3500}
        return v.get(country, "") if isinstance(v, dict) else v

    # answers may be limited to one country with `country: SG`
    book = [([_norm(m) for m in a["match"]], str(per_country(a["value"])))
            for a in cfg.get("answers", []) if a.get("country") in (None, country)]
    cl = cover_letter(cfg, job)
    if cl:
        book.append((["cover letter", "message to the hiring", "message to employer"], cl))
    # built-in profile mappings come after user answers so user answers win
    book += [
        (["first name", "given name"], p.get("first_name", "")),
        (["last name", "family name", "surname"], p.get("last_name", "")),
        (["full name", "your name"], p.get("full_name") or f"{p.get('first_name','')} {p.get('last_name','')}".strip()),
        (["email"], p.get("email") or resume.email),
        (["mobile", "phone", "contact number"], p.get("phone") or resume.phone),
        (["city"], p.get("city", "")),
        (["linkedin"], p.get("linkedin", "")),
        (["website", "portfolio", "github"], p.get("website", "")),
        (["years of experience", "years experience", "how many years"],
         str(p.get("years_experience") or resume.years_experience or "")),
        (["notice period"], p.get("notice_period", "")),
        (["expected salary", "salary expectation", "expected monthly"], str(per_country(p.get("expected_salary", "")))),
        (["current salary", "last drawn"], str(per_country(p.get("current_salary", "")))),
        (["nationality"], p.get("nationality", "")),
    ]
    return [(m, v) for m, v in book if v]


def answer_for(question: str, book) -> str | None:
    q = _norm(question)
    for matches, value in book:
        if any(m and m in q for m in matches):
            return value
    return None


def _pick_option(options: list[str], answer: str) -> str | None:
    a = _norm(answer)
    opts = [o for o in options if o and not _norm(o).startswith(("select", "please select", "choose", "--"))]
    for o in opts:
        if _norm(o) == a:
            return o
    for o in opts:
        if a in _norm(o) or _norm(o) in a:
            return o
    # numeric answers -> pick the range that contains the number, e.g. "3-5 years"
    if re.fullmatch(r"\d+(\.\d+)?", a):
        n = float(a)
        for o in opts:
            nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", o.replace(",", ""))]
            if len(nums) >= 2 and nums[0] <= n <= nums[1]:
                return o
            if len(nums) == 1 and re.search(r"\+|more|above|over", o, re.I) and n >= nums[0]:
                return o
            if len(nums) == 1 and re.search(r"less|below|under", o, re.I) and n < nums[0]:
                return o
    return None


def fill_form(page, scope_selector: str | None, cfg: dict, resume, job=None) -> list[str]:
    """Fill what we can. Returns a list of required questions we could NOT answer."""
    book = build_answer_book(cfg, resume, job)
    has_cl = bool(cover_letter(cfg, job))
    root = page.locator(scope_selector).first.element_handle() if scope_selector else None
    fields = page.evaluate(COLLECT_JS, root)
    unanswered = []
    radio_groups: dict[str, list[dict]] = {}

    for f in fields:
        if f["type"] in ("radio", "checkbox"):
            group_q = f["label"].split(" :: ")[0]
            radio_groups.setdefault(f["name"] or group_q, []).append(f)
            continue
        if f["value"]:
            continue  # already prefilled by the site
        ans = answer_for(f["label"], book)
        el = page.locator(f'[data-aa-idx="{f["idx"]}"]')
        try:
            if ans is None:
                if f["required"]:
                    unanswered.append(f["label"] or f["name"])
                continue
            if f["type"] == "select":
                opt = _pick_option(f["options"], ans)
                if opt:
                    el.select_option(label=opt)
                elif f["required"]:
                    unanswered.append(f"{f['label']} (options: {f['options'][:6]})")
            else:
                el.fill(ans)
        except Exception as e:
            if f["required"]:
                unanswered.append(f"{f['label']} [error: {e.__class__.__name__}]")

    for name, group in radio_groups.items():
        if any(g["value"] for g in group):
            continue
        question = group[0]["label"].split(" :: ")[0]
        labels = [g["label"].split(" :: ")[-1] for g in group]
        if re.search(r"cover letter", question + " ".join(labels), re.I) and group[0]["type"] == "radio":
            neg = r"don.?t|do not|no cover|skip|without"
            if has_cl:
                choice = [g for g, lab in zip(group, labels) if re.search(r"write|type", lab, re.I) and not re.search(neg, lab, re.I)]
            else:
                choice = [g for g, lab in zip(group, labels) if re.search(neg, lab, re.I)]
            if choice:
                page.locator(f'[data-aa-idx="{choice[0]["idx"]}"]').check(force=True)
            continue
        if re.search(r"r[eé]sum[eé]|\bcv\b", question, re.I) and group[0]["type"] == "radio":
            page.locator(f'[data-aa-idx="{group[0]["idx"]}"]').check(force=True)  # most recent resume
            continue
        ans = answer_for(question, book)
        if group[0]["type"] == "checkbox" and len(group) == 1:
            # single checkbox: consent / declaration boxes
            if re.search(r"agree|consent|confirm|declare|acknowledge|privacy", question, re.I):
                page.locator(f'[data-aa-idx="{group[0]["idx"]}"]').check(force=True)
            continue
        if ans is None:
            if any(g["required"] for g in group) or len(group) > 1:
                unanswered.append(question)
            continue
        opt = _pick_option(labels, ans)
        if opt:
            g = group[labels.index(opt)]
            page.locator(f'[data-aa-idx="{g["idx"]}"]').check(force=True)
        else:
            unanswered.append(f"{question} (options: {labels[:6]})")
    return unanswered
