# Job apply kit

A personal job-application assistant. It finds jobs every day, tailors a resume to each one, and fills out applications
in the person's own Chrome.

- **`me/config.json` doesn't exist:** this person isn't set up yet. Read `SETUP.md` and follow it, starting now, whatever
  they asked. Be warm and plain: they may never have used a tool like this.
- **Set up, and they ask to apply or start the day's run:** `DAILY-APPLY.md`.
- **Replies from employers:** `REPLIES.md`.
- **They want to change something** (job type, pay, how many a day, auto-submit): update `me/config.json` and tell them what
  changed. Their resume facts: edit `me/base.json`, then `python resume/build.py --png`, then `python resume/build.py --check`.

- **"Update the kit":** `git pull` in this folder (it never touches `me/`), then tell them what changed from `git log`. If it
  isn't a git folder, ask them for the new copy and replace everything except `me/`.

Everything personal lives in `me/`, which is never shared or committed. The resume is generated: change `me/base.json`, never
the PDF. Everything stays truthful: nothing goes on a resume or form that the person hasn't confirmed.
