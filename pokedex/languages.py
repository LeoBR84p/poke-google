"""Supported UI languages and their PokéAPI lookup priority.

Each language lists the PokéAPI `language_id` values to try in order — the
first one that has data for the field wins; otherwise English (id 9) is the
final fallback (always appended implicitly).
"""

from __future__ import annotations

from dataclasses import dataclass

EN_ID = 9


@dataclass(frozen=True)
class Language:
    code: str           # front-end / URL slug
    native_name: str    # shown in the language picker
    api_ids: tuple[int, ...]  # priority chain; English is always the final fallback


LANGUAGES: tuple[Language, ...] = (
    Language("en", "English", (9,)),
    Language("pt-br", "Português (BR)", (13, 9)),
    Language("es", "Español", (7, 9)),
    Language("ja", "日本語", (11, 1, 9)),
    Language("zh-hans", "中文 (简体)", (12, 9)),
)

DEFAULT_LANG = "en"


def by_code(code: str) -> Language:
    for lang in LANGUAGES:
        if lang.code == code:
            return lang
    raise KeyError(f"unknown language: {code}")


def resolve_text(
    table: dict[tuple[int, int], str],
    key_id: int,
    lang: Language,
) -> str | None:
    """Pick the first available translation from `lang.api_ids`.

    `table` is keyed by `(primary_id, language_id)` — e.g.
    `(move_id, language_id)` for move names.  Returns None only when no
    language in the chain has the entry.
    """
    for lid in lang.api_ids:
        value = table.get((key_id, lid))
        if value:
            return value
    return None
