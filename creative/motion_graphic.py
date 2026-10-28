"""Chat motion graphics are unavailable until they have a typed template contract."""
from .schemas import CreativeUnavailable

NOT_AVAILABLE = "ساخت موشن‌گرافیک در چت فعلاً در دسترس نیست؛ این مسیر باید به قالب‌های تأییدشده متصل شود."


def unavailable(*args, **kwargs):
    raise CreativeUnavailable(NOT_AVAILABLE)


# Reject every old authoring/assembly entry point, including cached pages.
author = repair = plan = author_scene = assemble = assemble_scenes = write_project = unavailable


def explain_problem(text: str) -> str:
    return NOT_AVAILABLE
