import json
from functools import lru_cache
from importlib.resources import files
from types import MappingProxyType
from uuid import UUID


@lru_cache(maxsize=1)
def load_default_offers() -> MappingProxyType:
    """Подготовленные тексты по Courses.Id; v1 также используется миграцией 0004."""
    path = files('src.config').joinpath('default_offer_texts.v1.json')
    data = json.loads(path.read_text(encoding='utf-8'))
    return MappingProxyType({UUID(course_id): item['text'] for course_id, item in data.items()})
