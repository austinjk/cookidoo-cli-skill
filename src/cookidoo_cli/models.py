from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime
from typing import Any

TEMPERATURE_C_VALUES = {
    "OFF", "37", "40", "45", "50", "55", "60", "65", "70", "75", "80",
    "85", "90", "95", "98", "100", "105", "110", "115", "120", "varoma",
}
SPEED_VALUES = {"soft", "0.5", "1", "1.5", "2", "2.5", "3", "3.5", "4", "4.5", "5"}


def jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "model_dump"):
        return jsonable(value.model_dump())
    if hasattr(value, "__dict__"):
        return {key: jsonable(item) for key, item in vars(value).items() if not key.startswith("_")}
    return value


def _speed(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    aliases = {"spoon": "soft", "soft-stir": "soft", "softstir": "soft"}
    text = aliases.get(text, text)
    try:
        if text != "soft":
            text = f"{float(text):g}"
    except ValueError:
        pass
    if text not in SPEED_VALUES:
        raise ValueError(f"Unsupported persistent Cookidoo speed {value!r}; expected soft or 0.5..5")
    return text


def _temperature(value: Any) -> dict[str, str] | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() == "varoma":
        return {"value": "varoma"}
    if text.upper() == "OFF":
        return {"value": "OFF", "unit": "C"}
    try:
        text = f"{float(text):g}"
    except ValueError:
        pass
    if text not in TEMPERATURE_C_VALUES:
        allowed = ", ".join(sorted(TEMPERATURE_C_VALUES - {"varoma", "OFF"}, key=float))
        raise ValueError(f"Unsupported persistent Cookidoo temperature {value!r}; expected one of {allowed}, OFF, or varoma")
    return {"value": text, "unit": "C"}


def _duration(seconds: int) -> str:
    minutes, remainder = divmod(seconds, 60)
    if minutes and remainder:
        return f"{minutes} min {remainder} sec"
    if minutes:
        return f"{minutes} min"
    return f"{remainder} sec"


@dataclass
class RecipeStep:
    text: str
    time_seconds: int | None = None
    temperature_c: int | str | None = None
    speed: str | float | int | None = None
    reverse: bool = False
    program: str | None = None
    anchor: str | None = None

    @classmethod
    def from_value(cls, value: str | dict[str, Any] | RecipeStep) -> RecipeStep:
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls(text=value)
        if not isinstance(value, dict):
            raise TypeError("Each recipe step must be a string or object")
        unsupported = set(value) & {"mode", "power", "pulse_count", "annotations"}
        if unsupported:
            raise ValueError(
                f"Unsupported special-mode fields {sorted(unsupported)}; describe the TM7 program in `program`/`text` and use persistent TTS settings only"
            )
        return cls(
            text=str(value.get("text") or "").strip(),
            time_seconds=value.get("time_seconds"),
            temperature_c=value.get("temperature_c"),
            speed=value.get("speed"),
            reverse=bool(value.get("reverse", False)),
            program=str(value["program"]).strip() if value.get("program") else None,
            anchor=str(value["anchor"]).strip() if value.get("anchor") else None,
        )

    def validate(self) -> None:
        if not self.text:
            raise ValueError("Recipe step text cannot be empty")
        if self.time_seconds is not None and (
            not isinstance(self.time_seconds, int) or not 1 <= self.time_seconds <= 5940
        ):
            raise ValueError("time_seconds must be an integer between 1 and 5940")
        _speed(self.speed)
        _temperature(self.temperature_c)
        if self.reverse and self.speed is None and self.time_seconds is None and self.temperature_c is None:
            raise ValueError("reverse requires at least one machine setting")
        if self.program and self.structured:
            raise ValueError("Named TM7 mode steps cannot include ordinary TTS settings; keep the manual mode handoff in prose only")
        if self.structured:
            self._normalized_tts_text()

    @property
    def structured(self) -> bool:
        return any((self.time_seconds is not None, self.temperature_c is not None, self.speed is not None, self.reverse))

    def marker(self) -> str:
        parts: list[str] = []
        if self.time_seconds:
            parts.append(_duration(self.time_seconds))
        if self.temperature_c is not None:
            rendered = str(self.temperature_c)
            parts.append("Varoma" if rendered.lower() == "varoma" else f"{rendered}°C")
        if self.reverse:
            parts.append("reverse")
        if self.speed is not None:
            parts.append(f"speed {_speed(self.speed)}")
        return "/".join(parts)

    def _normalized_tts_text(self) -> tuple[str, dict[str, int]]:
        marker = self.anchor if self.anchor and self.anchor in self.text else self.marker()
        offset = self.text.find(marker)
        if offset < 0:
            raise ValueError("Structured TTS step must contain its exact setting marker; split prose into a separate step")
        before = self.text[:offset].strip()
        after = self.text[offset + len(marker) :].strip()
        one_action_word = bool(before) and bool(re.fullmatch(r"[^\W\d_]+", before, flags=re.UNICODE))
        if before and not one_action_word:
            raise ValueError("Structured TTS step has prose before its setting marker; split prose into a separate step")
        if after and not re.fullmatch(r"[.!?]+", after):
            raise ValueError("Structured TTS step has prose after its setting marker; split prose into a separate step")
        return marker, {"offset": 0, "length": len(marker)}

    def to_instruction(self) -> dict[str, Any]:
        self.validate()
        if not self.structured:
            return {"type": "STEP", "text": self.text, "annotations": [], "missedUsages": []}
        data: dict[str, Any] = {}
        if self.time_seconds is not None:
            data["time"] = self.time_seconds
        temperature = _temperature(self.temperature_c)
        if temperature is not None:
            data["temperature"] = temperature
        speed = _speed(self.speed)
        if speed is not None:
            data["speed"] = speed
        if self.reverse:
            data["direction"] = "CCW"
        text, position = self._normalized_tts_text()
        return {
            "type": "STEP",
            "text": text,
            "annotations": [{
                "type": "TTS",
                "position": position,
                "data": data,
            }],
            "missedUsages": [],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "time_seconds": self.time_seconds,
            "temperature_c": self.temperature_c,
            "speed": self.speed,
            "reverse": self.reverse,
            "program": self.program,
            "anchor": self.anchor,
        }


@dataclass
class RecipeDraft:
    title: str
    ingredients: list[str]
    steps: list[RecipeStep]
    language: str = "en-US"
    servings: int = 4
    serving_unit: str = "portion"
    prep_time_seconds: int = 0
    total_time_seconds: int = 0
    notes: str = ""
    image: str | None = None
    tm_model: str = "TM7"
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: dict[str, Any], default_tm_model: str = "TM7") -> RecipeDraft:
        if not isinstance(value, dict):
            raise TypeError("Recipe document must be a JSON object")
        return cls(
            title=str(value.get("title") or value.get("name") or "").strip(),
            ingredients=[str(item).strip() for item in value.get("ingredients") or [] if str(item).strip()],
            steps=[RecipeStep.from_value(item) for item in value.get("steps") or []],
            language=str(value.get("language") or "en-US"),
            servings=int(value.get("servings") or 4),
            serving_unit=str(value.get("serving_unit") or "portion"),
            prep_time_seconds=int(value.get("prep_time_seconds") or 0),
            total_time_seconds=int(value.get("total_time_seconds") or 0),
            notes=str(value.get("notes") or ""),
            image=str(value["image"]) if value.get("image") else None,
            tm_model=str(value.get("tm_model") or default_tm_model).upper(),
            tags=[str(item) for item in value.get("tags") or []],
        )

    def validate(self) -> None:
        if not self.title:
            raise ValueError("Recipe title cannot be empty")
        if not self.ingredients:
            raise ValueError("Recipe must contain at least one ingredient")
        if not self.steps:
            raise ValueError("Recipe must contain at least one step")
        if not 1 <= self.servings <= 100:
            raise ValueError("servings must be between 1 and 100")
        if self.prep_time_seconds < 0 or self.total_time_seconds < 0:
            raise ValueError("Recipe times cannot be negative")
        if self.tm_model not in {"TM5", "TM6", "TM7"}:
            raise ValueError("tm_model must be TM5, TM6, or TM7")
        for step in self.steps:
            step.validate()

    def to_payload(self) -> dict[str, Any]:
        self.validate()
        patch = {
            "name": self.title,
            "image": self.image,
            "isImageOwnedByUser": bool(self.image),
            "tools": [self.tm_model],
            "yield": {"value": self.servings, "unitText": self.serving_unit},
            "prepTime": self.prep_time_seconds,
            "cookTime": 0,
            "totalTime": self.total_time_seconds,
            "ingredients": [{"type": "INGREDIENT", "text": item} for item in self.ingredients],
            "instructions": [step.to_instruction() for step in self.steps],
            "hints": self.notes,
            "workStatus": "PRIVATE",
            "recipeMetadata": {"requiresAnnotationsCheck": False},
        }
        return {
            "title": self.title,
            "language": self.language,
            "tm_model": self.tm_model,
            "cookidoo": {
                "create": {"recipeName": self.title},
                "patch": patch,
            },
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "ingredients": self.ingredients,
            "steps": [step.to_dict() for step in self.steps],
            "language": self.language,
            "servings": self.servings,
            "serving_unit": self.serving_unit,
            "prep_time_seconds": self.prep_time_seconds,
            "total_time_seconds": self.total_time_seconds,
            "notes": self.notes,
            "image": self.image,
            "tm_model": self.tm_model,
            "tags": self.tags,
        }
