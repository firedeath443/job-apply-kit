# Tailoring a resume to one posting

Goal: rank higher in the employer's applicant tracking system (ATS) and recruiter keyword searches, without
claiming anything untrue.

How screening works: most systems **rank** applicants rather than auto-reject them. Recruiters search resumes by
keyword (Workday's search reportedly matches exact words), and newer systems score how closely the resume's meaning
matches the posting. The hard automatic filters are **knockout questions** on the application form, not resume text.
So mirror the posting's exact terms where true, lead with the most relevant bullets, keep the layout simple, and
answer knockout questions accurately.

## Steps (for each application)
1. Save the full posting text to `me/applications/<slug>/posting.md` (slug = company-role, lowercase, hyphens).
2. Pull its key terms: required duties, software, certifications, years, industry words.
3. Sort each term:
   - In `me/keyword-bank.md` "Confirmed": use the posting's exact wording.
   - In "Never claim": leave it out and flag it (possible knockout).
   - Neither: leave it out and mention it in the report's HIGHLIGHTS. Don't hold up the application for it.
4. Write `me/applications/<slug>/variant.json`: reorder bullets, reword with approved phrasings, adjust the summary
   and skills line. Never add a job, a date, a duty or a skill that isn't already true.
5. `python resume/build.py me/applications/<slug>/variant.json --png`. It spaces the content out to use the page, and
   fails if it doesn't fit.
6. Write `me/applications/<slug>/notes.md`: matched terms, gaps, knockout risks, and fit (strong / ok / stretch).
