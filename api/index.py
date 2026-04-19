"""Vercel Serverless Function entrypoint.

Vercel's Python runtime auto-detects an ASGI `app` symbol and wraps it.
All routes under `/api/*` are rewritten to this module by `vercel.json`.
"""

from pokedex.server import app  # noqa: F401  — exported for Vercel
