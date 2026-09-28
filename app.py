import io
import re

from docx import Document
from flask import Flask, render_template, request
from pypdf import PdfReader

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB upload limit

SECTIONS = {
    "Experience": ["experience", "work history", "employment"],
    "Education": ["education", "academic"],
    "Skills": ["skills", "technologies", "technical skills"],
    "Projects": ["projects"],
    "Summary": ["summary", "objective", "profile", "about"],
}
ACTION_VERBS = {
    "built", "led", "designed", "developed", "created", "improved", "launched",
    "managed", "reduced", "increased", "implemented", "delivered", "automated",
    "analyzed", "optimized", "mentored", "shipped", "owned", "drove", "wrote",
}
WEAK_PHRASES = [
    "responsible for", "duties included", "worked on", "helped with",
    "hard working", "team player", "detail oriented", "results-driven",
]
STOPWORDS = set(
    "the a an and or of to in for with on at by from as is are be we you our your "
    "this that will can have has it its their they them who about into over more "
    "experience work team role years year ability strong skills".split()
)


def extract_text(file):
    name = file.filename.lower()
    data = file.read()
    if name.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if name.endswith(".docx"):
        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs)
    if name.endswith(".txt"):
        return data.decode("utf-8", errors="ignore")
    raise ValueError("Upload a PDF, DOCX or TXT file.")


def keywords(text):
    words = re.findall(r"[a-zA-Z][a-zA-Z+#.]{2,}", text.lower())
    return {w for w in words if w not in STOPWORDS}


def analyze(text, job_desc=""):
    lower = text.lower()
    words = re.findall(r"\b\w+\b", text)
    checks = []  # (status, title, detail, points_earned, points_possible)

    def add(ok, title, good, bad, points, partial=False):
        status = "pass" if ok else ("warn" if partial else "fail")
        earned = points if ok else (points // 2 if partial else 0)
        checks.append({"status": status, "title": title,
                       "detail": good if ok else bad,
                       "earned": earned, "possible": points})

    # Contact details
    add(re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text), "Email address",
        "Email found.", "No email address found. Add one at the top.", 8)
    add(re.search(r"(\+?\d[\d\s().-]{8,}\d)", text), "Phone number",
        "Phone number found.", "No phone number found.", 5)
    add(re.search(r"linkedin\.com|github\.com", lower), "LinkedIn or GitHub",
        "Profile link found.", "Add a LinkedIn or GitHub link.", 5, partial=False)

    # Sections
    found = [s for s, keys in SECTIONS.items() if any(k in lower for k in keys)]
    for core in ("Experience", "Education", "Skills"):
        add(core in found, f"{core} section",
            f"{core} section detected.",
            f"No clear '{core}' heading found. ATS tools look for it.", 8)

    # Length
    n = len(words)
    add(350 <= n <= 900, "Length",
        f"{n} words: a good length.",
        f"{n} words. Aim for 350 to 900 (one to two pages).", 10,
        partial=200 <= n < 350 or 900 < n <= 1200)

    # Action verbs
    used = sorted(v for v in ACTION_VERBS if re.search(rf"\b{v}\b", lower))
    add(len(used) >= 5, "Action verbs",
        f"Strong verbs used ({', '.join(used[:6])}).",
        "Start bullets with verbs like built, led, improved, launched.", 10,
        partial=len(used) >= 2)

    # Numbers
    nums = re.findall(r"\d+%|\$\d[\d,.]*|\b\d{2,}\b", text)
    add(len(nums) >= 5, "Measurable results",
        f"{len(nums)} numbers found. Good use of metrics.",
        "Add numbers: percentages, money saved, users, team size.", 12,
        partial=len(nums) >= 2)

    # Weak phrases
    weak = [p for p in WEAK_PHRASES if p in lower]
    add(not weak, "Weak phrases",
        "No vague phrases found.",
        f"Replace vague phrases: {', '.join(weak)}.", 8)

    # Job description match
    match = None
    missing = []
    if job_desc.strip():
        jd, cv = keywords(job_desc), keywords(text)
        hits = jd & cv
        match = round(100 * len(hits) / max(len(jd), 1))
        missing = sorted(jd - cv)[:20]
        add(match >= 50, "Job description match",
            f"{match}% of job keywords appear in your resume.",
            f"Only {match}% of job keywords appear in your resume.", 15,
            partial=match >= 30)

    earned = sum(c["earned"] for c in checks)
    possible = sum(c["possible"] for c in checks)
    score = round(100 * earned / possible)
    grade = "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 55 else "D"
    return {"score": score, "grade": grade, "checks": checks,
            "words": n, "match": match, "missing": missing}


@app.route("/", methods=["GET", "POST"])
def index():
    result = error = None
    if request.method == "POST":
        file = request.files.get("resume")
        if not file or not file.filename:
            error = "Choose a resume file first."
        else:
            try:
                text = extract_text(file)
                if len(text.strip()) < 50:
                    error = "Couldn't read any text. Scanned PDFs need OCR first."
                else:
                    result = analyze(text, request.form.get("job_desc", ""))
            except ValueError as e:
                error = str(e)
            except Exception:
                error = "That file couldn't be read. Try another copy."
    return render_template("index.html", result=result, error=error)


if __name__ == "__main__":
    app.run(debug=True)
