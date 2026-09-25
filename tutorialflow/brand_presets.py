from __future__ import annotations

import re


def canonical_brand_preset(value: str) -> str:
    """Accept preset IDs and display names while limiting selection to bundled brands."""
    if not isinstance(value, str):
        raise TypeError("Brand must be `education_global` (Education Global) or `default` (TutorialFlow).")
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().casefold()).strip("_")
    aliases = {
        "default": "default",
        "tutorialflow": "default",
        "education_global": "education_global",
        "educationglobal": "education_global",
    }
    try:
        return aliases[slug]
    except KeyError as exc:
        raise ValueError(
            "Unknown brand preset. Use `education_global` (Education Global) or `default` (TutorialFlow)."
        ) from exc
