"""
agents/parsing.py — Shared, robust JSON extraction for agent outputs.

WHY THIS EXISTS:
  LLMs return a natural-language response with a JSON block embedded in it.
  The old approach used a regex (r"\\{[^}]+\\}") which breaks the moment the
  JSON contains nested braces (e.g. {"a": {"b": 1}}) or a case description
  that itself contains braces.

  extract_json() instead walks the text looking for a "{" and uses
  json.JSONDecoder().raw_decode(), which parses one complete JSON value
  starting at a given offset (nested braces handled by the real parser).
  The first position that yields a valid JSON object wins.

  ⚠️ Stdlib only — keep this import-light so any agent can use it.
"""

import json


def extract_json(text: str) -> dict | None:
    """Return the first valid JSON object embedded in ``text``, or ``None``.

    Uses ``json.JSONDecoder().raw_decode()`` so nested braces are parsed
    correctly. Scans every ``{`` until one decodes to a dict.
    """
    decoder = json.JSONDecoder()
    search_start = 0
    while True:
        start = text.find("{", search_start)
        if start == -1:
            return None
        try:
            obj, _ = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            search_start = start + 1
            continue
        if isinstance(obj, dict):
            return obj
        search_start = start + 1
