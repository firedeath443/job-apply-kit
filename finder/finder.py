"""Job finder: searches job boards and employer career sites for the jobs in me/config.json, scores each one
for this applicant, and keeps everything in me/jobs.db. Runs on your own computer and costs no AI tokens.

  python finder/finder.py run                search everything, score, top up the shortlist
  python finder/finder.py run --sources himalayas,remotive     only these sources (for testing)
  python finder/finder.py today [N]          the top N jobs to apply to today, in a few short lines
  python finder/finder.py show <bucket>      list a bucket: shortlist, apply, maybe, skipped, skip, filled, blocked, applied
  python finder/finder.py decide <key> <shortlist|skip|filled|blocked|applied|undo> [reason]
  python finder/finder.py sync <inbox dir>   apply what was tapped on the dashboard (see DAILY-APPLY.md)
  python finder/finder.py feed               write me/feed.json for the dashboard
  python finder/finder.py status             how each source did last run

Filtering is deliberately loose. Jobs the applicant can't realistically get are not thrown away: they land in
"skipped" with the reason, so a bad rule can be spotted and fixed in me/config.json.
Sources with no key: Lever, Greenhouse, Ashby, Workday and BambooHR career sites, GovernmentJobs, Himalayas,
Jobicy, Remotive, plus Indeed, LinkedIn and Glassdoor through python-jobspy.
"""
import html, json, os, re, shutil, sqlite3, sys, time, traceback
import urllib.parse, urllib.request
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ME = Path(os.environ.get("JOB_KIT_ME", ROOT / "me"))
DB = ME / "jobs.db"
UA = "Mozilla/5.0 (job-finder; personal use)"
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/130.0 Safari/537.36")
if __name__ == "__main__" and not (ME / "config.json").exists():
    sys.exit(f"No {ME / 'config.json'} yet. Open this folder in Claude and say: set me up.")
CFG = json.loads((ME / "config.json").read_text(encoding="utf-8")) if (ME / "config.json").exists() else {}
WHERE, TARGET = CFG.get("where", {}), CFG.get("target", {})


def cfg_source(name, default=None):
    return CFG.get("sources", {}).get(name, default)


def terms():
    return TARGET.get("search_terms", [])


def wants_remote():
    return WHERE.get("remote", True)


def wants_local():
    return WHERE.get("local", True)


def words(items):
    """A regex matching any of these plain words or phrases (or regexes, which pass through)."""
    return re.compile(r"\b(" + "|".join(items) + r")\b", re.I) if items else None


# ---------- which jobs to keep ----------
TITLE_INCLUDE = words(TARGET.get("title_include", []))
TITLE_EXCLUDE = words(TARGET.get("title_exclude", []))
CLOSE, MID = words(WHERE.get("close_towns", [])), words(WHERE.get("mid_towns", []))
STATE_ABBR, STATE_NAME = CFG.get("home", {}).get("state", ""), CFG.get("home", {}).get("state_name", "")
HOME_STATE = re.compile(rf"\b({re.escape(STATE_ABBR)}|{re.escape(STATE_NAME)})\b") if STATE_ABBR else None
ALL_STATES = ("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND "
              "OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY").split()
OTHER_STATE = re.compile(r",\s*(" + "|".join(s for s in ALL_STATES if s != STATE_ABBR) + r")\b")
METROS = [dict(m, rx=re.compile(m["pattern"], re.I)) for m in WHERE.get("extra_metros", [])]
REMOTE = re.compile(r"\bremote\b", re.I)
US_OK = re.compile(r"\b(US|USA|U\.S\.|United States|North America|Americas|Worldwide|Anywhere)\b", re.I)
FOREIGN = re.compile(r"\b(Canada|India|Philippines|Mexico|Costa Rica|UK|United Kingdom|Ireland|Poland|Europe|EMEA|APAC|"
                     r"Brazil|Colombia|Argentina|LATAM|Latin America|Pakistan|Nigeria|Kenya|South Africa|Vietnam|"
                     r"Australia|Germany|Spain|Portugal)\b", re.I)


def is_local(loc):
    if not HOME_STATE:
        return False
    if HOME_STATE.search(loc):
        return True
    near = (CLOSE and CLOSE.search(loc)) or (MID and MID.search(loc))
    return bool(near and not OTHER_STATE.search(loc))


def classify(title, location):
    """Return a tag ('Local', 'Remote', or an extra metro's name) if the job is worth storing, else None."""
    title, loc = title or "", location or ""
    if not TITLE_INCLUDE or not TITLE_INCLUDE.search(title) or (TITLE_EXCLUDE and TITLE_EXCLUDE.search(title)):
        return None
    if FOREIGN.search(title) and not US_OK.search(title):
        return None
    if FOREIGN.search(loc) and not US_OK.search(loc):
        return None
    if (REMOTE.search(loc) or REMOTE.search(title)) and wants_remote():
        return "Remote"
    if is_local(loc):
        return "Local" if wants_local() else None
    for m in METROS:
        if m["rx"].search(loc):
            return m["name"]
    return None


def home_tier(loc):
    if CLOSE and CLOSE.search(loc):
        return "close"
    if MID and MID.search(loc):
        return "mid"
    town = loc.split(",")[0].strip().lower()
    if town in (STATE_ABBR.lower(), STATE_NAME.lower(), "united states", "us", "usa", ""):
        return "state"  # state only, town unknown
    return "far"


# ---------- http ----------


def get(url, data=None, headers=None, timeout=25, proxy=None, browser=False):
    h = {"User-Agent": BROWSER_UA if browser else UA, "Accept": "application/json, text/html"}
    h.update(headers or {})
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=h)
    opener = (urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
              if proxy else urllib.request.build_opener())
    with opener.open(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def text_of(s):
    s = re.sub(r"(?i)<(br|/p|/li|/div|/h\d)[^>]*>", "\n", s or "")
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n", s).strip()[:20000]


def ms_date(ms):
    try:
        return datetime.fromtimestamp(int(ms) / 1000).date().isoformat()
    except (TypeError, ValueError):
        return None


def job(**kw):
    base = dict(description="", salary_min=None, salary_max=None, posted=None, job_type="", detail=None)
    base.update(kw)
    return base


# ---------- fetchers: each returns a list of job dicts ----------
def fetch_lever(src):
    out = []
    for p in json.loads(get(f"https://api.lever.co/v0/postings/{src['slug']}?mode=json")):
        cats = p.get("categories", {})
        loc = ", ".join(filter(None, [cats.get("location"), cats.get("commitment"), p.get("workplaceType")]))
        desc = "\n".join([p.get("descriptionPlain", "")] +
                         [f"{l.get('text', '')}\n{text_of(l.get('content', ''))}" for l in p.get("lists", [])] +
                         [p.get("additionalPlain", "")])
        sal = p.get("salaryRange") or {}
        out.append(job(id=f"lever:{p['id']}", company=src["name"], title=p.get("text", ""), location=loc,
                       url=p.get("hostedUrl", ""), description=desc[:20000], posted=ms_date(p.get("createdAt")),
                       salary_min=sal.get("min"), salary_max=sal.get("max"), job_type=cats.get("commitment", "")))
    return out


def fetch_greenhouse(src):
    data = json.loads(get(f"https://boards-api.greenhouse.io/v1/boards/{src['slug']}/jobs?content=true"))
    return [job(id=f"gh:{j['id']}", company=src["name"], title=j.get("title", ""),
                location=(j.get("location") or {}).get("name", ""), url=j.get("absolute_url", ""),
                description=text_of(html.unescape(j.get("content", ""))),
                posted=(j.get("first_published") or j.get("updated_at") or "")[:10] or None)
            for j in data.get("jobs", [])]


def fetch_ashby(src):
    data = json.loads(get(f"https://api.ashbyhq.com/posting-api/job-board/{src['slug']}?includeCompensation=true"))
    out = []
    for j in data.get("jobs", []):
        loc = j.get("location", "") + (" (Remote)" if j.get("isRemote") else "")
        out.append(job(id=f"ashby:{j.get('id')}", company=src["name"], title=j.get("title", ""), location=loc,
                       url=j.get("jobUrl", ""), description=(j.get("descriptionPlain") or "")[:20000],
                       posted=(j.get("publishedAt") or "")[:10] or None, job_type=j.get("employmentType", "")))
    return out


def workday_urls(src):
    """Workday boards come in two URL shapes; return (api_base, public_base)."""
    if src.get("host") == "myworkdaysite":
        root = f"https://wd{src['wd']}.myworkdaysite.com"
        return f"{root}/wday/cxs/{src['tenant']}/{src['site']}", f"{root}/recruiting/{src['tenant']}/{src['site']}"
    root = f"https://{src['tenant']}.wd{src['wd']}.myworkdayjobs.com"
    return f"{root}/wday/cxs/{src['tenant']}/{src['site']}", f"{root}/{src['site']}"


def fetch_workday(src):
    api, public = workday_urls(src)
    out, seen = [], set()
    for term in terms()[:4]:
        data = json.loads(get(f"{api}/jobs", data={"limit": 20, "offset": 0, "searchText": term, "appliedFacets": {}}))
        for j in data.get("jobPostings", []):
            path = j.get("externalPath", "")
            if path in seen:
                continue
            seen.add(path)
            out.append(job(id=f"wd:{src['tenant']}:{path}", company=src["name"], title=j.get("title", ""),
                           location=j.get("locationsText", ""), url=f"{public}{path}", detail=f"wd:{api}{path}"))
    return out


def fetch_bamboohr(src):
    root = f"https://{src['slug']}.bamboohr.com/careers"
    data = json.loads(get(f"{root}/list"))
    out = []
    for j in data.get("result", []):
        loc = j.get("location") or {}
        where = ", ".join(filter(None, [loc.get("city"), loc.get("state")]))
        if j.get("isRemote") or str(j.get("locationType")) == "1":
            where += " (Remote)"
        out.append(job(id=f"bamboo:{src['slug']}:{j['id']}", company=src["name"], title=j.get("jobOpeningName", ""),
                       location=where, url=f"{root}/{j['id']}", job_type=j.get("employmentStatusLabel") or "",
                       detail=f"bamboo:{root}/{j['id']}/detail"))
    return out


def fetch_governmentjobs(cfg):
    out, seen = [], set()
    item = re.compile(r'<li class="job-item"[^>]*data-job-id="([^"]+)".*?class="job-details-link" href="([^"]+)">(.*?)</a>'
                      r'.*?job-organization">(.*?)</div>.*?job-location">(.*?)</span>', re.S)
    for kw in cfg["keywords"]:
        q = urllib.parse.urlencode({"keyword": kw, "location": cfg["location"], "distance": cfg["distance"],
                                    "sort": "date", "isDescendingSort": "True"})
        page = get(f"https://www.governmentjobs.com/jobs?{q}", headers={"Accept": "text/html"})
        for jid, href, title, org, loc in item.findall(page):
            if jid in seen:
                continue
            seen.add(jid)
            url = "https://www.governmentjobs.com" + href
            out.append(job(id=f"gj:{jid}", company=html.unescape(org.strip()), title=html.unescape(title.strip()),
                           location=html.unescape(loc.strip()), url=url, detail=f"ldjson:{url}"))
    return out


def fetch_himalayas():
    out, seen = [], set()
    for term in terms()[:6]:
        cursor = None
        for _ in range(3):
            q = {"q": term, "country": "US", "limit": 20}
            if cursor:
                q["cursor"] = cursor
            data = json.loads(get("https://himalayas.app/jobs/api/search?" + urllib.parse.urlencode(q)))
            for j in data.get("jobs", []):
                where = ", ".join(j.get("locationRestrictions") or []) or "Worldwide"
                if j.get("guid") in seen or not US_OK.search(where):
                    continue
                seen.add(j.get("guid"))
                out.append(job(id=f"himalayas:{j.get('guid')}", company=j.get("companyName", ""),
                               title=j.get("title", ""), location=f"Remote ({where})",
                               url=j.get("applicationLink") or j.get("guid", ""),
                               description=text_of(j.get("description", "")),
                               salary_min=j.get("minSalary"), salary_max=j.get("maxSalary"),
                               posted=ms_date(j["pubDate"] * 1000) if isinstance(j.get("pubDate"), (int, float)) else None,
                               job_type=j.get("employmentType") or ""))
            cursor = data.get("nextCursor")
            if not cursor:
                break
    return out


def fetch_jobicy():
    data = json.loads(get("https://jobicy.com/api/v2/remote-jobs?count=50&geo=usa&industry=" + urllib.parse.quote(cfg_source("jobicy_industry", ""))))
    return [job(id=f"jobicy:{j['id']}", company=j.get("companyName", ""), title=html.unescape(j.get("jobTitle", "")),
                location=f"Remote ({j.get('jobGeo', 'USA')})", url=j.get("url", ""),
                description=text_of(j.get("jobDescription", "")), salary_min=j.get("annualSalaryMin"),
                salary_max=j.get("annualSalaryMax"), posted=(j.get("pubDate") or "")[:10] or None,
                job_type=", ".join(j.get("jobType") or []))
            for j in data.get("jobs", [])]


def fetch_remotive():
    out, seen = [], set()
    for term in terms()[:4]:
        data = json.loads(get("https://remotive.com/api/remote-jobs?" + urllib.parse.urlencode({"search": term})))
        for j in data.get("jobs", []):
            where = j.get("candidate_required_location") or "Worldwide"
            if j["id"] in seen or not US_OK.search(where):
                continue
            seen.add(j["id"])
            out.append(job(id=f"remotive:{j['id']}", company=j.get("company_name", ""), title=j.get("title", ""),
                           location=f"Remote ({where})", url=j.get("url", ""),
                           description=text_of(j.get("description", "")) + "\n" + (j.get("salary") or ""),
                           posted=(j.get("publication_date") or "")[:10] or None, job_type=j.get("job_type") or ""))
    return out


def _jobspy(site, search_terms, remote_terms=(), **extra):
    from jobspy import scrape_jobs  # heavy import; only when this source runs

    def val(v):
        return "" if v is None or (isinstance(v, float) and v != v) else str(v)

    def num(v):
        try:
            f = float(v)
            return None if f != f else f
        except (TypeError, ValueError):
            return None

    out, seen, errors = [], set(), []
    proxy, results = cfg_source("proxy"), cfg_source("results_per_search", 30)
    searches = [(t, {"location": CFG["home"]["search_location"], "distance": CFG["where"].get("radius_miles", 40)})
                for t in search_terms] if wants_local() else []
    searches += [(t, {"location": CFG["home"].get("country", "United States"), "is_remote": True})
                 for t in remote_terms] if wants_remote() else []
    for term, where in searches:
        try:
            df = scrape_jobs(site_name=[site], search_term=term, results_wanted=results, hours_old=cfg_source("hours_old", 168),
                             country_indeed=CFG["home"].get("country_indeed", "USA"), proxies=[proxy] if proxy else None, verbose=0, **where, **extra)
        except Exception as e:  # one bad search shouldn't lose the rest
            errors.append(f"{term}: {e}")
            continue
        for r in df.to_dict("records"):
            jid = val(r.get("id")) or val(r.get("job_url"))
            if not jid or jid in seen:
                continue
            seen.add(jid)
            loc = val(r.get("location"))
            if r.get("is_remote") == True or where.get("is_remote"):  # noqa: E712 (numpy bool)
                loc = f"Remote ({loc or 'US'})"
            lo, hi, interval = num(r.get("min_amount")), num(r.get("max_amount")), val(r.get("interval"))
            mult = {"hourly": 2080, "daily": 260, "weekly": 52, "monthly": 12}.get(interval, 1)
            url = val(r.get("job_url"))
            detail = None
            if site == "linkedin":
                m = re.search(r"/jobs/view/(\d+)", url)
                detail = f"li:{m.group(1)}" if m else None
            out.append(job(id=f"{site}:{jid}", company=val(r.get("company")), title=val(r.get("title")),
                           location=loc, url=val(r.get("job_url_direct")) or url, alt_url=url,
                           description=val(r.get("description"))[:20000],
                           salary_min=lo * mult if lo else None, salary_max=hi * mult if hi else None,
                           posted=val(r.get("date_posted"))[:10] or None, job_type=val(r.get("job_type")),
                           detail=detail))
        time.sleep(10 if site == "linkedin" else 3)  # LinkedIn rate-limits quickly
    if errors and not out:
        raise RuntimeError("; ".join(errors)[:300])
    return out


# ---------- full descriptions for sources whose search results don't include one ----------
def fetch_detail(detail):
    """Return (description, salary_min, salary_max, posted) for a stored detail pointer."""
    kind, _, target = detail.partition(":")
    if kind == "wd":
        info = json.loads(get(target)).get("jobPostingInfo", {})
        return text_of(info.get("jobDescription", "")) + "\n" + (info.get("timeType") or ""), None, None, \
            (info.get("startDate") or "")[:10] or None
    if kind == "bamboo":
        jo = json.loads(get(target)).get("result", {}).get("jobOpening", {})
        return (text_of(jo.get("description", "")) + "\n" + (jo.get("compensation") or "") + "\n" +
                (jo.get("minimumExperience") or "")), None, None, (jo.get("datePosted") or "")[:10] or None
    if kind == "li":
        page = get(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{target}", proxy=cfg_source("proxy"), browser=True,
                   headers={"Accept": "text/html"})
        m = re.search(r'show-more-less-html__markup[^>]*>(.*?)</div>', page, re.S)
        pay = re.search(r'compensation__salary[^>]*>(.*?)<', page, re.S)
        desc = text_of(m.group(1)) if m else ""
        return desc + ("\nPay: " + text_of(pay.group(1)) if pay else ""), None, None, None
    if kind == "ldjson":  # pages that publish schema.org JobPosting data (GovernmentJobs and others)
        page = get(target, browser=True, headers={"Accept": "text/html"})
        for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page, re.S):
            try:
                d = json.loads(block, strict=False)
            except ValueError:
                continue
            for item in d if isinstance(d, list) else [d]:
                if isinstance(item, dict) and item.get("@type") == "JobPosting":
                    v = ((item.get("baseSalary") or {}).get("value") or {})
                    unit = str(v.get("unitText", "YEAR")).upper()
                    mult = {"HOUR": 2080, "WEEK": 52, "MONTH": 12}.get(unit, 1)
                    lo = v.get("minValue") or v.get("value")
                    hi = v.get("maxValue") or v.get("value")
                    return (text_of(item.get("description", "")), float(lo) * mult if lo else None,
                            float(hi) * mult if hi else None, (item.get("datePosted") or "")[:10] or None)
        return "", None, None, None
    return "", None, None, None


def enrich(con, limit=80, linkedin_limit=15):
    """Newest first, capped per run: the rest get their descriptions on later days."""
    rows = con.execute("""SELECT id, detail, tag, location FROM jobs WHERE detail IS NOT NULL
                          AND COALESCE(description,'')='' AND COALESCE(detail_tries,0) < 3
                          ORDER BY first_seen DESC""").fetchall()
    done = li = 0
    li_blocked = False
    for jid, detail, _, _ in rows:
        if done >= limit:
            break
        is_li = detail.startswith("li:")
        if is_li:
            if li_blocked or li >= linkedin_limit:
                continue
            li += 1
        done += 1
        try:
            desc, lo, hi, posted = fetch_detail(detail)
            con.execute("""UPDATE jobs SET description=?, salary_min=COALESCE(salary_min,?), salary_max=COALESCE(salary_max,?),
                           posted=COALESCE(posted,?), detail_tries=COALESCE(detail_tries,0)+1 WHERE id=?""",
                        (desc[:20000], lo, hi, posted, jid))
        except Exception as e:
            print(f"detail failed {jid}: {e}", flush=True)
            if is_li and "429" in str(e):
                li_blocked = True  # LinkedIn is rate-limiting; try the rest tomorrow (don't count this try)
            else:
                con.execute("UPDATE jobs SET detail_tries=COALESCE(detail_tries,0)+1 WHERE id=?", (jid,))
        con.commit()
        time.sleep(5 if is_li else 0.5)
    return done


# ---------- employer discovery: jobs that link to a readable career site add that site ----------
ATS_PATTERNS = [
    ("workday", re.compile(r"https://([\w-]+)\.wd(\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([\w-]+)/job/")),
    ("workday_site", re.compile(r"https://wd(\d+)\.myworkdaysite\.com/(?:[a-z]{2}-[A-Z]{2}/)?recruiting/([\w-]+)/([\w-]+)/")),
    ("greenhouse", re.compile(r"https://(?:boards|job-boards)\.greenhouse\.io/([\w-]+)/jobs/")),
    ("lever", re.compile(r"https://jobs\.lever\.co/([\w.-]+)/")),
    ("ashby", re.compile(r"https://jobs\.ashbyhq\.com/([\w.%-]+)/")),
    ("bamboohr", re.compile(r"https://([\w-]+)\.bamboohr\.com/careers")),
]


def discover(con, cfg):
    known = {(k, json.dumps(s, sort_keys=True)) for k in ("lever", "greenhouse", "ashby", "workday", "bamboohr")
             for s in cfg.get(k, [])}
    added = 0
    for company, url in con.execute("SELECT company, url FROM jobs WHERE tag='Local'").fetchall():
        for kind, rx in ATS_PATTERNS:
            m = rx.match(url or "")
            if not m:
                continue
            if kind == "workday":
                src, kind = {"tenant": m.group(1), "wd": int(m.group(2)), "site": m.group(3)}, "workday"
            elif kind == "workday_site":
                src, kind = {"tenant": m.group(2), "wd": int(m.group(1)), "site": m.group(3),
                             "host": "myworkdaysite"}, "workday"
            else:
                src = {"slug": m.group(1)}
            key = f"{kind}:{json.dumps(src, sort_keys=True)}"
            if any(k == kind and all(json.loads(s).get(f) == v for f, v in src.items()) for k, s in known):
                break
            src["name"] = company or src.get("slug") or src.get("tenant")
            cur = con.execute("INSERT OR IGNORE INTO employers VALUES (?,?,?,?,?)",
                              (key, kind, json.dumps(src), company, now_iso()))
            added += cur.rowcount
            break
    con.commit()
    return added


# A job that REQUIRES a language the applicant doesn't speak is dropped entirely. "Preferred" doesn't count.
LANGS = (r"(Spanish|Mandarin|Chinese|Cantonese|Korean|Japanese|Turkish|French|German|Portuguese|Italian|Russian|"
         r"Polish|Hebrew|Yiddish|Arabic|Hindi|Vietnamese|Tagalog|Filipino|Creole|Greek|Ukrainian|Dutch|Hungarian|"
         r"Romanian|Gujarati|Punjabi|Urdu|Bengali|Farsi|Persian|Armenian|Thai|Indonesian|Malay|Swedish|Danish|"
         r"Norwegian|Finnish|Czech|Albanian|Serbian|Croatian|Bulgarian|Hmong|Somali|Amharic|Swahili)")
LANG_TITLE = re.compile(rf"\b(bilingual|multilingual|trilingual)\b|\b{LANGS}\b[ -]*(speak\w*|fluen\w*|required)?|"
                        rf"\bspeak\w*\s+{LANGS}\b", re.I)
LANG_DESC = re.compile(
    rf"\b(fluen\w*|proficien\w*|bilingual|speak\w*|read\w*|writ\w*|command)\b[^.;\n]{{0,40}}\b{LANGS}\b[^.;\n]{{0,60}}"
    rf"\b(required|requirement|must|mandatory|essential|necessary)\b|"
    rf"\b(required|must|mandatory|essential)\b[^.;\n]{{0,40}}\b(fluen\w*|proficien\w*|bilingual|speak\w*)\b[^.;\n]{{0,30}}"
    rf"\b{LANGS}\b|\bbilingual\b[^.;\n]{{0,20}}\b(required|a must|mandatory)\b", re.I)
LANG_SOFT = re.compile(r"\b(prefer\w*|a plus|plus\b|nice to have|desir\w*|bonus|advantage|helpful|not required)\b", re.I)


def language_required(title, desc):
    """Quote of a hard second-language requirement, or None."""
    m = LANG_TITLE.search(title or "")
    if m:
        return m.group(0).strip()
    for m in LANG_DESC.finditer(desc or ""):
        start = (desc.rfind(".", 0, m.start()) + 1)
        end = desc.find(".", m.end())
        sentence = desc[start:end if end > 0 else len(desc)]
        if not LANG_SOFT.search(sentence):
            return m.group(0).strip()[:120]
    return None


NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
YEARS = re.compile(r"\b(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\b(?:\s*\(\d{1,2}\))?\s*"
                   r"(?:\+|plus|or more)?\s*(?:(?:-|–|to)\s*(?:\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)"
                   r"\s*)?\+?\s*years?\b", re.I)
NOT_REQUIREMENT = re.compile(r"\b(in lieu|substitut\w*|has been|have been|for over|founded|history|serving|"
                             r"years? old|anniversary|tenure|vesting|per year|each year)\b|"
                             r"\b(has|have|with) (over |more than )?\d+ years (of )?(experience )?(serving|in business)|"
                             r"\bover \d+ years\b|"
                             # "a degree or 5 years": an alternative to the degree
                             r"degree[^.;\n]{0,60}\bor\b|\bor\b[^.;\n]{0,60}degree", re.I)


PREFERRED = re.compile(r"prefer|a plus|ideal|desir|nice to have|bonus|helpful|advantage", re.I)


def norm(s):
    s = re.sub(r"\b(inc|llc|l\.l\.c|llp|corp|corporation|co|ltd|lp|the|company)\b\.?", " ", (s or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def dedupe_key(company, title, tag, location):
    town = "remote" if tag == "Remote" else norm((location or "").split(",")[0])
    return f"{norm(company)}|{norm(title)}|{town}"


def sentences(text):
    return [s.strip() for s in re.split(r"[\n.;•]+(?=\s|$)|\n", text or "") if s.strip()]


def years_asked(desc):
    """(required_min, preferred_min, quote). Uses the smallest required number so a rule like
    '5 years, or 2 years with a degree' never skips a job the applicant could get."""
    req, pref = [], []
    for s in sentences(desc):
        if "experience" not in s.lower() or NOT_REQUIREMENT.search(s):
            continue
        for m in YEARS.finditer(s):
            n = m.group(1).lower()
            n = NUM.get(n, None) if not n.isdigit() else int(n)
            if not n or n > 15:
                continue
            (pref if PREFERRED.search(s) else req).append((n, s[:180]))
    r = min(req) if req else None
    p = min(pref) if pref else None
    return (r[0] if r else None), (p[0] if p else None), (r or p or (None, ""))[1]


MONEY = r"\$\s?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*([kK])?"
PAY_RANGE = re.compile(MONEY + r"\s*(?:-|–|—|to)\s*" + MONEY + r"(?:[^.\n]{0,25}?\b(hour|hr|hourly|year|yr|annual))?", re.I)
PAY_HOURLY = re.compile(MONEY + r"\s*(?:per|an|/)\s*(?:hour|hr)\b", re.I)


def parse_pay(desc):
    def val(n, k):
        return float(n.replace(",", "")) * (1000 if k else 1)
    m = PAY_RANGE.search(desc or "")
    if m:
        lo, hi = val(m.group(1), m.group(2)), val(m.group(3), m.group(4))
        if (m.group(5) or "").lower().startswith(("hour", "hr")) or hi < 200:
            lo, hi = lo * 2080, hi * 2080
        if 25000 <= lo <= hi <= 250000:
            return lo, hi
    m = PAY_HOURLY.search(desc or "")
    if m:
        v = val(m.group(1), m.group(2)) * 2080
        if 25000 <= v <= 250000:
            return v, v
    return None, None


# Work arrangement (for the In person / Hybrid / Remote filter). Job sites often file hybrid jobs under
# "remote", so a remote listing only becomes hybrid on a clear statement (title, location, "Work Location:").
WORK_LOC = re.compile(r"\b(work location|location type|workplace type|work model|work arrangement|"
                      r"flexible work arrangements|location)\W{0,6}(in[- ]person|on-?site|hybrid|remote)", re.I)
HYBRID_REMOTE_IN = re.compile(r"\bhybrid remote in ([^\n.]{3,40})", re.I)
HYBRID_DESC = re.compile(
    r"\bhybrid\b[^.\n]{0,30}\b(role|position|schedule|work|working|environment|model|arrangement|flexibility|"
    r"opportunity|setting|basis|options?|policy)\b|\(hybrid\)|#LI-Hybrid|\|\s*hybrid\b|\bhybrid\s*[:,]\s*\d|"
    r"\b(is|as) (a |an )?hybrid\b|\b\d\s*(\(\d\) )?days?( per| a|/)? ?week (in|at) (the |our )?office", re.I)
NOT_HYBRID = re.compile(r"\bnot (eligible for |a |an )?(fully )?(hybrid|remote)|\bno (remote|hybrid)\b|"
                        r"\b(remote|hybrid) (work )?(is )?not (available|offered|an option)", re.I)
ONSITE_DESC = re.compile(r"\b(on-?site|in[- ]office|in[- ]person)\b[^.\n]{0,25}\b(role|position|job|schedule|"
                         r"required|requirement|daily|five|5|full[- ]time)\b|#LI-Onsite|\bfully in[- ]office\b", re.I)
REMOTE_SAID = re.compile(r"\bremote\b|\b(can|to|will|may|ability to|option to) work from home\b|"
                         r"\bwork[- ]from[- ]home (position|role|job|opportunity|schedule)\b|\bwfh\b|telecommut|"
                         r"work from anywhere", re.I)


def arrangement(title, loc, desc, tag, filtered=False):
    """('remote'|'hybrid'|'onsite', stated?, place-if-hybrid-listed-as-remote).
    filtered: the "remote" label came only from a search filter (LinkedIn), not from the listing itself."""
    head = f"{title} {loc}"
    place = re.sub(r"^Remote \((.*)\)$", r"\1", loc)
    field = WORK_LOC.search(desc)
    field = field.group(2).lower().replace("-", " ") if field else ""
    if re.search(r"\bhybrid\b", head, re.I) or field == "hybrid" or HYBRID_REMOTE_IN.search(desc):
        m = HYBRID_REMOTE_IN.search(desc)
        return "hybrid", True, m.group(1) if m else place
    if re.search(r"\b(on-?site|in[- ]person)\b", loc, re.I) or field in ("in person", "on site", "onsite"):
        return "onsite", True, None
    if tag == "Remote" and filtered and field != "remote":
        # LinkedIn's remote filter lets on-site jobs through (2026-10-21: 7 of 8 auto-picks were on-site or hybrid),
        # so a LinkedIn-only "remote" job counts as remote only once its own text says so.
        if NOT_HYBRID.search(desc):
            return "onsite", True, None
        if HYBRID_DESC.search(desc) or re.search(r"\bhybrid location\b", desc, re.I):
            return "hybrid", True, place
        if not REMOTE_SAID.search(f"{title} {place} {desc}"):
            if not desc.strip():
                return "remote", False, None  # no description yet: shows as "Remote?"
            return "onsite", bool(ONSITE_DESC.search(desc)), None
    if tag == "Remote" or field == "remote":
        return "remote", True, None
    if NOT_HYBRID.search(desc):
        return "onsite", True, None
    if HYBRID_DESC.search(desc):
        return "hybrid", True, None
    if ONSITE_DESC.search(desc):
        return "onsite", True, None
    return "onsite", False, None  # nothing said either way; most of these are in person


# ---------- searches on the big boards: small on purpose, so a home connection doesn't get blocked ----------
def fetch_indeed():
    return _jobspy("indeed", terms()[:6], remote_terms=terms()[:4])


def fetch_linkedin():
    return _jobspy("linkedin", terms()[:4], remote_terms=terms()[:2])


def fetch_glassdoor():
    return _jobspy("glassdoor", terms()[:3])


# ---------- storage ----------
def db():
    ME.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB, timeout=30)
    con.execute("""CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, source TEXT, company TEXT, title TEXT,
                   location TEXT, tag TEXT, url TEXT, first_seen TEXT, last_seen TEXT, description TEXT, salary_min REAL,
                   salary_max REAL, posted TEXT, job_type TEXT, detail TEXT, detail_tries INTEGER, alt_url TEXT)""")
    con.execute("CREATE TABLE IF NOT EXISTS runs (source TEXT PRIMARY KEY, at TEXT, status TEXT, found INTEGER, kept INTEGER)")
    con.execute("""CREATE TABLE IF NOT EXISTS decisions (key TEXT PRIMARY KEY, decision TEXT, reason TEXT, at TEXT,
                   title TEXT, company TEXT)""")
    con.execute("CREATE TABLE IF NOT EXISTS employers (key TEXT PRIMARY KEY, kind TEXT, src TEXT, company TEXT, added TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS synced (id TEXT PRIMARY KEY, at TEXT)")
    return con


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def run_all(only=None):
    con, now = db(), now_iso()
    discover(con, CFG.get("employers", {}))
    fetchers = {"lever": fetch_lever, "greenhouse": fetch_greenhouse, "ashby": fetch_ashby,
                "workday": fetch_workday, "bamboohr": fetch_bamboohr}
    todo = []
    for kind, fn in fetchers.items():
        for src in CFG.get("employers", {}).get(kind, []):
            todo.append((f"{kind}:{src['name']}", lambda s=src, f=fn: f(s)))
    for kind, src in con.execute("SELECT kind, src FROM employers ORDER BY added").fetchall():
        s = json.loads(src)
        todo.append((f"found:{kind}:{s['name']}", lambda s=s, f=fetchers[kind]: f(s)))
    gov = {"keywords": terms()[:5], "location": CFG["home"]["search_location"], "distance": WHERE.get("radius_miles", 40)}
    boards = {"governmentjobs": lambda: fetch_governmentjobs(gov), "himalayas": fetch_himalayas, "jobicy": fetch_jobicy,
              "remotive": fetch_remotive, "indeed": fetch_indeed, "linkedin": fetch_linkedin, "glassdoor": fetch_glassdoor}
    for name, fn in boards.items():
        if cfg_source(name, True) is False:
            continue
        if name == "jobicy" and not cfg_source("jobicy_industry"):
            continue
        todo.append((name, fn))
    if only:
        todo = [t for t in todo if t[0] in only]
    for name, fn in todo:
        try:
            jobs = fn()
            kept = 0
            for j in jobs:
                tag = classify(j["title"], j["location"])
                if not tag:
                    continue
                kept += 1
                con.execute("""INSERT INTO jobs (id, source, company, title, location, tag, url, first_seen, last_seen,
                                 description, salary_min, salary_max, posted, job_type, detail, detail_tries, alt_url)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?)
                               ON CONFLICT(id) DO UPDATE SET last_seen=excluded.last_seen, title=excluded.title,
                               location=excluded.location, tag=excluded.tag, url=excluded.url,
                               description=COALESCE(NULLIF(excluded.description,''), jobs.description),
                               salary_min=COALESCE(excluded.salary_min, jobs.salary_min),
                               salary_max=COALESCE(excluded.salary_max, jobs.salary_max),
                               posted=COALESCE(jobs.posted, excluded.posted),
                               job_type=COALESCE(NULLIF(excluded.job_type,''), jobs.job_type),
                               detail=COALESCE(excluded.detail, jobs.detail),
                               alt_url=COALESCE(excluded.alt_url, jobs.alt_url)""",
                            (j["id"], name, j["company"], j["title"], j["location"], tag, j["url"], now, now,
                             j.get("description") or "", j.get("salary_min"), j.get("salary_max"), j.get("posted"),
                             j.get("job_type") or "", j.get("detail"), j.get("alt_url")))
            con.execute("REPLACE INTO runs VALUES (?,?,?,?,?)", (name, now, "ok", len(jobs), kept))
            print(f"{name}: found {len(jobs)}, kept {kept}", flush=True)
        except Exception as e:
            con.execute("REPLACE INTO runs VALUES (?,?,?,?,?)", (name, now, f"error: {e}"[:200], 0, 0))
            print(f"{name}: error {str(e)[:150]}", flush=True)
            traceback.print_exc(file=sys.stderr)
        con.commit()
    try:
        n = enrich(con)
        con.execute("REPLACE INTO runs VALUES (?,?,?,?,?)", ("(full descriptions)", now, "ok", n, n))
        print(f"full descriptions fetched: {n}", flush=True)
    except Exception as e:
        con.execute("REPLACE INTO runs VALUES (?,?,?,?,?)", ("(full descriptions)", now, f"error: {e}"[:200], 0, 0))
    con.commit()
    n = top_up(con)
    con.commit()
    con.close()
    print(f"added to shortlist: {n}", flush=True)


# ---------- scoring ----------
# Hard skips are only for jobs this applicant couldn't realistically get. Everything else is a score.
INTERN = re.compile(r"\b(intern|internship|co-?op)\b", re.I)
LEVEL = re.compile(r"\b(II|III|IV|[234])\b")
TOO_SENIOR = words(TARGET.get("skip_title_words", []))
STRETCH = words(TARGET.get("stretch_title_words", []))
DUTIES = [(n, re.compile(p, re.I)) for n, p in TARGET.get("duties", [])]
UNFAMILIAR = [(n, re.compile(p, re.I)) for n, p in TARGET.get("unfamiliar", [])]
MISSING = [(c, re.compile(rf"\b{c}\b", re.I)) for c in TARGET.get("credentials_missing", [])]
SPOKEN = {s.lower() for s in TARGET.get("languages", ["English"])}
REQUIRED_WORD = re.compile(r"\b(required|must|mandatory|need to hold|must hold|must have)\b", re.I)
AGENCY = re.compile(r"robert half|\bvaco\b|kforce|insight global|aerotek|randstad|adecco|manpower|michael page|\bhays\b|"
                    r"beacon hill|addison group|tandym|kelly services|express employment|spherion|teksystems|jobot|"
                    r"cybercoders|motion recruitment|apex systems|staffing|recruit|personnel|placement|search group", re.I)
AGGREGATORS = re.compile(r"indeed\.com|glassdoor\.com|linkedin\.com|ziprecruiter\.com|himalayas\.app|jobicy\.com|"
                         r"remotive\.com|adzuna|appcast|apptrkr", re.I)
CAPTCHA_ATS = re.compile(r"bamboohr\.com|applytojob\.com|jazzhr|breezy\.hr|indeed\.com", re.I)
PART_TIME = re.compile(r"part[- ]?time", re.I)
TEMP = re.compile(r"\b(temporary|temp|contract|seasonal)\b", re.I)
ENTRY = re.compile(r"entry[- ]level|recent (college )?grad|new grad|no experience (is )?(required|necessary)|"
                   r"\b0\s*(-|–|to)\s*[12]\s*years|\b1\s*(-|–|to)\s*2\s*years", re.I)
BUCKETS = ("shortlist", "filled", "blocked", "applied", "skip")


def load_prefs():
    return CFG.get("learned", {})


def foreign_language_required(title, desc):
    q = language_required(title, desc)
    if q and any(s in q.lower() for s in SPOKEN):
        return None
    return q


def credential_required(desc):
    """The sentence saying a credential the applicant doesn't hold is required, or None."""
    for s in sentences(desc):
        for name, rx in MISSING:
            if rx.search(s) and REQUIRED_WORD.search(s) and not PREFERRED.search(s):
                return name, s[:180]
    return None


def score(j, now, prefs, decision=None):
    """Return (bucket, score, plus-reasons, minus-reasons, skip-reasons, facts)."""
    title, desc, loc, tag = j["title"] or "", j["description"] or "", j["location"] or "", j["tag"]
    company = j["company"] or ""
    plus, minus, skip, facts = [], [], [], {}
    s = 0
    have = TARGET.get("years_experience", 2)
    floor = TARGET.get("min_pay")

    # Things this applicant couldn't realistically get -> Skipped (still listed, with the reason).
    if TOO_SENIOR and TOO_SENIOR.search(title):
        skip.append(f"Title too senior ({TOO_SENIOR.search(title).group(0)})")
    if TARGET.get("skip_internships", True) and INTERN.search(title):
        skip.append("Internship")
    cred = credential_required(desc)
    if cred:
        skip.append(f"{cred[0]} required: “{cred[1]}”")
    req, pref, quote = years_asked(desc)
    facts["years"] = req if req is not None else pref
    if req is not None and req >= have + TARGET.get("years_stretch_limit", 3):
        skip.append(f"Requires {req}+ years: “{quote}”")
    lo, hi = j["salary_min"], j["salary_max"]
    if not lo and not hi:
        lo, hi = parse_pay(desc)
    lo, hi = lo or hi, hi or lo
    facts["pay"] = (lo, hi)
    if floor and hi and hi < floor:
        skip.append(f"Top of pay range ${hi/1000:.0f}K is under your ${floor/1000:.0f}K minimum")
    metro = next((m for m in METROS if m["name"] == tag), None)
    if metro and metro.get("min_pay") and hi and hi < metro["min_pay"]:
        skip.append(f"{tag} under ${metro['min_pay']/1000:.0f}K; your rule")
    if norm(company) in {norm(c) for c in prefs.get("skip_companies", [])}:
        skip.append("Company on your skip list")
    for pat in prefs.get("skip_title_patterns", []):
        if re.search(pat, title, re.I):
            skip.append(f"Title matches your skip rule ({pat})")
    if TARGET.get("full_time_only", True) and PART_TIME.search(title + " " + (j["job_type"] or "")):
        skip.append("Part-time; you asked for full-time")

    # Location
    tier = home_tier(loc) if tag == "Local" else ("metro" if metro else "remote")
    arr, stated, place = arrangement(title, loc, desc, tag, j.get("remote_from_filter", False))
    facts["arr"], facts["arr_stated"] = arr, stated
    hybrid_elsewhere = False
    if tag == "Remote" and arr == "hybrid":
        # Listed as remote but it's hybrid, so where the office is decides the commute.
        if place and is_local(place):
            tier = home_tier(place)
        else:
            hybrid_elsewhere = True
    facts["tier"] = tier
    prefer = WHERE.get("prefer", "either")
    points = {"close": 30, "mid": 20, "state": 15, "far": 8, "remote": 16, "metro": 5}
    if prefer == "remote":
        points.update(remote=30, close=20, mid=14, state=10, far=5)
    pts = points[tier]
    s += pts
    label = {"close": "Close to home", "mid": "A reasonable commute", "state": "In your state (town not listed)",
             "far": "Far from home", "remote": "Remote", "metro": f"{tag} commute"}[tier]
    (plus if pts >= 16 else minus).append(label)
    if hybrid_elsewhere:
        s -= 10; minus.append(f"Listed as remote but says hybrid ({place or 'office not given'})")
    if tag == "Remote" and arr == "onsite":
        town = re.sub(r"^Remote \((.*)\)$", r"\1", loc)
        if "Remote" in plus:
            plus.remove("Remote")
        s -= 10; minus.append(f"Listed as remote, but the posting {'says on-site' if stated else 'never says remote'} "
                              f"({town})")
    elif tag == "Remote" and not stated:
        minus.append("Remote not confirmed yet")

    # Experience asked
    if req is not None:
        if req <= have:
            s += 25; plus.append(f"Asks for {req} yr{'s' if req > 1 else ''}")
        elif req == have + 1:
            s += 15; plus.append(f"Asks for {req} yrs (a small stretch)")
        elif req == have + 2:
            s += 5; minus.append(f"Asks for {req} yrs (a stretch)")
    elif pref is not None:
        if pref <= have + 1:
            s += 20; plus.append(f"{pref} yrs preferred, not required")
        else:
            s += 8; minus.append(f"{pref}+ yrs preferred (not required)")
    elif ENTRY.search(desc) or re.search(r"entry|junior|jr\.?|assistant|coordinator", title, re.I):
        s += 22; plus.append("Entry-level")
    else:
        s += 12
    if STRETCH and STRETCH.search(title):
        s -= 15; minus.append("Senior title (usually more years)")
    lvl = LEVEL.search(title)
    if lvl and TARGET.get("penalize_levels", True):
        drop = {"II": 5, "2": 5, "III": 12, "3": 12}.get(lvl.group(1), 20)
        s -= drop; minus.append(f"Level {lvl.group(1)} title")

    # Duties that match what the applicant has done
    if desc:
        hits = [name for name, rx in DUTIES if rx.search(desc)]
        s += min(25, 5 * len(hits))
        if hits:
            plus.append("Matches: " + ", ".join(hits[:6]))
        unfamiliar = [name for name, rx in UNFAMILIAR if rx.search(desc)]
        if unfamiliar:
            minus.append("Mentions " + ", ".join(unfamiliar) + " (not on your resume)")
    else:
        s += 10; minus.append("No description yet (open the posting)")

    # Pay, against what the applicant asked for
    want = TARGET.get("target_pay") or floor or 60000
    if hi:
        mid = (lo + hi) / 2
        facts["mid"] = mid
        s += 15 if mid >= want else 12 if mid >= want * .85 else 6 if mid >= want * .7 else 0
        (plus if mid >= want * .85 else minus).append(
            f"Pay ${lo/1000:.0f}K–${hi/1000:.0f}K" if lo != hi else f"Pay ${hi/1000:.0f}K")
    else:
        s += 7

    # Freshness: when it was first seen anywhere
    first = j["first_seen"]
    posted = j["posted"] if j["posted"] and j["posted"] <= first[:10] else first[:10]
    age = (now.date() - datetime.fromisoformat(posted[:10]).date()).days
    facts["age"] = age
    s += 10 if age <= 3 else 7 if age <= 7 else 4 if age <= 14 else 0
    if age > 30:
        s -= 5; minus.append(f"Open {age}+ days (may be stale)")

    # Where it comes from / job type
    if j["url"] and not AGGREGATORS.search(j["url"]):
        s += 5; plus.append("Apply on the company's own site")
    if AGENCY.search(company):
        s -= 5; minus.append("Staffing agency (employer hidden)")
    if not TARGET.get("full_time_only", True) and PART_TIME.search(title + " " + (j["job_type"] or "")):
        minus.append("Part-time")
    elif TEMP.search(title + " " + (j["job_type"] or "")):
        s -= 5; minus.append("Temporary/contract")
    if norm(company) in {norm(c) for c in prefs.get("prefer_companies", [])}:
        s += 10; plus.append("Company you liked before")

    if decision in BUCKETS:
        bucket = decision
    elif skip:
        bucket = "skipped"
    elif s >= prefs.get("apply_threshold", 65):
        bucket = "apply"
    else:
        bucket = "maybe"
    return bucket, s, plus, minus, skip, facts


def ranked():
    """All live jobs, deduplicated and scored, best first."""
    con = db()
    con.row_factory = sqlite3.Row
    now = datetime.now().astimezone()
    live = (now - timedelta(days=3)).isoformat()
    rows = con.execute("SELECT * FROM jobs").fetchall()
    decisions = {r["key"]: dict(r) for r in con.execute("SELECT * FROM decisions")}
    con.close()
    prefs = load_prefs()
    groups = {}
    for r in rows:
        groups.setdefault(dedupe_key(r["company"], r["title"], r["tag"], r["location"]), []).append(dict(r))
    out = []
    for key, items in groups.items():
        d = decisions.get(key)
        if not any(r["last_seen"] >= live for r in items) and not (d and d["decision"] in ("applied", "filled", "blocked")):
            continue  # posting is gone and it was never applied to: drop it
        # Prefer the copy with a description and a direct company link; keep the others as extra links.
        items.sort(key=lambda r: (bool(r["description"]), not AGGREGATORS.search(r["url"] or ""), r["first_seen"]),
                   reverse=True)
        best = dict(items[0])
        best["first_seen"] = min(r["first_seen"] for r in items)
        best["posted"] = min((r["posted"] for r in items if r["posted"]), default=None)
        for f in ("salary_min", "salary_max"):
            best[f] = best[f] or next((r[f] for r in items if r[f]), None)
        best["description"] = max((r["description"] or "" for r in items), key=len)
        best["remote_from_filter"] = all(r["id"].startswith("linkedin:") for r in items)
        if (not d or d["decision"] in ("skip", "shortlist")) and foreign_language_required(best["title"], best["description"]):
            continue  # needs a language the applicant doesn't speak
        bucket, s, plus, minus, skip, facts = score(best, now, prefs, d["decision"] if d else None)
        links = []
        for r in items:
            for u in (r["url"], r.get("alt_url")):
                if u and u not in links:
                    links.append(u)
        out.append(dict(key=key, bucket=bucket, score=s, plus=plus, minus=minus, skip=skip, facts=facts,
                        title=best["title"], company=best["company"], location=best["location"], tag=best["tag"],
                        url=best["url"], links=links, first_seen=best["first_seen"], posted=best["posted"],
                        description=best["description"], decision=d,
                        new=best["first_seen"] >= (now - timedelta(hours=26)).isoformat()))
    out.sort(key=lambda j: (-j["score"], j["first_seen"]))
    return out


def set_decision(con, key, decision, reason=""):
    if decision == "undo":
        con.execute("DELETE FROM decisions WHERE key=?", (key,))
        return
    k = key.split("|")
    con.execute("REPLACE INTO decisions VALUES (?,?,?,?,?,?)",
                (key, decision, (reason or "")[:300], now_iso(), k[1] if len(k) > 1 else "", k[0]))


def top_up(con):
    """If the shortlist is short of the daily number, add the best of "apply": never part-time, temp or senior titles.
    With picking "mine", nothing is added: the applicant shortlists on the dashboard."""
    daily = CFG.get("daily", {})
    if daily.get("picking", "auto") != "auto":
        return 0
    jobs = ranked()
    need = daily.get("count", 3) * 2 - sum(1 for j in jobs if j["bucket"] == "shortlist")  # two days' worth to pick from
    pool = [j for j in jobs if j["bucket"] == "apply"
            and not any(m == "Part-time" or m == "Temporary/contract" for m in j["minus"])
            and not (STRETCH and STRETCH.search(j["title"] or ""))]

    def captcha_prone(j):  # these sites usually need a person to tick a CAPTCHA
        return any(CAPTCHA_ATS.search(u or "") for u in j["links"])

    prefer_remote = WHERE.get("prefer") == "remote"
    # A CAPTCHA site counts as 15 points lower: when nobody is home, those jobs can't finish.
    pool.sort(key=lambda j: (prefer_remote and j["facts"].get("arr") != "remote", -(j["score"] - 15 * captcha_prone(j))))
    picks = pool[:max(0, need)]
    for j in picks:
        set_decision(con, j["key"], "shortlist", f"Auto {now_iso()[:10]}: best match")
    return len(picks)


# ---------- what Claude and the dashboard read ----------
def pay_text(j):
    lo, hi = j["facts"].get("pay", (None, None))
    if not hi:
        return "pay not listed"
    return f"${lo/1000:.0f}K-${hi/1000:.0f}K" if lo != hi else f"${hi/1000:.0f}K"


def line(j, with_key=True):
    return " | ".join([j["company"] or "?", j["title"] or "?", j["location"] or "?", pay_text(j), str(j["score"])] +
                      ([j["key"]] if with_key else []))


def card(j):
    d = j["decision"] or {}
    return {"key": j["key"], "title": j["title"], "company": j["company"], "location": j["location"], "pay": pay_text(j),
            "score": j["score"], "arr": j["facts"].get("arr"), "url": j["url"], "new": j["new"], "bucket": j["bucket"],
            "plus": j["plus"][:5], "minus": j["minus"][:4], "skip": j["skip"][:2], "reason": d.get("reason") or "",
            "at": (d.get("at") or "")[:10]}


def feed():
    """The dashboard's one document: small on purpose (no descriptions)."""
    jobs = ranked()
    con = db()
    runs = con.execute("SELECT source, at, status, found, kept FROM runs ORDER BY source").fetchall()
    con.close()
    by = {b: [j for j in jobs if j["bucket"] == b] for b in BUCKETS + ("apply", "maybe", "skipped")}
    out = {"updated": now_iso(),
           "counts": {b: len(v) for b, v in by.items()},
           "shortlist": [card(j) for j in by["shortlist"][:40]],
           "filled": [card(j) for j in by["filled"]],
           "blocked": [card(j) for j in by["blocked"]],
           "applied": sorted((card(j) for j in by["applied"]), key=lambda c: c["at"], reverse=True)[:150],
           "apply": [card(j) for j in by["apply"][:40]],
           "sources": [{"source": r[0], "status": r[2][:60], "found": r[3], "kept": r[4]} for r in runs
                       if not r[0].startswith(("found:", "lever:", "greenhouse:", "ashby:", "workday:", "bamboohr:"))]}
    path = ME / "feed.json"
    path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"{path} ({path.stat().st_size // 1024} KB): " + ", ".join(f"{k} {v}" for k, v in out["counts"].items()))


def sync(inbox):
    """Apply dashboard taps saved by Claude to <inbox>/decisions/*.json, and report answered and open questions."""
    inbox, con, applied = Path(inbox), db(), []
    for f in sorted((inbox / "decisions").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        d = d.get("data", d)
        stamp = f"{f.stem}:{d.get('at')}"
        if not d.get("key") or con.execute("SELECT 1 FROM synced WHERE id=?", (stamp,)).fetchone():
            continue
        set_decision(con, d["key"], d.get("decision"), d.get("reason") or "From the dashboard")
        con.execute("INSERT INTO synced VALUES (?,?)", (stamp, now_iso()))
        applied.append(f"{d.get('decision')}: {d['key']}")
    con.commit()
    # Settings changed on the dashboard go into config.json, which the next steps read.
    sf = next(iter(inbox.glob("state/settings.json")), None)
    if sf:
        v = json.loads(sf.read_text(encoding="utf-8"))
        v = v.get("data", v)
        daily = CFG.setdefault("daily", {})
        daily.update({k: v[k] for k in ("count", "submit", "picking", "paused") if k in v})
        (ME / "config.json").write_text(json.dumps(CFG, indent=2, ensure_ascii=False), encoding="utf-8")
        print("settings: " + json.dumps(daily))
    open_q, answered = {}, []
    for f in sorted((inbox / "questions").glob("*.json")):
        q = json.loads(f.read_text(encoding="utf-8"))
        q = q.get("data", q)
        if q.get("used"):
            continue
        if q.get("answer"):
            answered.append(f"{f.stem} | {q.get('key') or 'GENERAL'} | {q.get('question')} => {q['answer']}")
        else:
            open_q[q.get("key") or ""] = open_q.get(q.get("key") or "", 0) + 1
    print(f"dashboard decisions applied: {len(applied)}")
    print("\n".join(applied))
    print(f"answered questions: {len(answered)}")
    print("\n".join(answered))
    ready = [j for j in ranked() if j["bucket"] == "filled" and j["key"] not in open_q]
    print(f"filled jobs with no open questions left (add to today): {len(ready)}")
    print("\n".join(line(j) for j in ready))
    con.close()
    # The next run reads fresh copies, so something deleted on the dashboard can't come back from an old file.
    for sub in ("decisions", "questions", "state"):
        shutil.rmtree(inbox / sub, ignore_errors=True)


def main():
    args = sys.argv[1:] or ["status"]
    cmd = args[0]
    if cmd == "run":
        only = args[args.index("--sources") + 1].split(",") if "--sources" in args else None
        run_all(only)
    elif cmd == "today":
        n = int(args[1]) if len(args) > 1 else CFG.get("daily", {}).get("count", 3)
        for j in [j for j in ranked() if j["bucket"] == "shortlist"][:n]:
            print(line(j))
    elif cmd == "show":
        jobs = [j for j in ranked() if j["bucket"] == args[1]]
        print(len(jobs))
        for j in jobs[:int(args[2]) if len(args) > 2 else 30]:
            print(line(j))
    elif cmd == "job":  # everything a helper needs about one job, without its description
        j = next(j for j in ranked() if j["key"] == args[1])
        print(json.dumps({k: j[k] for k in ("key", "title", "company", "location", "url", "links", "score", "plus", "minus",
                                            "skip", "bucket")}, indent=1))
    elif cmd == "decide":
        con = db()
        set_decision(con, args[1], args[2], args[3] if len(args) > 3 else "")
        con.commit()
        con.close()
        print("ok")
    elif cmd == "sync":
        sync(args[1])
    elif cmd == "feed":
        feed()
    elif cmd == "status":
        con = db()
        for r in con.execute("SELECT source, status, found, kept, at FROM runs ORDER BY source"):
            print(" | ".join(str(x) for x in r))
        con.close()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
