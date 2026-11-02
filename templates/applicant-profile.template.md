# Applicant profile: {{NAME}}

Source of truth for filling out job applications. Helpers fill forms from this file. Anything marked ❓ is not
answered yet, so ask instead of guessing.

Files: main resume `me/documents/{{NAME}} Resume.pdf`, tailored resumes `me/applications/<slug>/`, allowed wording
`me/keyword-bank.md`.

## Contact
| Field | Value |
|---|---|
| First name | |
| Last name | |
| Email | |
| Phone | |
| Street address | |
| City / State / ZIP | |
| Country | |
| LinkedIn | |
| Website / portfolio | |

## Work experience (most recent first)
For each job: title, location, dates, full-time or part-time, description (see `me/base.json`), reason for leaving,
supervisor name and phone (leave blank if the applicant doesn't want them listed), and "may we contact?".

## Education
| Field | Value |
|---|---|
| School | |
| Degree | |
| Major | |
| Dates | |
| GPA (only if they want it listed) | |

## Certifications / licenses

## Skills (for tag and keyword boxes)

**Do not claim** (full list in `me/keyword-bank.md`):

## Standard screening answers
| Question | Answer |
|---|---|
| Legally authorized to work here? | |
| Citizen? (or citizen / permanent resident) | |
| Require visa sponsorship now or in future? | |
| 18 or older? | |
| Willing to undergo a background check? | |
| Willing to take a drug test? | |
| Highest education | |
| Years of experience in this field | |
| Desired salary | Midpoint of the posting's listed range, rounded to a clean number (nearest $250; hourly: nearest $0.25). No range listed: use the row below |
| Desired salary when no range is listed | |
| Earliest start date | |
| Notice needed | |
| Willing to relocate? | |
| Work arrangement | |
| Reliable transportation / driver's license? | (never enter the license number) |
| Previously worked for this company? | Answer per company (default No) |
| Ever convicted of a crime? | |
| How did you hear about us? | The job board actually used |
| References | |
| OK to text me during hiring (SMS opt-in)? | |

## Voluntary self-identification (EEO)
The applicant's choice: answer, or "decline to answer". Never guess.
| Question | Answer |
|---|---|
| Gender | |
| Race / ethnicity | |
| Veteran status | |
| Disability status | |

---

## Rules for filling an application
1. Fill only from this file. If a field isn't here, add a question for the applicant, then add their answer to the
   Question bank below so it's never asked twice. Never invent an answer.
2. **Read every question fully before answering it:** the label, help text, every option, and whether it's a
   knockout ("Do you have 2+ years of Salesforce experience?"). Answer what is actually asked, not what the field
   looks like. Watch for:
   - Narrow experience questions (a specific software, a number of years): answer truthfully from the "Do not
     claim" list and the experience numbers above, even if it costs the application.
   - Negatively worded or double questions ("Will you NOT require sponsorship?").
   - Dropdowns whose wording differs from the profile: pick the option that means the same thing, and ask if none
     clearly does.
   - Free-text answers: write them fresh for that question and that company, grounded in the resume.
3. Never type passwords, create accounts, or enter SSN, date of birth, driver's license number, or bank details.
   Never solve CAPTCHAs. When a site shows a login and Chrome has already filled in the saved email and password,
   clicking "Sign in" is fine, and so is "Sign in with Google" when it just signs in. Stop and hand it over
   (NEEDS-YOU) if the fields are empty, a Google consent screen appears, or an account would have to be created.
   Verification codes: never type them in.
4. Privacy-policy boxes, "I certify this is true", acknowledgments and e-signatures: {{SIGNING_RULE}}
5. Upload the tailored `me/applications/<slug>/` resume if one exists, otherwise the main resume. Check what a parsed
   upload filled in against this file and fix mistakes.
6. Intermediate buttons ("Next", "Continue", a "Submit" that only saves a step): click them. Check the step indicator
   first: a button on the last step or a review page counts as final.
7. Final Submit/Apply: only when the helper's prompt carries the approval line (see
   `.claude/agents/job-applicant.md`). Otherwise stop on the review page and report READY.
8. Cover letter: {{COVER_LETTER_RULE}}

## Question bank (answers to one-off questions)
| Question | Answer | Date added |
|---|---|---|

## Fill as much as possible
Answer every optional section too, not just the required ones: work experience, education, skills, work style, links
and similar profile-builder sections. Draft free-text ones fresh, grounded in the resume and real facts (never
invent), and list them in the review. Only leave something blank when there is no truthful answer.
