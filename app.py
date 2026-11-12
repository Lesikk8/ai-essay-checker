"""AI Essay Checker — перевірка есе англійською мовою за допомогою Gemini API."""
import logging
import os
import re

from flask import Flask, render_template, request
from markupsafe import Markup, escape

from checker import storage
from checker.llm import CheckError, check_essay

logging.basicConfig(level=logging.INFO, format="%(message)s")

app = Flask(__name__)

ESSAY_TYPES = {
    "opinion": "Opinion essay",
    "for_against": "For and against essay",
    "letter": "Informal letter / email",
    "story": "Story",
    "review": "Review",
}
MIN_WORDS, MAX_WORDS = 50, 600
CRITERIA = [
    ("grammar", "Граматика"),
    ("vocabulary", "Лексика"),
    ("coherence", "Зв’язність"),
    ("task_achievement", "Виконання завдання"),
]


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z']+", text))


def highlight(essay: str, mistakes) -> Markup:
    """Підсвічує фрагменти з помилками в тексті есе (номер — як у списку)."""
    spans = []
    for n, m in enumerate(mistakes, start=1):
        start = essay.find(m.fragment)
        while start != -1 and any(s < start + len(m.fragment) and start < e for s, e, _ in spans):
            start = essay.find(m.fragment, start + 1)
        if start != -1:
            spans.append((start, start + len(m.fragment), n))
    spans.sort()
    out, pos = [], 0
    for s, e, n in spans:
        out.append(escape(essay[pos:s]))
        out.append(Markup('<mark id="m{0}" title="Помилка {0}">{1}<sup>{0}</sup></mark>').format(n, essay[s:e]))
        pos = e
    out.append(escape(essay[pos:]))
    return Markup("").join(out)


@app.get("/")
def index():
    return render_template("index.html", essay_types=ESSAY_TYPES, form={}, error=None,
                           min_words=MIN_WORDS, max_words=MAX_WORDS)


@app.post("/check")
def check():
    form = {k: request.form.get(k, "").strip() for k in ("student", "essay_type", "topic", "essay")}
    words = word_count(form["essay"])
    error = None
    if form["essay_type"] not in ESSAY_TYPES:
        error = "Оберіть тип завдання."
    elif words < MIN_WORDS:
        error = f"Текст закороткий: {words} слів (потрібно щонайменше {MIN_WORDS})."
    elif words > MAX_WORDS:
        error = f"Текст задовгий: {words} слів (максимум {MAX_WORDS})."

    if error is None:
        try:
            report, model = check_essay(form["essay"], ESSAY_TYPES[form["essay_type"]], form["topic"])
        except CheckError as e:
            error = str(e)

    if error:
        return render_template("index.html", essay_types=ESSAY_TYPES, form=form, error=error,
                               min_words=MIN_WORDS, max_words=MAX_WORDS), 400

    saved = None
    if form["student"]:
        saved = storage.save_report(form["student"], form["essay_type"], form["topic"],
                                    form["essay"], report.model_dump(), model)

    total = sum(getattr(report, key) for key, _ in CRITERIA)
    return render_template("result.html", form=form, report=report, model=model, words=words,
                           criteria=CRITERIA, total=total, saved=saved,
                           essay_type=ESSAY_TYPES[form["essay_type"]],
                           highlighted=highlight(form["essay"], report.mistakes))


@app.get("/history")
def history():
    student = request.args.get("student", "").strip()
    items = storage.history(student) if student else []
    return render_template("history.html", student=student, items=items,
                           essay_types=ESSAY_TYPES, firestore=storage.enabled())


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=True)
