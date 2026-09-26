from __future__ import annotations

import re


def canonical_brand_preset(value: str) -> str:
    """Accept the neutral generic brand preset and its legacy alias."""
    if not isinstance(value, str):
        raise TypeError("Brand must be `general`.")
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().casefold()).strip("_")
    aliases = {
        "general": "default",
        "default": "default",
        "tutorialflow": "default",
    }
    try:
        return aliases[slug]
    except KeyError as exc:
        raise ValueError(
            "Unknown brand preset. Use `general`."
        ) from exc
