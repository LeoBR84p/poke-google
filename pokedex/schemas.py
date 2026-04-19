"""Pydantic models describing the Pokédex dataset schema.

A single schema is shared by the static JSON files and the FastAPI responses.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DamageClass = Literal["physical", "special", "status"]
LearnMethod = Literal["level-up", "machine", "tutor", "egg", "other"]
EvolutionTrigger = Literal[
    "level-up",
    "trade",
    "use-item",
    "shed",
    "spin",
    "tower-of-darkness",
    "tower-of-waters",
    "three-critical-hits",
    "take-damage",
    "other",
]
SpriteKind = Literal["sprite", "official-artwork"]


class Move(BaseModel):
    name: str
    type: str
    damage_class: DamageClass
    power: int | None = None
    accuracy: int | None = None
    pp: int | None = None
    learn_method: LearnMethod
    level_learned: int | None = None
    description: str | None = None


class Weakness(BaseModel):
    type: str
    multiplier: float


class EvolutionTarget(BaseModel):
    species: str
    trigger: EvolutionTrigger
    min_level: int | None = None
    detail: str | None = None


class Evolution(BaseModel):
    stage: int = Field(ge=1, le=3)
    evolves_from: str | None = None
    evolves_to: list[EvolutionTarget] = Field(default_factory=list)


class PokedexEntrySummary(BaseModel):
    """Lightweight payload for the left-hand Pokémon list."""

    national_number: int
    regional_number: int | None = None
    species_id: int
    name: str
    types: list[str]
    sprite_url: str


class PokedexEntry(BaseModel):
    """Full Pokémon payload, loaded on demand when an entry is opened."""

    national_number: int
    regional_number: int | None = None
    species_id: int
    name: str
    genus: str | None = None
    types: list[str]
    weaknesses: list[Weakness]
    description: str | None = None
    sprite_url: str
    artwork_url: str
    height_m: float
    weight_kg: float
    evolution: Evolution
    moves: list[Move]


class GameInfo(BaseModel):
    id: str
    name: str
    generation: int
    version_group_id: int
    pokedex_ids: list[int]
    sprite_kind: SpriteKind
    sprite_path: str | None = None
    release_year: int | None = None


class GamePokedexIndex(BaseModel):
    """Summary document for one game: meta + minimal Pokémon list."""

    game: GameInfo
    pokemon: list[PokedexEntrySummary]


class GameIndex(BaseModel):
    """Top-level index of every supported game."""

    games: list[GameInfo]
