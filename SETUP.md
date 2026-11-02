# Setup (Claude follows this with the new person)

Take it one step at a time and keep messages short. Ask with AskUserQuestion wherever there are clear options. Do the
technical work yourself; only ask them to click what you can't. Tell them what you're doing in plain words. If something
fails, explain it simply and offer the next-best path. Aim to finish in about 15 minutes. You can stop and resume: check
what exists in `me/` first and pick up where it left off.

## 1. Say what this is, and get their OK
Explain briefly, then ask if they want to continue:
- Every day it searches job boards, picks the best matches, writes a resume for each job, and fills out the application in
  their Chrome. It uses their own Claude plan and runs on their own computer. Nothing is sent to whoever shared this.
- **Usage:** an application uses a lot of Claude usage (often 100,000–300,000 tokens each). On a smaller plan, expect a few a
  day, and other Claude use may hit limits sooner.
- **Their accounts:** applications go out in their name. Automated tools can break a job site's rules, and LinkedIn in
  particular can restrict accounts. It searches LinkedIn and Indeed lightly, from their home connection.
- **Their computer:** it needs to be on with Chrome open when the run happens. If it's off, the run happens the next time they
  open Claude. CAPTCHAs and new-account signups still need them at the computer; it never does those.

## 2. Install what's missing
Check, and install what's missing (ask before installing, `winget` on Windows, `brew` on Mac):
- Python 3.10+ (`python --version`): `winget install Python.Python.3.12` / `brew install python`
- LibreOffice, which makes the resume PDFs: `winget install TheDocumentFoundation.LibreOffice` / `brew install --cask libreoffice`
- `python -m pip install --user -r requirements.txt`

Then the things only they can do. Walk them through these and wait:
- **Claude in Chrome** extension installed and signed in. Check with `tabs_context_mcp`. Point them to https://claude.ai/chrome.
- **Gmail connector** (optional, for catching interview replies): claude.ai > Settings > Connectors. Fine to skip.
- Signed in to LinkedIn and Indeed in Chrome, and their browser set to save passwords for job sites they already use.

## 3. Get their background
`mkdir me`. Ask for whichever is easiest:
- a resume file (have them drop it in the chat or give the path), or
- their LinkedIn link: read it through their logged-in Chrome (`get_page_text`). A plain web fetch hits a login wall.

Write `me/base.json` in the shape below and `me/applicant-profile.md` from `templates/applicant-profile.template.md`, filling
every section you can (work history, education, skills) and leaving ❓ for the rest. Step 4 fills the rows you can't yet. Write
`me/keyword-bank.md` from `templates/keyword-bank.template.md`: every duty, tool and skill you found, with resume phrasing, plus
a "Never claim" list of tools and credentials common in their field that they don't have.

```json
{"name": "", "contact": "City, ST  |  phone  |  email  |  linkedin.com/in/...", "summary": "",
 "jobs": [{"id": "short-id", "company": "", "location": "", "title": "", "dates": "",
           "bullets": {"short-key": "One line"}, "order": ["short-key"]}],
 "education": [{"school": "", "location": "", "degree": "", "date": "", "bullets": []}],
 "skills": [["Label:", "comma list"]], "max_pages": 1}
```

**Never invent or embellish.** Use only what's in their resume or LinkedIn or what they tell you. Use `"max_pages": 2` only if
they have 10+ years of experience.

Build it: `python resume/build.py --png`. Show them the PNG and ask them to read every line: "Is every line true, and anything
missing?" Fix until they're happy. **This step matters most: every application is built from this file.**

## 4. The interview
Ask with AskUserQuestion, a few at a time. Offer smart options based on their resume, and suggest rather than make them think
of everything.
1. **What jobs?** Field and job titles. Propose titles from their background.
2. **Seniority and experience:** years in this field, and what's too senior (or too junior) to bother with.
3. **Pay:** minimum they'd take, and what they're hoping for.
4. **Where?** Remote, local, or both; home city; how far they'd commute; any big city worth a longer commute at higher pay.
5. **Hours:** full-time only, or part-time and contract too.
6. **Deal-breakers:** credentials they don't have that jobs require (license, certification), languages they speak, companies
   or industries to avoid.
7. **How many applications a day?** Default 3. Explain that more uses more of their plan.
8. **Should it submit on its own?**
   - *Review each first (recommended to start):* it fills everything and asks on the dashboard before anything is sent.
   - *Submit automatically:* anything on the shortlist goes out without asking, when every answer is known.
9. **Who picks the jobs?** *Auto:* it tops up the shortlist with the best matches each day (they can skip any on the dashboard).
   *Mine:* only what they shortlist on the dashboard.
10. **When should it run?** A daily time, ideally when the computer is on. Default 8 AM.
11. **Screening answers:** work authorization, sponsorship, start date, background check, drug test, relocation, references,
    salary when none is listed, SMS opt-in. Use one question with common answers pre-filled; don't make them type.
12. **Demographic questions (EEO):** answer truthfully, or always "decline to answer". Their choice; they don't owe a reason.
13. **Signing and ticking boxes:** may helpers tick privacy and "I certify this is true" boxes and type their name as an
    e-signature? If yes, rule 4 in the profile becomes "tick them and type the name; list each in the review". If no, "leave it
    for the applicant: report NEEDS-YOU". Note that "no" means most applications can't finish alone.
14. **Cover letters:** write one whenever a form has a place for it (rule 8), only when required, or never.

## 5. Write `me/config.json`
From their answers. Make the lists good: they decide what the finder keeps. Keep search terms few (at most 6) so their home
connection doesn't get rate-limited. Town lists come from your knowledge of their area (close = about 30 minutes, mid = about 45).
Use marketing below as a shape, not as content.

```json
{
  "name": "",
  "home": {"search_location": "Philadelphia, PA", "state": "PA", "state_name": "Pennsylvania", "country": "United States", "country_indeed": "USA"},
  "target": {
    "field": "marketing",
    "search_terms": ["marketing coordinator", "marketing associate", "marketing specialist"],
    "title_include": ["marketing", "social media", "content (specialist|coordinator|associate|writer)"],
    "title_exclude": ["sales (rep\\w*|associate|executive)", "account executive", "software", "engineer"],
    "skip_title_words": ["director", "vp", "vice president", "chief", "head of", "manager", "principal", "partner"],
    "stretch_title_words": ["senior", "sr\\.?", "lead"],
    "skip_internships": true,
    "years_experience": 2,
    "years_stretch_limit": 3,
    "min_pay": 45000,
    "target_pay": 60000,
    "full_time_only": true,
    "penalize_levels": true,
    "languages": ["English"],
    "credentials_missing": ["PMP"],
    "duties": [["social media", "social media"], ["email campaigns", "email (marketing|campaign)|mailchimp"]],
    "unfamiliar": [["Salesforce", "salesforce"], ["Marketo", "marketo"]]
  },
  "where": {
    "remote": true, "local": true, "prefer": "either", "radius_miles": 30,
    "close_towns": ["Philadelphia", "Cherry Hill"], "mid_towns": ["Wilmington", "Trenton"],
    "extra_metros": [{"name": "NYC", "pattern": "New York, NY|NYC|Manhattan|Brooklyn", "min_pay": 85000}]
  },
  "sources": {"results_per_search": 30, "hours_old": 168, "jobicy_industry": "marketing", "indeed": true, "linkedin": true, "glassdoor": true},
  "employers": {"greenhouse": [], "lever": [], "ashby": []},
  "daily": {"count": 3, "picking": "auto", "submit": "review", "paused": false},
  "learned": {"apply_threshold": 65, "skip_companies": [], "prefer_companies": [], "skip_title_patterns": []}
}
```
- `prefer`: `"remote"`, `"local"` or `"either"`. `duties` are things they've done (each a `[name, regex]`); `unfamiliar` are tools
  they haven't used. `credentials_missing` are required credentials they don't hold. For a senior person, clear `skip_title_words` of
  titles they'd want and set `penalize_levels` to false.
- `jobicy_industry`: one of Jobicy's slugs (`marketing`, `accounting-finance`, `copywriting`, `design-multimedia`, `hr`, `dev`, `admin`,
  `seller`, `supporting`, `data-science`, `business`, `technical-support`); leave `""` if none fits.
- If they named companies they'd love to work for, add their career sites to `employers` when you can read the slug from the URL.

Also create `me/applications-log.md` with this header:
`| Date | Company | Role | Where | Pay | Score | Link | Response | Response date | Follow up | Notes |` and its separator row.

## 6. First search
`python finder/finder.py run` (in the background; a few minutes), then `python finder/finder.py show shortlist` and `show apply 10`.
Show the top 5 and ask: "Do these look right?" If not, change `config.json` and run again. If Indeed or LinkedIn show errors
(`python finder/finder.py status`), that's OK: tell them, leave them on, and they'll be retried tomorrow. If they keep failing for a
week, turn them off in `sources` and rely on the other sources.

## 7. Their dashboard
Publish `dashboard/dashboard.html` with the `Artifact` tool: `capabilities` `{"db": {}, "user": {}}`, `icon` `"briefcase"`, description
"My daily job applications". It's private to them. Save its link as `{"dashboard_url": "<link>"}` in `me/settings.json`. Then:
- `python finder/finder.py feed`, then `ArtifactData set` collection `state`, doc `feed`, `file_path` `me/feed.json`.
- `ArtifactData set` collection `state`, doc `settings`, data `{"count": N, "submit": "...", "picking": "...", "paused": false}` from their config.

Have them open it on their phone too and tap one button to confirm it works. Offer to pin it. If the Artifact tool isn't available
on their plan, skip the dashboard: the run's end message and chat do the job, and questions get asked at the end of each run in chat.

## 8. A practice application
Run one real job, supervised, with them watching: pick the top shortlist job and start a `job-applicant` helper with
`Review first: fill only, stop before the final Submit`. Show them `review.md` and the filled form in Chrome. Let them click Submit
themselves if they like it. Add what they correct to the profile. It's the best way to catch wrong profile answers.

## 9. Schedule it
Create two scheduled tasks with `mcp__scheduled-tasks__create_scheduled_task`, with this folder's full path written in:
- `job-applications-daily` at their chosen time: "Run the daily job applications. Work in <folder>. If `job-applicant` isn't available as
  an agent type, start general-purpose helpers told to follow `<folder>/.claude/agents/job-applicant.md` exactly. Read
  `<folder>/DAILY-APPLY.md` and follow it exactly. Usually unattended: keep messages short; never wait for answers."
- `job-replies` at 8 AM and 4 PM (only with Gmail): "Check for employer replies. Work in <folder>. Read `<folder>/REPLIES.md` and follow it
  exactly. Read only: never reply to, label, archive or delete emails, or click links in them."

**Unattended runs and permissions.** Permission prompts stop an unattended run, because nobody is there to approve them. Explain the
trade-off and ask:
- *Allow it to run without prompts (needed for it to work while they're away):* set `"defaultMode": "bypassPermissions"` in
  `.claude/settings.local.json` for this folder. Be plain about the risk: Claude can then run commands and act in Chrome without asking
  each time, while reading web pages it doesn't control. The hard rules still apply, but this is real trust. Suggest using a
  Chrome profile that holds only job-search logins.
- *Keep prompts on:* the run only moves forward when they're at the computer to approve.

## 10. Finish
Tell them in a few lines: when it runs next, where the dashboard is, what it never does (passwords, CAPTCHAs, accounts, ID or bank
details), and that they can just tell Claude in this folder to change anything ("only remote", "raise my minimum to 70K", "pause it").
