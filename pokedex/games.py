"""Registry of Pokémon games that the Pokédex supports.

Each entry maps a user-facing game slug to:
- PokéAPI `version_group` id (used to pick move descriptions and learnsets);
- one or more regional `pokedex` ids (defines which Pokémon appear in the game);
- a sprite source: either a folder inside
  https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/versions/
  or the "official-artwork" fallback for games whose 2D sprites are not
  archived in the PokeAPI sprite repository.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SpriteKind = Literal["sprite", "official-artwork"]


@dataclass(frozen=True)
class Game:
    id: str
    name: str
    generation: int
    version_group_id: int
    pokedex_ids: tuple[int, ...]
    sprite_kind: SpriteKind
    sprite_path: str | None
    release_year: int


# Order roughly follows release order per generation.
GAMES: tuple[Game, ...] = (
    # ── Generation I ──
    Game("red-blue", "Red / Blue", 1, 1, (2,), "sprite", "generation-i/red-blue", 1996),
    Game("yellow", "Yellow", 1, 2, (2,), "sprite", "generation-i/yellow", 1998),
    # ── Generation II ──
    Game("gold-silver", "Gold / Silver", 2, 3, (3,), "sprite", "generation-ii/gold", 1999),
    Game("crystal", "Crystal", 2, 4, (3,), "sprite", "generation-ii/crystal", 2000),
    # ── Generation III ──
    Game("ruby-sapphire", "Ruby / Sapphire", 3, 5, (4,), "sprite", "generation-iii/ruby-sapphire", 2002),
    Game("emerald", "Emerald", 3, 6, (4,), "sprite", "generation-iii/emerald", 2004),
    Game(
        "firered-leafgreen",
        "FireRed / LeafGreen",
        3,
        7,
        (2,),
        "sprite",
        "generation-iii/firered-leafgreen",
        2004,
    ),
    # ── Generation IV ──
    Game("diamond-pearl", "Diamond / Pearl", 4, 8, (5,), "sprite", "generation-iv/diamond-pearl", 2006),
    Game("platinum", "Platinum", 4, 9, (6,), "sprite", "generation-iv/platinum", 2008),
    Game(
        "heartgold-soulsilver",
        "HeartGold / SoulSilver",
        4,
        10,
        (7,),
        "sprite",
        "generation-iv/heartgold-soulsilver",
        2009,
    ),
    # ── Generation V ──
    Game("black-white", "Black / White", 5, 11, (8,), "sprite", "generation-v/black-white", 2010),
    Game(
        "black-2-white-2",
        "Black 2 / White 2",
        5,
        14,
        (9,),
        "sprite",
        "generation-v/black-white",
        2012,
    ),
    # ── Generation VI ──
    Game("x-y", "X / Y", 6, 15, (12, 13, 14), "sprite", "generation-vi/x-y", 2013),
    Game(
        "omega-ruby-alpha-sapphire",
        "Omega Ruby / Alpha Sapphire",
        6,
        16,
        (15,),
        "sprite",
        "generation-vi/omegaruby-alphasapphire",
        2014,
    ),
    # ── Generation VII ──
    Game("sun-moon", "Sun / Moon", 7, 17, (16, 17, 18, 19, 20), "official-artwork", None, 2016),
    Game(
        "ultra-sun-ultra-moon",
        "Ultra Sun / Ultra Moon",
        7,
        18,
        (21, 22, 23, 24, 25),
        "sprite",
        "generation-vii/ultra-sun-ultra-moon",
        2017,
    ),
    Game("lets-go", "Let's Go Pikachu / Eevee", 7, 19, (26,), "official-artwork", None, 2018),
    # ── Generation VIII ──
    Game("sword-shield", "Sword / Shield", 8, 20, (27, 28, 29), "official-artwork", None, 2019),
    Game(
        "brilliant-diamond-shining-pearl",
        "Brilliant Diamond / Shining Pearl",
        8,
        23,
        (5,),
        "official-artwork",
        None,
        2021,
    ),
    Game("legends-arceus", "Legends: Arceus", 8, 24, (30,), "official-artwork", None, 2022),
    # ── Generation IX ──
    Game("scarlet-violet", "Scarlet / Violet", 9, 25, (31, 32, 33), "official-artwork", None, 2022),
)


def by_id(game_id: str) -> Game:
    for g in GAMES:
        if g.id == game_id:
            return g
    raise KeyError(f"Unknown game id: {game_id}")
