"""FastAPI app that serves the localized Pokédex dataset.

Layout on disk (produced by `python -m pokedex.build_dataset`):

    data/games.json(.br)                                  — language-neutral index
    data/<lang>/strings.json(.br)                         — UI + type + trigger labels
    data/<lang>/games/<game_id>/index.json(.br)           — summary list
    data/<lang>/games/<game_id>/<species_id>.json(.br)    — full entry

Endpoints
---------
GET /api/languages                               → list of supported languages
GET /api/games                                   → GameIndex (language-neutral)
GET /api/{lang}/strings                          → UI/type/trigger strings
GET /api/{lang}/games/{game_id}                  → GamePokedexIndex
GET /api/{lang}/games/{game_id}/{species_id}     → PokedexEntry

When the client sends `Accept-Encoding: br` the pre-compressed
`.json.br` bytes are streamed back with `Content-Encoding: br`;
otherwise the server decompresses once and returns plain JSON.
"""

from __future__ import annotations

from pathlib import Path

import brotli
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from pokedex.chat import (
    ChatRequest,
    ChatResponse,
    OPENROUTER_MODEL,
    chat as chat_with_professor,
)
import os
from pokedex.languages import LANGUAGES

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
INDEX_PATH = DATA_DIR / "games.json"
PUBLIC_DIR = ROOT / "public"

JSON_CACHE = "public, max-age=3600, s-maxage=604800, stale-while-revalidate=604800"

app = FastAPI(title="Pokédex by Game", version="0.3.0")

VALID_LANGS = {lang.code for lang in LANGUAGES}


def _brotli_response(path: Path, request: Request) -> Response:
    br_path = path.with_suffix(path.suffix + ".br")
    if br_path.exists():
        blob = br_path.read_bytes()
        if "br" in request.headers.get("accept-encoding", "").lower():
            return Response(
                content=blob,
                media_type="application/json",
                headers={
                    "Content-Encoding": "br",
                    "Cache-Control": JSON_CACHE,
                    "Vary": "Accept-Encoding",
                },
            )
        return Response(
            content=brotli.decompress(blob),
            media_type="application/json",
            headers={"Cache-Control": JSON_CACHE, "Vary": "Accept-Encoding"},
        )
    if path.exists():
        return Response(
            content=path.read_bytes(),
            media_type="application/json",
            headers={"Cache-Control": JSON_CACHE},
        )
    raise HTTPException(status_code=404, detail=f"missing file: {path.name}")


def _require_lang(lang: str) -> None:
    if lang not in VALID_LANGS:
        raise HTTPException(status_code=404, detail=f"unknown language: {lang}")


@app.get("/api/languages")
def list_languages() -> JSONResponse:
    return JSONResponse(
        content={
            "languages": [
                {"code": lang.code, "native_name": lang.native_name}
                for lang in LANGUAGES
            ]
        },
        headers={"Cache-Control": JSON_CACHE},
    )


@app.get("/api/games")
def list_games(request: Request) -> Response:
    if not INDEX_PATH.exists() and not INDEX_PATH.with_suffix(".json.br").exists():
        raise HTTPException(
            status_code=503,
            detail="games.json missing — run `python -m pokedex.build_dataset`.",
        )
    return _brotli_response(INDEX_PATH, request)


@app.get("/api/{lang}/strings")
def get_strings(lang: str, request: Request) -> Response:
    _require_lang(lang)
    path = DATA_DIR / lang / "strings.json"
    if not path.exists() and not path.with_suffix(".json.br").exists():
        raise HTTPException(status_code=404, detail=f"strings for {lang} not built")
    return _brotli_response(path, request)


@app.get("/api/{lang}/games/{game_id}")
def get_game_index(lang: str, game_id: str, request: Request) -> Response:
    _require_lang(lang)
    path = DATA_DIR / lang / "games" / game_id / "index.json"
    if not path.exists() and not path.with_suffix(".json.br").exists():
        raise HTTPException(status_code=404, detail=f"unknown game: {game_id}")
    return _brotli_response(path, request)


@app.get("/api/{lang}/games/{game_id}/{species_id}")
def get_pokemon(
    lang: str, game_id: str, species_id: int, request: Request
) -> Response:
    _require_lang(lang)
    path = DATA_DIR / lang / "games" / game_id / f"{species_id}.json"
    if not path.exists() and not path.with_suffix(".json.br").exists():
        raise HTTPException(
            status_code=404, detail=f"species {species_id} not in {game_id}"
        )
    return _brotli_response(path, request)


# ───── chat with Professor Oak / Carvalho ─────


@app.get("/api/chat/health")
def chat_health() -> JSONResponse:
    """Lightweight introspection so the UI can surface config problems
    without having to first fail a real completion request."""
    has_key = bool(os.environ.get("OPENROUTER_API_KEY"))
    return JSONResponse(
        content={
            "has_api_key": has_key,
            "model": OPENROUTER_MODEL,
            "referer": os.environ.get("OPENROUTER_REFERER"),
        }
    )


@app.post("/api/chat", response_model=ChatResponse)
async def post_chat(req: ChatRequest) -> ChatResponse:
    try:
        return await chat_with_professor(req)
    except RuntimeError as exc:
        # Server-side misconfig (missing API key) or malformed upstream JSON.
        raise HTTPException(status_code=503, detail=str(exc))
    except httpx.HTTPStatusError as exc:
        # Surface upstream status + message so the UI can show WHY it failed.
        status = exc.response.status_code
        try:
            body = exc.response.json()
            upstream_msg = (
                (body.get("error") or {}).get("message")
                or body.get("message")
                or str(body)[:300]
            )
        except Exception:
            upstream_msg = (exc.response.text or "")[:300]
        if status == 429:
            code = 429
        elif status in (401, 403):
            # Auth / quota — treat as config so the UI shows the config message.
            code = 503
        else:
            code = 502
        raise HTTPException(
            status_code=code,
            detail=f"OpenRouter {status}: {upstream_msg}",
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"network error: {exc.__class__.__name__}: {exc}"
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ───── static assets for local dev ─────
if PUBLIC_DIR.exists():
    assets_dir = PUBLIC_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
    cells_dir = PUBLIC_DIR / "cells"
    if cells_dir.exists():
        app.mount("/cells", StaticFiles(directory=cells_dir), name="cells")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(PUBLIC_DIR / "index.html")

    @app.get("/chat", include_in_schema=False)
    def chat_page() -> FileResponse:
        return FileResponse(PUBLIC_DIR / "chat.html")

    @app.get("/{asset}", include_in_schema=False)
    def asset(asset: str) -> FileResponse:
        target = PUBLIC_DIR / asset
        if target.is_file():
            return FileResponse(target)
        raise HTTPException(status_code=404)
