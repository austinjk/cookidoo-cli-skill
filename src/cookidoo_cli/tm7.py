from __future__ import annotations

import re
from typing import Any

from .models import RecipeDraft

ACCESSORY_RE = re.compile(
    r"\b(varoma|butterfly|whisk|simmering basket|spatula|measuring cup|blade cover|peeler|cutter\+|cutter|spiralizer|sensor|nester)(?=\W|$)",
    re.IGNORECASE,
)
# TM7 Blend/Turbo modes accept fixed settings only; a speed ramp mid-step is impossible on the device.
GRADUAL_SPEED_RE = re.compile(
    r"\bgradually\b.{0,80}\bspeed\b"
    r"|\bspeed\b.{0,80}\bgradually\b"
    r"|\bramp\w*\s+(?:the\s+)?speed\b"
    r"|\bincreas\w*\s+the\s+speed\s+(?:from|to)\b",
    re.IGNORECASE,
)
SPECIAL_PROGRAM_RE = re.compile(
    r"\b(open cooking|browning|high[-_. ]temperature|steam(?:ing)?|dough|knead|turbo|blend|rice cooker|slow cook|sous[-_. ]vide|ferment(?:ation)?|warm[-_. ]up|reheat|sauce|kettle|egg boiler|sugar (?:stages|cooking)|pre[-_. ]clean)\b",
    re.IGNORECASE,
)


def _program_key(value: str | None) -> str | None:
    if not value:
        return None
    normalized = re.sub(r"[-_.]+", " ", value.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    aliases = {
        "knead": "dough",
        "steaming": "steam",
        "ferment": "fermentation",
        "reheat": "warm up",
        "sugar cooking": "sugar stages",
    }
    return aliases.get(normalized, normalized)


KNOWN_PROGRAMS = {
    "open cooking", "browning", "high temperature", "steam", "dough", "turbo", "blend",
    "rice cooker", "slow cook", "sous vide", "fermentation", "warm up", "sauce", "kettle",
    "egg boiler", "sugar stages", "pre clean",
}


def validate_tm7_recipe(draft: RecipeDraft) -> dict[str, Any]:
    """Return structural TM7 guidance; this is not a food-safety certification."""
    errors: list[str] = []
    warnings: list[str] = []
    suggestions: list[str] = []
    try:
        draft.validate()
    except ValueError as exc:
        errors.append(str(exc))

    structured = [step for step in draft.steps if step.structured]
    action_ratio = len(structured) / len(draft.steps) if draft.steps else 0
    ingredient_mentions = sum(
        1
        for step in draft.steps
        if any(ingredient.lower() in step.text.lower() for ingredient in draft.ingredients)
    )
    program_steps = [step for step in draft.steps if step.program or SPECIAL_PROGRAM_RE.search(step.text)]
    accessories = sorted({match.group(0).lower() for step in draft.steps for match in ACCESSORY_RE.finditer(step.text)})

    if draft.tm_model != "TM7":
        warnings.append(f"Recipe is tagged for {draft.tm_model}, not TM7")
    if not structured:
        warnings.append("No persistent TTS machine settings were supplied; every step will be manual text")
    elif action_ratio < 0.25:
        suggestions.append("Consider structuring more machine-action steps with time, temperature, speed, or reverse")
    if not ingredient_mentions:
        suggestions.append("Mention full ingredient strings in preparation steps when useful for Cookidoo linking")
    for step in program_steps:
        if step.program and step.program.lower() not in step.text.lower():
            suggestions.append(f"Name the manual TM7 program {step.program!r} in its visible step text")
        program_match = SPECIAL_PROGRAM_RE.search(step.text)
        program_name = step.program or (program_match.group(0) if program_match else None)
        program = _program_key(program_name)
        if not program:
            continue
        if program not in KNOWN_PROGRAMS:
            warnings.append(f"Unrecognized TM7 program {program_name!r}; verify its exact name and availability on the device")
        if program == "high temperature":
            warnings.append("High Temperature is TM6 terminology; verify whether the exact TM7 recipe uses Browning")
        if program == "sugar stages":
            errors.append("Sugar Stages is available only in official Guided Cooking and cannot be used in a created recipe")
        if program == "open cooking":
            if step.speed is not None or step.reverse:
                errors.append("Open Cooking cannot rotate the blade; remove speed and reverse")
            if isinstance(step.temperature_c, (int, float)) and step.temperature_c > 100:
                errors.append("Open Cooking is limited to 100°C")
        if program == "dough" and isinstance(step.temperature_c, (int, float)) and step.temperature_c >= 60:
            errors.append("Dough cannot start unless the bowl is below 60°C")
        if program == "turbo" and isinstance(step.temperature_c, (int, float)) and step.temperature_c > 60:
            errors.append("Turbo cannot start when the bowl is above 60°C")
        if program in ("blend", "turbo") and GRADUAL_SPEED_RE.search(step.text):
            warnings.append(
                f"TM7 {program_name} mode does not support gradually changing the speed; rewrite the step with fixed settings"
            )
        if step.structured:
            warnings.append(
                f"Structured fields on the {program_name!r} step create ordinary TTS behavior; they do not activate that TM7 mode"
            )
    if any(step.temperature_c == "varoma" and "varoma" not in step.text.lower() for step in draft.steps):
        suggestions.append("Name Varoma in the visible step text when using the varoma TTS temperature")

    score = 0
    if not errors:
        score += 20
    score += min(50, round(action_ratio * 100))
    score += 15 if ingredient_mentions else 0
    score += 10 if accessories else 0
    score += 5 if draft.tm_model == "TM7" else 0

    return {
        "valid": not errors,
        "score": min(100, score),
        "errors": errors,
        "warnings": warnings,
        "suggestions": suggestions,
        "metrics": {
            "steps": len(draft.steps),
            "structured_tts_steps": len(structured),
            "structured_ratio": round(action_ratio, 3),
            "ingredient_reference_steps": ingredient_mentions,
            "manual_program_steps": len(program_steps),
            "accessories": accessories,
        },
        "limitations": [
            "The score measures structure and TM7 usability, not recipe quality or food safety.",
            "Cookidoo created recipes reliably preserve TTS settings; special MODE annotations are not emitted, and their handling by the unofficial API is unverified.",
            "Ordinary created-recipe TTS supports soft/speed 0.5..5 even though TM7 hardware supports higher manual speeds.",
            "The `program` field is visible documentation only; the cook selects the named mode directly on the TM7.",
        ],
    }
