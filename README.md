# Pokédex by Game

Web Pokédex that lets you pick any mainline Pokémon game and browse the
Pokémon that appear in it, with a classic Pokédex look.

For every Pokémon the app shows:

- National Pokédex number (and the regional/in-game number for that title)
- Type(s) and computed weaknesses (current-gen type chart)
- Sprite or official artwork pulled straight from PokéAPI's sprite repo
- Evolution chain — pre-evolution, current stage, and future evolutions with
  trigger / level / friendship / item conditions
- Possible attacks (level-up, TM/HM, tutor, egg) with **per-game flavor text**

## Data source

Built from the open-source [PokéAPI](https://pokeapi.co) CSV dump
(`github.com/PokeAPI/pokeapi/tree/master/data/v2/csv`). Sprite assets come
from the companion `github.com/PokeAPI/sprites` repository.

The dataset is precomputed into static JSON files (one per game + one per
Pokémon) so the app serves them without ever calling PokéAPI at runtime.

## Supported games

| Generation | Games |
|------------|-------|
| I   | Red / Blue, Yellow |
| II  | Gold / Silver, Crystal |
| III | Ruby / Sapphire, Emerald, FireRed / LeafGreen |
| IV  | Diamond / Pearl, Platinum, HeartGold / SoulSilver |
| V   | Black / White, Black 2 / White 2 |
| VI  | X / Y, Omega Ruby / Alpha Sapphire |
| VII | Sun / Moon, Ultra Sun / Ultra Moon, Let's Go Pikachu / Eevee |
| VIII| Sword / Shield, Brilliant Diamond / Shining Pearl, Legends: Arceus |
| IX  | Scarlet / Violet |

Gen I–VII use PokéAPI's in-game 2D sprites.  Sun / Moon, Let's Go and every
Gen VIII / IX title fall back to the official artwork (same source, higher
resolution).

## Data layout & compression

The dataset is split in two tiers so the UI stays fast:

```
data/games.json(.br)                           — GameIndex
data/games/<game_id>/index.json(.br)           — GamePokedexIndex (summary)
data/games/<game_id>/<species_id>.json(.br)    — PokedexEntry    (full entry)
```

Every `.json` ships with a Brotli-compressed `.json.br` sibling (quality 11).
The FastAPI server detects `Accept-Encoding: br` and returns the precompiled
bytes with `Content-Encoding: br`; otherwise it decompresses on the fly.

Typical wire sizes (post-split + Brotli):

| Request | Before | After |
|---------|--------|-------|
| Scarlet / Violet bootstrap | 16 MB | **9.5 KB** |
| Single Pokémon entry | (inside the 16 MB blob) | **2–4 KB** |
| Game list | 125 KB | **0.7 KB** |

## Project layout

```
.
├── pokedex/
│   ├── schemas.py        # Pydantic models — shared by files + API
│   ├── games.py          # Registry of supported games
│   ├── build_dataset.py  # Transforms PokéAPI CSVs → split JSON + .br
│   └── server.py         # FastAPI app (serves /api/* + static UI)
├── api/
│   └── index.py          # Vercel Serverless Function entrypoint
├── public/               # Static assets (served by Vercel CDN)
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── data/
│   ├── games.json(.br)
│   ├── games/<id>/…      # Per-game summary + per-Pokémon detail
│   └── raw_csv/          # PokéAPI CSV cache (gitignored)
├── vercel.json           # Function + cache header config
├── requirements.txt
└── README.md
```

## Running locally

```bash
pip install -r requirements.txt

# (one-time) refresh the CSV cache and regenerate JSON
mkdir -p data/raw_csv
for f in pokemon.csv pokemon_species.csv pokemon_species_names.csv \
         pokemon_types.csv types.csv type_efficacy.csv moves.csv \
         move_names.csv move_flavor_text.csv version_groups.csv \
         versions.csv pokedexes.csv pokemon_dex_numbers.csv \
         pokemon_species_flavor_text.csv pokemon_evolution.csv \
         pokemon_moves.csv languages.csv pokemon_move_methods.csv ; do
    curl -s -o data/raw_csv/$f \
        "https://raw.githubusercontent.com/PokeAPI/pokeapi/master/data/v2/csv/$f"
done
python -m pokedex.build_dataset

# serve the UI + API
uvicorn pokedex.server:app --reload --port 8000
```

Open http://localhost:8000.

## Deploying to Vercel

1. Commit the `data/games/**/*.json.br` files (they are the dataset the
   serverless function reads).
2. `vercel deploy` — Vercel auto-detects:
   - `api/index.py` as a Python Serverless Function (FastAPI ASGI app);
   - `public/` as the static asset root;
   - `vercel.json` for cache headers, rewrites and `includeFiles` scope.

`vercel.json` adds `"includeFiles": "data/**/*.json.br"` so **only** the
compressed dataset (~5 MB total) is bundled into the function — comfortably
under Hobby's 50 MB deployment limit.

## API

| Method | Path | Returns |
|--------|------|---------|
| GET | `/api/games` | `GameIndex` |
| GET | `/api/games/{game_id}` | `GamePokedexIndex` |
| GET | `/api/games/{game_id}/{species_id}` | `PokedexEntry` |

All JSON responses support `Accept-Encoding: br` and set a long
`Cache-Control` so Vercel's CDN keeps them at the edge.

## Notes & caveats

- Type-effectiveness uses today's chart (Fairy + Steel/Dark changes from
  Gen 6 included). Weaknesses for Gen I–V Pokémon reflect the modern
  matchup, not the era-accurate one.
- Only the default form of each species is included (no megas, regional
  variants, or gigantamax).
- Move list is filtered to level-up, TM/HM, tutor and egg moves.
