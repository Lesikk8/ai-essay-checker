"""Збереження звітів у Firestore. Якщо Firestore недоступний — застосунок працює без історії."""
import logging
import os
from datetime import datetime, timezone

log = logging.getLogger("checker.storage")
COLLECTION = "essays"

_db = None
_tried = False


def get_db():
    global _db, _tried
    if _tried:
        return _db
    _tried = True
    if os.environ.get("USE_FIRESTORE", "1") != "1":
        log.info("[firestore] вимкнено (USE_FIRESTORE=0)")
        return None
    try:
        from google.cloud import firestore
        _db = firestore.Client()
        log.info("[firestore] підключено, проєкт %s", _db.project)
    except Exception as e:  # немає облікових даних локально
        log.warning("[firestore] недоступний: %s", e)
        _db = None
    return _db


def enabled() -> bool:
    return get_db() is not None


def save_report(student: str, essay_type: str, topic: str, essay: str, report: dict, model: str):
    db = get_db()
    if db is None:
        return None
    total = report["grammar"] + report["vocabulary"] + report["coherence"] + report["task_achievement"]
    doc = {
        "student": student,
        "student_key": student.strip().lower(),
        "essay_type": essay_type,
        "topic": topic,
        "essay": essay,
        "report": report,
        "total": total,
        "model": model,
        "created": datetime.now(timezone.utc),
    }
    try:
        _, ref = db.collection(COLLECTION).add(doc)
        log.info("[firestore] збережено %s", ref.id)
        return ref.id
    except Exception as e:
        log.warning("[firestore] не вдалося зберегти: %s", e)
        return None


def history(student: str, limit: int = 20):
    db = get_db()
    if db is None:
        return []
    key = student.strip().lower()
    from google.cloud.firestore_v1.base_query import FieldFilter
    query = db.collection(COLLECTION).where(filter=FieldFilter("student_key", "==", key))
    docs = query.limit(100).stream()
    items = [d.to_dict() | {"id": d.id} for d in docs]
    items.sort(key=lambda x: x["created"])
    return items[-limit:]
