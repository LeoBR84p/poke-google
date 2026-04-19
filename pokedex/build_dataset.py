"""Transform the PokéAPI CSV dumps into static per-language, per-game JSON.

The dataset is organised in three tiers so the UI stays fast and localisable:

    data/games.json(.br)                         — language-neutral game index
    data/<lang>/strings.json(.br)                — UI + type + trigger labels
    data/<lang>/games/<id>/index.json(.br)       — translated summary list
    data/<lang>/games/<id>/<species_id>.json(.br)— translated full entry

Every `.json` is paired with a `.json.br` Brotli-compressed sibling (q=11).

Run with:  python -m pokedex.build_dataset
"""

from __future__ import annotations

import csv
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import brotli

from pokedex import i18n
from pokedex.games import GAMES, Game
from pokedex.languages import LANGUAGES, EN_ID, Language, resolve_text
from pokedex.schemas import (
    Evolution,
    EvolutionTarget,
    GameIndex,
    GameInfo,
    GamePokedexIndex,
    Move,
    PokedexEntry,
    PokedexEntrySummary,
    Weakness,
)

# ───────────────────────── paths ─────────────────────────

ROOT = Path(__file__).resolve().parents[1]
CSV_DIR = ROOT / "data" / "raw_csv"
DATA_OUT = ROOT / "data"
INDEX_OUT_PATH = DATA_OUT / "games.json"

NATIONAL_DEX = 1

SPRITE_BASE = (
    "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon"
)
ARTWORK_URL = f"{SPRITE_BASE}/other/official-artwork/{{id}}.png"

MOVE_METHOD_KEEP: dict[int, str] = {1: "level-up", 2: "egg", 3: "tutor", 4: "machine"}

TRIGGER_MAP: dict[int, str] = {
    1: "level-up",
    2: "trade",
    3: "use-item",
    4: "shed",
    5: "spin",
    6: "tower-of-darkness",
    7: "tower-of-waters",
    8: "three-critical-hits",
    9: "take-damage",
    10: "other",
}

DAMAGE_CLASS_MAP = {1: "status", 2: "physical", 3: "special"}

BROTLI_QUALITY = 11


def _read_csv(name: str) -> list[dict[str, str]]:
    with (CSV_DIR / name).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _int_or_none(value: str) -> int | None:
    return int(value) if value not in ("", None) else None


def _maybe_int(value: str) -> int:
    return int(value) if value else 0


def _clean_flavor(raw: str) -> str:
    return raw.replace("\n", " ").replace("\f", " ").replace("\u00ad", "")


# ───────────────────────── data load ─────────────────────────


class DataStore:
    """CSV-backed lookup tables.  Loaded once; every language reuses them."""

    def __init__(self) -> None:
        print("loading csvs…", file=sys.stderr)

        pokemons = _read_csv("pokemon.csv")
        self.pokemon_by_id: dict[int, dict[str, str]] = {
            int(r["id"]): r for r in pokemons
        }
        self.default_pokemon_by_species: dict[int, int] = {
            int(r["species_id"]): int(r["id"])
            for r in pokemons
            if r["is_default"] == "1"
        }

        self.species_by_id: dict[int, dict[str, str]] = {
            int(r["id"]): r for r in _read_csv("pokemon_species.csv")
        }

        # Per-language species names + genus: keys are (species_id, language_id).
        self.species_name_by_lang: dict[tuple[int, int], str] = {}
        self.species_genus_by_lang: dict[tuple[int, int], str] = {}
        for row in _read_csv("pokemon_species_names.csv"):
            lid = int(row["local_language_id"])
            sid = int(row["pokemon_species_id"])
            if row.get("name"):
                self.species_name_by_lang[(sid, lid)] = row["name"]
            if row.get("genus"):
                self.species_genus_by_lang[(sid, lid)] = row["genus"]

        self.type_identifier: dict[int, str] = {
            int(r["id"]): r["identifier"] for r in _read_csv("types.csv")
        }

        self.types_of_pokemon: dict[int, list[str]] = defaultdict(list)
        buckets: dict[int, list[tuple[int, str]]] = defaultdict(list)
        for row in _read_csv("pokemon_types.csv"):
            pid = int(row["pokemon_id"])
            slot = int(row["slot"])
            buckets[pid].append((slot, self.type_identifier[int(row["type_id"])]))
        for pid, items in buckets.items():
            self.types_of_pokemon[pid] = [t for _, t in sorted(items)]

        self.damage_factor: dict[tuple[int, int], float] = {
            (int(r["damage_type_id"]), int(r["target_type_id"])): int(r["damage_factor"]) / 100
            for r in _read_csv("type_efficacy.csv")
        }

        self.regional_number: dict[tuple[int, int], int] = {}
        self.species_in_pokedex: dict[int, list[tuple[int, int]]] = defaultdict(list)
        for row in _read_csv("pokemon_dex_numbers.csv"):
            sid = int(row["species_id"])
            pdx = int(row["pokedex_id"])
            num = int(row["pokedex_number"])
            self.regional_number[(pdx, sid)] = num
            self.species_in_pokedex[pdx].append((num, sid))
        self.national_number: dict[int, int] = {
            sid: num for (pdx, sid), num in self.regional_number.items() if pdx == NATIONAL_DEX
        }
        for sid in self.species_by_id:
            self.national_number.setdefault(sid, sid)

        self.move_by_id: dict[int, dict[str, str]] = {
            int(r["id"]): r for r in _read_csv("moves.csv")
        }
        # Move names keyed by (move_id, language_id)
        self.move_name_by_lang: dict[tuple[int, int], str] = {}
        for row in _read_csv("move_names.csv"):
            self.move_name_by_lang[(int(row["move_id"]), int(row["local_language_id"]))] = row["name"]

        # Move flavor texts: (move_id, version_group_id, language_id) -> text
        self.move_flavor: dict[tuple[int, int, int], str] = {}
        # Secondary index keyed by move_id for fast fallback lookups.
        self.move_flavor_by_move: dict[int, list[tuple[int, int, str]]] = defaultdict(list)
        for row in _read_csv("move_flavor_text.csv"):
            mid = int(row["move_id"])
            vgid = int(row["version_group_id"])
            lid = int(row["language_id"])
            text = _clean_flavor(row["flavor_text"])
            self.move_flavor[(mid, vgid, lid)] = text
            self.move_flavor_by_move[mid].append((vgid, lid, text))

        self.learnset: dict[tuple[int, int], list[tuple[int, int, int]]] = defaultdict(list)
        for row in _read_csv("pokemon_moves.csv"):
            method_id = int(row["pokemon_move_method_id"])
            if method_id not in MOVE_METHOD_KEEP:
                continue
            key = (int(row["pokemon_id"]), int(row["version_group_id"]))
            self.learnset[key].append(
                (int(row["move_id"]), method_id, _maybe_int(row["level"]))
            )

        # Species flavor: (species_id, version_id, language_id) -> text
        self.species_flavor: dict[tuple[int, int, int], str] = {}
        self.species_flavor_by_species: dict[int, list[tuple[int, int, str]]] = defaultdict(list)
        for row in _read_csv("pokemon_species_flavor_text.csv"):
            sid = int(row["species_id"])
            vid = int(row["version_id"])
            lid = int(row["language_id"])
            text = _clean_flavor(row["flavor_text"])
            self.species_flavor[(sid, vid, lid)] = text
            self.species_flavor_by_species[sid].append((vid, lid, text))

        self.versions_of_vg: dict[int, list[int]] = defaultdict(list)
        for r in _read_csv("versions.csv"):
            self.versions_of_vg[int(r["version_group_id"])].append(int(r["id"]))
        for lst in self.versions_of_vg.values():
            lst.sort()

        self.evolution_row_by_species: dict[int, dict[str, str]] = {
            int(r["evolved_species_id"]): r for r in _read_csv("pokemon_evolution.csv")
        }

        self.stage_of_species: dict[int, int] = {
            sid: self._stage(sid) for sid in self.species_by_id
        }
        self.evolves_to_of: dict[int, list[int]] = defaultdict(list)
        for sid, row in self.species_by_id.items():
            parent = _int_or_none(row["evolves_from_species_id"])
            if parent is not None:
                self.evolves_to_of[parent].append(sid)

        print("  done.", file=sys.stderr)

    # ─── stage walker ───
    def _stage(self, sid: int) -> int:
        stage = 1
        current = sid
        seen: set[int] = set()
        while current not in seen:
            seen.add(current)
            parent = _int_or_none(
                self.species_by_id[current].get("evolves_from_species_id", "")
            )
            if parent is None:
                break
            current = parent
            stage += 1
        return min(stage, 3)

    # ─── localised lookups ───

    def species_name(self, species_id: int, lang: Language) -> str:
        for lid in lang.api_ids:
            name = self.species_name_by_lang.get((species_id, lid))
            if name:
                return name
        return self.species_name_by_lang.get((species_id, EN_ID)) or self.species_by_id[species_id]["identifier"]

    def species_genus(self, species_id: int, lang: Language) -> str | None:
        for lid in lang.api_ids:
            genus = self.species_genus_by_lang.get((species_id, lid))
            if genus:
                return genus
        return self.species_genus_by_lang.get((species_id, EN_ID))

    def move_name(self, move_id: int, lang: Language) -> str:
        for lid in lang.api_ids:
            name = self.move_name_by_lang.get((move_id, lid))
            if name:
                return name
        return (
            self.move_name_by_lang.get((move_id, EN_ID))
            or self.move_by_id[move_id]["identifier"]
        )

    def species_description(
        self, species_id: int, vg_id: int, lang: Language
    ) -> str | None:
        """Pick the best flavor text for the (species, version_group, language)."""
        chain = lang.api_ids if EN_ID in lang.api_ids else lang.api_ids + (EN_ID,)
        flavors = self.species_flavor_by_species.get(species_id, [])
        if not flavors:
            return None
        # 1) exact version_group in priority-chain order.
        for lid in chain:
            for vid in self.versions_of_vg.get(vg_id, []):
                text = self.species_flavor.get((species_id, vid, lid))
                if text:
                    return text
        # 2) newest version available for the species, in chain order.
        for lid in chain:
            candidates = [(vid, text) for (vid, cur_lid, text) in flavors if cur_lid == lid]
            if candidates:
                candidates.sort()
                return candidates[-1][1]
        return None

    def move_flavor_text(
        self, move_id: int, vg_id: int, lang: Language
    ) -> str | None:
        chain = lang.api_ids if EN_ID in lang.api_ids else lang.api_ids + (EN_ID,)
        flavors = self.move_flavor_by_move.get(move_id, [])
        if not flavors:
            return None
        for lid in chain:
            exact = self.move_flavor.get((move_id, vg_id, lid))
            if exact:
                return exact
            older = [(mvg, text) for (mvg, cur_lid, text) in flavors if cur_lid == lid and mvg <= vg_id]
            if older:
                older.sort()
                return older[-1][1]
            any_vg = [(mvg, text) for (mvg, cur_lid, text) in flavors if cur_lid == lid]
            if any_vg:
                any_vg.sort()
                return any_vg[0][1]
        return None


# ───────────────────────── builders ─────────────────────────


def compute_weaknesses(store: DataStore, poke_types: list[str]) -> list[Weakness]:
    type_name_to_id = {name: tid for tid, name in store.type_identifier.items()}
    defender_ids = [type_name_to_id[t] for t in poke_types]
    weaknesses: list[Weakness] = []
    for attacker_id, attacker_name in store.type_identifier.items():
        if attacker_name in {"unknown", "shadow"}:
            continue
        multiplier = 1.0
        for d_id in defender_ids:
            multiplier *= store.damage_factor.get((attacker_id, d_id), 1.0)
        if multiplier > 1.0:
            weaknesses.append(Weakness(type=attacker_name, multiplier=multiplier))
    weaknesses.sort(key=lambda w: (-w.multiplier, w.type))
    return weaknesses


def sprite_url_for(game: Game, species_id: int, store: DataStore) -> str:
    pokemon_id = store.default_pokemon_by_species.get(species_id, species_id)
    if game.sprite_kind == "sprite" and game.sprite_path:
        return f"{SPRITE_BASE}/versions/{game.sprite_path}/{pokemon_id}.png"
    return ARTWORK_URL.format(id=pokemon_id)


def build_moves(
    store: DataStore, pokemon_id: int, vg_id: int, lang: Language
) -> list[Move]:
    entries = store.learnset.get((pokemon_id, vg_id), [])
    best: dict[tuple[int, int], tuple[int, int, int]] = {}
    for move_id, method_id, level in entries:
        key = (move_id, method_id)
        if key not in best or (method_id == 1 and level < best[key][2]):
            best[key] = (move_id, method_id, level)
    method_order = {1: 0, 4: 1, 3: 2, 2: 3}
    picked = sorted(best.values(), key=lambda t: (method_order.get(t[1], 9), t[2], t[0]))
    moves: list[Move] = []
    for move_id, method_id, level in picked:
        mrow = store.move_by_id.get(move_id)
        if mrow is None:
            continue
        moves.append(
            Move(
                name=store.move_name(move_id, lang).strip(),
                type=store.type_identifier[int(mrow["type_id"])],
                damage_class=DAMAGE_CLASS_MAP[int(mrow["damage_class_id"])],  # type: ignore[arg-type]
                power=_int_or_none(mrow["power"]),
                accuracy=_int_or_none(mrow["accuracy"]),
                pp=_int_or_none(mrow["pp"]),
                learn_method=MOVE_METHOD_KEEP[method_id],  # type: ignore[arg-type]
                level_learned=level if method_id == 1 and level > 0 else None,
                description=store.move_flavor_text(move_id, vg_id, lang),
            )
        )
    return moves


def build_evolution(
    store: DataStore, species_id: int, lang: Language
) -> Evolution:
    stage = store.stage_of_species[species_id]
    parent_id = _int_or_none(
        store.species_by_id[species_id].get("evolves_from_species_id", "")
    )
    evolves_from = store.species_name(parent_id, lang) if parent_id else None

    targets: list[EvolutionTarget] = []
    for child_sid in store.evolves_to_of.get(species_id, []):
        row = store.evolution_row_by_species.get(child_sid, {})
        trigger_id = _int_or_none(row.get("evolution_trigger_id", "")) or 10
        targets.append(
            EvolutionTarget(
                species=store.species_name(child_sid, lang),
                trigger=TRIGGER_MAP.get(trigger_id, "other"),  # type: ignore[arg-type]
                min_level=_int_or_none(row.get("minimum_level", "")),
                detail=None,  # UI composes the label from trigger + min_level per-lang.
            )
        )
    return Evolution(stage=stage, evolves_from=evolves_from, evolves_to=targets)


# ───────────────────────── write helpers ─────────────────────────


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    path.write_bytes(raw)
    path.with_suffix(path.suffix + ".br").write_bytes(
        brotli.compress(raw, quality=BROTLI_QUALITY)
    )


# ───────────────────────── main ─────────────────────────


def build_game(
    store: DataStore, game: Game, lang: Language
) -> tuple[GamePokedexIndex, list[PokedexEntry]]:
    species_ids: list[tuple[int, int]] = []
    seen: set[int] = set()
    for pdx in game.pokedex_ids:
        for num, sid in store.species_in_pokedex.get(pdx, []):
            if sid in seen or sid not in store.default_pokemon_by_species:
                continue
            seen.add(sid)
            species_ids.append((num, sid))
    species_ids.sort(key=lambda t: (t[0], t[1]))

    summaries: list[PokedexEntrySummary] = []
    entries: list[PokedexEntry] = []
    for regional_num, species_id in species_ids:
        pokemon_id = store.default_pokemon_by_species[species_id]
        pokemon_row = store.pokemon_by_id[pokemon_id]
        types = store.types_of_pokemon.get(pokemon_id, [])
        sprite_url = sprite_url_for(game, species_id, store)
        name = store.species_name(species_id, lang)
        national = store.national_number.get(species_id, species_id)

        summaries.append(
            PokedexEntrySummary(
                national_number=national,
                regional_number=regional_num,
                species_id=species_id,
                name=name,
                types=types,
                sprite_url=sprite_url,
            )
        )
        entries.append(
            PokedexEntry(
                national_number=national,
                regional_number=regional_num,
                species_id=species_id,
                name=name,
                genus=store.species_genus(species_id, lang),
                types=types,
                weaknesses=compute_weaknesses(store, types),
                description=store.species_description(species_id, game.version_group_id, lang),
                sprite_url=sprite_url,
                artwork_url=ARTWORK_URL.format(id=pokemon_id),
                height_m=int(pokemon_row["height"]) / 10.0,
                weight_kg=int(pokemon_row["weight"]) / 10.0,
                evolution=build_evolution(store, species_id, lang),
                moves=build_moves(store, pokemon_id, game.version_group_id, lang),
            )
        )

    info = GameInfo(
        id=game.id,
        name=game.name,
        generation=game.generation,
        version_group_id=game.version_group_id,
        pokedex_ids=list(game.pokedex_ids),
        sprite_kind=game.sprite_kind,
        sprite_path=game.sprite_path,
        release_year=game.release_year,
    )
    return GamePokedexIndex(game=info, pokemon=summaries), entries


def main() -> None:
    store = DataStore()

    # Wipe the data/<lang>/ tree so we don't keep stale files.  Leave the
    # top-level data/games.json(.br) until we regenerate it below.
    import subprocess
    for lang in LANGUAGES:
        lang_dir = DATA_OUT / lang.code
        if lang_dir.exists():
            subprocess.run(["rm", "-rf", str(lang_dir)], check=True)

    game_infos: list[GameInfo] = []
    for lang in LANGUAGES:
        print(f"─── language: {lang.code} ({lang.native_name}) ───", file=sys.stderr)
        lang_dir = DATA_OUT / lang.code
        lang_dir.mkdir(parents=True, exist_ok=True)
        write_json(lang_dir / "strings.json", i18n.bundle(lang.code))

        for game in GAMES:
            print(f"  {lang.code} · {game.id}", file=sys.stderr, end=" ")
            index_doc, entries = build_game(store, game, lang)
            game_dir = lang_dir / "games" / game.id
            write_json(game_dir / "index.json", index_doc.model_dump(mode="json"))
            for entry in entries:
                write_json(
                    game_dir / f"{entry.species_id}.json", entry.model_dump(mode="json")
                )
            print(f"→ {len(entries)}", file=sys.stderr)
            if lang.code == "en":
                game_infos.append(index_doc.game)

    write_json(INDEX_OUT_PATH, GameIndex(games=game_infos).model_dump(mode="json"))
    print(f"wrote {len(LANGUAGES)} languages × {len(game_infos)} games", file=sys.stderr)


if __name__ == "__main__":
    main()
