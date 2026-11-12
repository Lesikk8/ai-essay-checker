"""Інтеграція з Gemini API: перевірка есе англійською мовою."""
import logging
import os
from typing import List

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field

log = logging.getLogger("checker.llm")

# Кілька моделей Flash: якщо в однієї закінчився ліміт (429) або вона
# перевантажена (503/504), пробуємо наступну.
DEFAULT_MODELS = "gemini-3.8-flash,gemini-3.5-flash,gemini-3.5-flash-lite"

CEFR_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
CATEGORIES = ["Grammar", "Vocabulary", "Spelling", "Punctuation", "Style"]


class Mistake(BaseModel):
    fragment: str = Field(description="Exact fragment from the essay, copied character by character")
    correction: str = Field(description="Corrected version of the fragment")
    category: str = Field(description="One of: Grammar, Vocabulary, Spelling, Punctuation, Style")
    rule: str = Field(description="Short explanation of the rule in Ukrainian")


class EssayReport(BaseModel):
    cefr_level: str = Field(description="Estimated CEFR level: A1, A2, B1, B2, C1 or C2")
    grammar: int = Field(description="Grammar score 0-5")
    vocabulary: int = Field(description="Vocabulary score 0-5")
    coherence: int = Field(description="Coherence and cohesion score 0-5")
    task_achievement: int = Field(description="Task achievement score 0-5")
    mistakes: List[Mistake]
    strengths: List[str] = Field(description="2-3 strengths of the essay, in Ukrainian")
    feedback: str = Field(description="Overall feedback and advice, 2-4 sentences in Ukrainian")


EXAMINER_PROMPT = """You are an experienced Cambridge English examiner who checks essays
written by Ukrainian learners of English.

Assess the essay using four criteria, each scored from 0 to 5:
- grammar: accuracy and range of grammatical structures;
- vocabulary: accuracy and range of vocabulary;
- coherence: organisation, paragraphs, linking words;
- task_achievement: how well the essay fits the task type and the topic.

Estimate the overall CEFR level (A1-C2).

Rules for mistakes:
- "fragment" MUST be copied exactly from the essay (same letters, same case), 1-8 words;
- list each real mistake once, at most 15 mistakes, in the order they appear;
- do not mark correct sentences as mistakes and do not invent mistakes;
- write "rule", "strengths" and "feedback" in Ukrainian, simply and clearly,
  as a teacher would explain to a student.
"""


class CheckError(Exception):
    """Зрозуміла помилка для показу користувачу."""


def _models() -> List[str]:
    raw = os.environ.get("GEMINI_MODELS", DEFAULT_MODELS)
    return [m.strip() for m in raw.split(",") if m.strip()]


def _clamp(value: int) -> int:
    return max(0, min(5, int(value)))


def clean_report(report: EssayReport, essay: str) -> EssayReport:
    """Захист від галюцинацій: лишаємо лише помилки, які справді є в тексті."""
    seen = set()
    mistakes = []
    for m in report.mistakes:
        frag = m.fragment.strip()
        if not frag or frag not in essay or frag in seen:
            continue
        if frag == m.correction.strip():
            continue
        seen.add(frag)
        if m.category not in CATEGORIES:
            m.category = "Grammar"
        m.fragment = frag
        mistakes.append(m)

    level = report.cefr_level.strip().upper()
    return report.model_copy(update={
        "cefr_level": level if level in CEFR_LEVELS else "B1",
        "grammar": _clamp(report.grammar),
        "vocabulary": _clamp(report.vocabulary),
        "coherence": _clamp(report.coherence),
        "task_achievement": _clamp(report.task_achievement),
        "mistakes": mistakes,
    })


def check_essay(essay: str, essay_type: str, topic: str) -> tuple[EssayReport, str]:
    """Надсилає есе в Gemini і повертає (звіт, назва моделі)."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise CheckError("Не задано GEMINI_API_KEY.")

    client = genai.Client(api_key=api_key)
    task = f"Task type: {essay_type}\nTopic: {topic or 'not specified'}\n\nEssay:\n{essay}"

    last_error = None
    for model in _models():
        try:
            log.info("[gemini] перевірка: %s", model)
            response = client.models.generate_content(
                model=model,
                contents=[task],
                config=types.GenerateContentConfig(
                    system_instruction=EXAMINER_PROMPT,
                    response_mime_type="application/json",
                    response_schema=EssayReport,
                    temperature=0.2,
                ),
            )
            report = response.parsed
            if report is None:
                report = EssayReport.model_validate_json(response.text)
            log.info("[gemini] %s відповіла", model)
            return clean_report(report, essay), model
        except errors.APIError as e:
            last_error = e
            log.warning("[gemini] %s - %s %s", model, e.code, e.status)
            if e.code in (404, 429, 500, 503, 504):
                continue  # пробуємо наступну модель
            raise CheckError(f"Gemini API повернув помилку {e.code}: {e.message}") from e

    raise CheckError(f"Усі моделі зараз недоступні, спробуйте за хвилину ({last_error}).")
