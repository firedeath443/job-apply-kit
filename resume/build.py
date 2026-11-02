"""Build the resume (DOCX + PDF) from me/base.json, optionally tailored by a variant.json.

Usage:
  python resume/build.py                                  -> me/documents/<Name> Resume.{docx,pdf}
  python resume/build.py me/applications/<slug>/variant.json
                                                          -> me/applications/<slug>/<Name> Resume.{docx,pdf}
  add --png to also write a preview image next to the PDF
  python resume/build.py --check                          -> lists every copy out of date with base.json

A variant may set:
  "summary": "<text>"
  "jobs": {"<job id>": {"order": [...], "bullets": {"<bullet id>": "<reworded>"}}}
  "skills": [["Label:", "..."], ...]
Reworded text must stay truthful: use only phrasings from me/keyword-bank.md.
The vertical layout (margins, line and section spacing) is loosened automatically until the content fills the
page, so there is no dead space at the bottom. The build fails if the content can't fit in "max_pages" (default 1).
"""
import copy, hashlib, json, os, re, shutil, subprocess, sys, tempfile
from datetime import date
from pathlib import Path

from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("JOB_KIT_ME", HERE.parent / "me"))
SOFFICE = (shutil.which("soffice") or
           next((p for p in (r"C:\Program Files\LibreOffice\program\soffice.exe",
                             r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
                             "/Applications/LibreOffice.app/Contents/MacOS/soffice") if Path(p).exists()), None))
BASE = ROOT / "base.json"
if not BASE.exists():
    sys.exit(f"No {BASE} yet. Open this folder in Claude and say: set me up.")
PERSON = json.loads(BASE.read_text(encoding="utf-8"))["name"]
NAME = f"{PERSON} Resume"

FONT = "Calibri"
BODY = 11
ACCENT = RGBColor(0x1F, 0x3A, 0x5F)
SLACK = 0.03


def load(variant_path):
    data = json.loads(BASE.read_text(encoding="utf-8"))
    if not variant_path:
        return data, ROOT / "documents"
    v = json.loads(Path(variant_path).read_text(encoding="utf-8"))
    data = copy.deepcopy(data)
    if "summary" in v:
        data["summary"] = v["summary"]
    for job in data["jobs"]:
        jv = v.get("jobs", {}).get(job["id"], {})
        for key, text in jv.get("bullets", {}).items():
            if key not in job["bullets"]:
                sys.exit(f"variant adds unknown bullet '{key}' to {job['id']}; add it to base.json first")
            job["bullets"][key] = text
        if "order" in jv:
            unknown = set(jv["order"]) - set(job["bullets"])
            if unknown:
                sys.exit(f"unknown bullets in order for {job['id']}: {unknown}")
            job["order"] = jv["order"]
    if "skills" in v:
        data["skills"] = v["skills"]
    return data, Path(variant_path).resolve().parent


def lerp(tight, loose, t):
    return tight + (loose - tight) * t


def build_docx(data, out_docx, t=0.0):
    """t = 0 is the tightest layout, t = 1 the loosest."""
    # Only vertical spacing changes, so line wraps stay the same at every t.
    body = BODY
    line = lerp(1.0, 1.3, t)
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Inches(8.5), Inches(11)
    sec.left_margin = sec.right_margin = Inches(0.7)
    sec.top_margin = sec.bottom_margin = Inches(lerp(0.6, 0.9, t))
    text_w = sec.page_width - sec.left_margin - sec.right_margin

    st = doc.styles["Normal"]
    st.font.name = FONT
    st.font.size = Pt(body)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    st.paragraph_format.space_after = Pt(0)
    st.paragraph_format.space_before = Pt(0)
    st.paragraph_format.line_spacing = line
    doc.styles["List Bullet"].font.name = FONT
    doc.styles["List Bullet"].font.size = Pt(body)

    def para(space_before=0, space_after=0, align=None):
        p = doc.add_paragraph()
        p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(space_before), Pt(space_after)
        if align is not None:
            p.alignment = align
        return p

    def run(p, text, bold=False, italic=False, size=None, color=None):
        r = p.add_run(text)
        r.bold, r.italic = bold, italic
        if size:
            r.font.size = Pt(size)
        if color:
            r.font.color.rgb = color

    def section(title):
        p = para(space_before=lerp(12, 24, t), space_after=lerp(4, 8, t))
        run(p, title.upper(), bold=True, size=body, color=ACCENT)
        bdr = OxmlElement("w:pBdr")
        b = OxmlElement("w:bottom")
        for k, val in (("val", "single"), ("sz", "6"), ("space", "1"), ("color", "1F3A5F")):
            b.set(qn(f"w:{k}"), val)
        bdr.append(b)
        p._p.get_or_add_pPr().append(bdr)

    def left_right(left, right, bold_left=True, italic=False, space_before=0):
        p = para(space_before=space_before)
        p.paragraph_format.tab_stops.add_tab_stop(text_w, WD_TAB_ALIGNMENT.RIGHT)
        run(p, left, bold=bold_left, italic=italic)
        run(p, "\t" + right, italic=italic)

    def bullet(text, label=None):
        p = doc.add_paragraph(style="List Bullet")
        pf = p.paragraph_format
        pf.space_before, pf.space_after = Pt(0), Pt(lerp(0, 4, t))
        pf.line_spacing = line
        pf.left_indent = Inches(0.22)
        pf.first_line_indent = Inches(-0.16)
        if label:
            run(p, label, bold=True)
            text = " " + text
        run(p, text)

    p = para(align=WD_ALIGN_PARAGRAPH.CENTER)
    run(p, PERSON, bold=True, size=round(lerp(20, 24, t)), color=ACCENT)
    p = para(space_before=lerp(2, 4, t), align=WD_ALIGN_PARAGRAPH.CENTER)
    run(p, data["contact"])

    section("Summary")
    run(para(), data["summary"])

    section("Experience")
    for i, job in enumerate(data["jobs"]):
        left_right(job["company"], job["location"], space_before=lerp(8, 16, t) if i else 0)
        left_right(job["title"], job["dates"], bold_left=False, italic=True)
        for key in job["order"]:
            bullet(job["bullets"][key])

    schools = data.get("education") or []
    if schools:
        section("Education")
    for i, ed in enumerate(schools if isinstance(schools, list) else [schools]):
        left_right(ed["school"], ed.get("location", ""), space_before=lerp(4, 8, t) if i else 0)
        left_right(ed["degree"], ed.get("date", ""), bold_left=False, italic=True)
        for b in ed.get("bullets", []):
            bullet(b)

    if data.get("skills"):
        section("Skills")
    for label, text in data.get("skills", []):
        bullet(text, label=label)

    doc.core_properties.author = PERSON
    doc.core_properties.title = f"{PERSON} – Resume"
    doc.save(out_docx)


def to_pdf(out_docx, png=False):
    if not SOFFICE:
        sys.exit("LibreOffice isn't installed. See SETUP.md, step 2.")
    outdir = str(out_docx.parent)
    # Own LibreOffice profile per build, so helper agents can build resumes at the same time.
    profile = Path(tempfile.mkdtemp(prefix="lo-profile-"))
    soffice = [SOFFICE, f"-env:UserInstallation={profile.as_uri()}", "--headless"]
    try:
        subprocess.run(soffice + ["--convert-to", "pdf", "--outdir", outdir, str(out_docx)],
                       check=True, capture_output=True)
        pdf = out_docx.with_suffix(".pdf")
        pages = len(re.findall(rb"/Type\s*/Page[^s]", pdf.read_bytes()))
        if png:
            subprocess.run(soffice + ["--convert-to", "png", "--outdir", outdir, str(out_docx)],
                           check=True, capture_output=True)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    return pdf, pages


# ---------- one true resume: stamps and the --check ----------
# Every build writes built-from.json next to its PDF: which base.json it came from, plus the base text of
# anything the variant overrides. `--check` then finds anything out of date with the current base.json.


def base_hash():
    return hashlib.sha256(BASE.read_bytes()).hexdigest()[:16]


def overridden_base_text(variant_path):
    """The base.json text behind each piece a variant replaces (summary, skills, reworded bullets)."""
    if not variant_path:
        return {}
    base = json.loads(BASE.read_text(encoding="utf-8"))
    v = json.loads(Path(variant_path).read_text(encoding="utf-8"))
    out = {}
    if "summary" in v:
        out["summary"] = base["summary"]
    if "skills" in v:
        out["skills"] = base["skills"]
    for job in base["jobs"]:
        for key in v.get("jobs", {}).get(job["id"], {}).get("bullets", {}):
            out[f"{job['id']}.{key}"] = job["bullets"].get(key)
    return out


def check():
    """Report every resume copy that no longer matches base.json. Exit 1 if any need action."""
    now, problems = base_hash(), []
    stamp = ROOT / "documents" / "built-from.json"
    if not stamp.exists() or json.loads(stamp.read_text())["base"] != now:
        problems.append("documents/ main resume is older than base.json: run `python resume/build.py --png`")
    for variant in sorted((ROOT / "applications").glob("*/variant.json")):
        folder = variant.parent
        if (folder / "submitted.txt").exists():
            continue  # a record of what was sent; leave it alone
        s = folder / "built-from.json"
        if not s.exists():
            problems.append(f"{folder.name}: no build stamp; rebuild it")
            continue
        s = json.loads(s.read_text(encoding="utf-8"))
        if s["base"] == now:
            continue
        changed = [k for k, old in overridden_base_text(variant).items() if s["overrides"].get(k) != old]
        msg = f"{folder.name}: built from an older base.json; rebuild it"
        if changed:
            msg += f". Base text changed under its own rewording of {', '.join(changed)}: update variant.json first"
        problems.append(msg)
    print("\n".join(problems) if problems else "OK: every resume copy matches base.json")
    sys.exit(1 if problems else 0)


def main():
    if "-h" in sys.argv or "--help" in sys.argv:
        print(__doc__)
        return
    if "--check" in sys.argv:
        check()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    data, outdir = load(args[0] if args else None)
    outdir.mkdir(parents=True, exist_ok=True)
    out_docx = outdir / f"{NAME}.docx"

    limit = data.get("max_pages", 1)

    def pages_at(t):
        build_docx(data, out_docx, t)
        return to_pdf(out_docx)[1]

    if pages_at(0.0) > limit:
        sys.exit(f"FAIL: {out_docx.with_suffix('.pdf')} is over {limit} page(s) at the tightest layout; trim content")
    # Loosen the layout as far as it goes while staying on one page.
    lo, hi = 0.0, 1.0
    if pages_at(1.0) <= limit:
        lo = 1.0
    else:
        for _ in range(6):
            mid = (lo + hi) / 2
            if pages_at(mid) <= limit:
                lo = mid
            else:
                hi = mid
        lo = max(0.0, lo - SLACK)  # leave a little room so Word doesn't spill a line
    build_docx(data, out_docx, lo)
    pdf, pages = to_pdf(out_docx, png="--png" in sys.argv)
    if pages > limit:
        sys.exit(f"FAIL: {pdf} is {pages} pages")
    (outdir / "built-from.json").write_text(json.dumps(
        {"base": base_hash(), "built": date.today().isoformat(),
         "overrides": overridden_base_text(args[0] if args else None)}, indent=1), encoding="utf-8")
    print(f"OK: {pdf} ({pages} page(s), layout {lo:.2f})")


if __name__ == "__main__":
    main()
