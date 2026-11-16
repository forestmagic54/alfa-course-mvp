"""Versioned, auditable feature mapping for the product's 23 binary item features.

Never globally replace Latin homographs in arbitrary text. Only explicit aliases
in controlled taxonomy labels are normalized. Unknown labels remain visible in
quality reports and still participate in TF-IDF.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping

from .text_utils import clean_text

STAGES = ("stage_idea", "stage_active", "stage_scale")
TASKS = (
    "task_start",
    "task_tax",
    "task_marketing",
    "task_sales",
    "task_team",
    "task_finance",
)
INDUSTRIES = (
    "ind_ecom",
    "ind_accounting",
    "ind_retail",
    "ind_horeca",
    "ind_services",
    "ind_b2b",
    "ind_b2g",
    "ind_wholesale",
    "ind_production",
    "ind_construction",
    "ind_logistics",
)
FORMATS = ("fmt_course", "fmt_article", "fmt_doc")
FEATURE_CODES = STAGES + TASKS + INDUSTRIES + FORMATS
assert len(FEATURE_CODES) == 23

# These lists are candidate mappings, not verified official ground-truth labels.
# Reviewed taxonomy aliases can be supplied in material input as explicit features.
TASK_LABELS = {
    "task_start": (
        "первые шаги",
        "старт бизнеса",
        "регистрация бизнеса",
        "формы бизнеса",
        "франчайзинг",
        "выбор ниши",
        "генерация идей",
        "создание бизнеса",
    ),
    "task_tax": (
        "налоги",
        "налоги и законы",
        "законы",
        "составление договора",
        "выбор налогового режима",
        "юридические вопросы",
    ),
    "task_marketing": (
        "маркетинг",
        "маркетинг и продажи",
        "маркетплейсы",
        "продвижение в соцсетях",
        "продвижение продукта",
        "реклама",
        "контент-стратегия",
    ),
    "task_sales": (
        "продажи",
        "продажи и переговоры",
        "клиентский сервис",
        "коммуникации",
        "построение воронки продаж",
        "работа в crm",
        "переговоры",
    ),
    "task_team": (
        "управление командой",
        "лидерство",
        "операционка",
        "поиск сотрудников",
        "управление проектами",
        "мотивация сотрудников",
    ),
    "task_finance": (
        "финансы",
        "финансы и учет",
        "финансовый анализ",
        "финансовое планирование",
        "управление финансами",
        "привлечение финансирования",
    ),
}
STAGE_LABELS = {
    "stage_idea": (
        "первые шаги",
        "старт бизнеса",
        "регистрация бизнеса",
        "формы бизнеса",
        "франчайзинг",
        "без опыта",
    ),
    "stage_active": (
        "операционка",
        "налоги и законы",
        "финансы и учет",
        "клиентский сервис",
    ),
    "stage_scale": (
        "стратегия и бизнес-модели",
        "лидерство",
        "управление командой",
        "бизнес за рубежом",
        "ии и автоматизация",
    ),
}
INDUSTRY_LABELS = {
    "ind_ecom": ("ecom", "marketplace", "маркетплейсы", "электронная коммерция"),
    "ind_accounting": ("бухгалтерия", "финансы и страхование"),
    "ind_retail": ("розница", "ретейл", "розничная торговля"),
    "ind_horeca": ("horeca", "общепит", "рестораны и кафе"),
    "ind_services": ("услуги", "сфера услуг"),
    "ind_b2b": ("b2b", "бизнес для бизнеса"),
    "ind_b2g": ("b2g", "бизнес для государства"),
    "ind_wholesale": ("оптовая торговля", "опт"),
    "ind_production": ("производство", "промышленность"),
    "ind_construction": ("строительство и недвижимость", "строительство"),
    "ind_logistics": ("транспорт и логистика", "логистика"),
}
PROMO_LABELS = {"актуальное", "new", "for you", "альфа-банк", "альфа-курс"}
ALIASES = {
    "ретейл": "ретейл",
    "ретэйл": "ретейл",
    "рoзница": "розница",
    "e-commerce": "ecom",
    "ecommerce": "ecom",
    "хорека": "horeca",
    "horeсa": "horeca",
    "маркeтплейсы": "маркетплейсы",
    "постановка целeй": "постановка целей",
    "💥 new": "new",
}


def normalize_label(label: str) -> str:
    label = unicodedata.normalize("NFKC", str(label))
    label = clean_text(label)
    label = re.sub(r"\s+", " ", label).strip()
    return ALIASES.get(label, label)


def features_for(
    *,
    topics: list[str],
    tags: list[str],
    industries: list[str],
    kind: str,
    explicit: list[str] | None = None,
) -> tuple[int, ...]:
    topic_labels = {normalize_label(x) for x in topics}
    tag_labels = {normalize_label(x) for x in tags}
    industry_labels = {normalize_label(x) for x in industries} - PROMO_LABELS
    pooled = topic_labels | tag_labels
    flags = {x: 0 for x in FEATURE_CODES}
    for key, labels in TASK_LABELS.items():
        flags[key] = int(bool(pooled & {normalize_label(x) for x in labels}))
    for key, labels in STAGE_LABELS.items():
        # Promotional industry labels such as 'with experience' must not
        # automatically assert a user's level; stage here relies on topics/tags.
        flags[key] = int(bool(pooled & {normalize_label(x) for x in labels}))
    for key, labels in INDUSTRY_LABELS.items():
        flags[key] = int(
            bool(
                (industry_labels | topic_labels) & {normalize_label(x) for x in labels}
            )
        )
    fmt = {"course": "fmt_course", "article": "fmt_article", "document": "fmt_doc"}[
        kind
    ]
    flags[fmt] = 1
    for key in explicit or []:
        if key not in FEATURE_CODES:
            raise ValueError(f"Unknown feature code: {key}")
        if key in FORMATS and key != fmt:
            raise ValueError("Explicit format feature conflicts with material kind")
        flags[key] = 1
    return tuple(flags[key] for key in FEATURE_CODES)


def unknown_labels(materials: list[Mapping]) -> dict[str, list[str]]:
    known = {
        normalize_label(v)
        for group in (TASK_LABELS, STAGE_LABELS, INDUSTRY_LABELS)
        for vals in group.values()
        for v in vals
    } | PROMO_LABELS
    return {
        key: sorted(
            {
                normalize_label(label)
                for m in materials
                for label in m.get(key, [])
                if normalize_label(label) not in known
            }
        )
        for key in ("topics", "tags", "industries")
    }


PROFILE_TEXT = {
    "stage_idea": "начало своего бизнеса предпринимательство первые шаги",
    "stage_active": "работающий бизнес оптимизация процессов",
    "stage_scale": "масштабирование бизнеса стратегия развитие",
    "task_start": "старт бизнеса регистрация выбор ниши предпринимательство",
    "task_tax": "налоги учет право налогообложение договоры",
    "task_marketing": "маркетинг продвижение реклама привлечение клиентов",
    "task_sales": "продажи увеличение выручки работа с клиентами",
    "task_team": "управление командой сотрудники наем лидерство",
    "task_finance": "финансы бюджет учет финансовое планирование",
    **{k: " ".join(v[:3]) for k, v in INDUSTRY_LABELS.items()},
}
