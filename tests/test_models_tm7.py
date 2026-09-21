from __future__ import annotations

import pytest

from cookidoo_cli.models import RecipeDraft, RecipeStep
from cookidoo_cli.tm7 import validate_tm7_recipe


def valid_recipe() -> RecipeDraft:
    return RecipeDraft.from_dict(
        {
            "title": "Soup",
            "ingredients": ["100 g onion", "500 g water"],
            "steps": [
                {"text": "Place 100 g onion in the mixing bowl."},
                {"text": "Chop 5 sec/speed 5.", "time_seconds": 5, "speed": 5, "anchor": "5 sec/speed 5"},
                {"text": "Add 500 g water."},
                {
                    "text": "Cook 10 min/100°C/reverse/speed 1.",
                    "time_seconds": 600,
                    "temperature_c": 100,
                    "speed": 1,
                    "reverse": True,
                    "anchor": "10 min/100°C/reverse/speed 1",
                },
            ],
            "tm_model": "TM7",
        }
    )


def test_tts_instruction_preserves_settings_and_anchor():
    instruction = valid_recipe().steps[3].to_instruction()
    annotation = instruction["annotations"][0]
    assert annotation["type"] == "TTS"
    assert annotation["data"] == {
        "time": 600,
        "temperature": {"value": "100", "unit": "C"},
        "speed": "1",
        "direction": "CCW",
    }
    position = annotation["position"]
    assert instruction["text"][position["offset"] : position["offset"] + position["length"]] == "10 min/100°C/reverse/speed 1"
    assert instruction["text"] == "10 min/100°C/reverse/speed 1"


def test_tts_rejects_prose_without_setting_marker():
    with pytest.raises(ValueError, match="exact setting marker"):
        RecipeStep(text="Cook the soup.", time_seconds=300, temperature_c=90, speed="soft").to_instruction()


def test_varoma_is_tts_not_mode():
    instruction = RecipeStep(text="Steam 12 min/Varoma/speed 1.", time_seconds=720, temperature_c="varoma", speed=1).to_instruction()
    annotation = instruction["annotations"][0]
    assert annotation["type"] == "TTS"
    assert annotation["data"]["temperature"] == {"value": "varoma"}
    assert "name" not in annotation


@pytest.mark.parametrize("temperature", [36, 63, 121, "hot"])
def test_rejects_unsupported_temperature_instead_of_approximating(temperature):
    with pytest.raises(ValueError, match="Unsupported"):
        RecipeStep(text="Cook.", temperature_c=temperature).to_instruction()


@pytest.mark.parametrize("speed", [0, 5.5, 8, "fast"])
def test_rejects_nonpersistent_speed(speed):
    with pytest.raises(ValueError, match="Unsupported"):
        RecipeStep(text="Blend.", speed=speed).to_instruction()


def test_rejects_mode_fields():
    with pytest.raises(ValueError, match="special-mode"):
        RecipeStep.from_value({"text": "Brown.", "mode": "BROWNING"})


def test_program_is_visible_manual_metadata_only():
    step = RecipeStep.from_value({"text": "Use Browning manually for 8 minutes.", "program": "Browning"})
    assert step.to_instruction()["annotations"] == []


def test_recipe_payload_is_tm7_private_and_annotated():
    payload = valid_recipe().to_payload()
    patch = payload["cookidoo"]["patch"]
    assert patch["tools"] == ["TM7"]
    assert patch["workStatus"] == "PRIVATE"
    assert patch["yield"]["unitText"] == "portion"
    assert "tags" not in patch
    assert len(patch["instructions"]) == 4


def test_tts_rejects_ingredient_prose_around_action():
    with pytest.raises(ValueError, match="prose before"):
        RecipeStep(
            text="Add 500 g water and cook 10 min/100°C/speed 1.",
            time_seconds=600,
            temperature_c=100,
            speed=1,
            anchor="10 min/100°C/speed 1",
        ).to_instruction()


def test_tm7_validator_reports_structure_not_food_safety():
    result = validate_tm7_recipe(valid_recipe())
    assert result["valid"] is True
    assert result["metrics"]["structured_tts_steps"] == 2
    assert any("food safety" in item.lower() for item in result["limitations"])


def test_tm7_validator_warns_for_flat_recipe():
    recipe = RecipeDraft.from_dict({"title": "Toast", "ingredients": ["bread"], "steps": ["Toast bread."], "tm_model": "TM7"})
    result = validate_tm7_recipe(recipe)
    assert any("No persistent TTS" in warning for warning in result["warnings"])


def test_tm7_validator_detects_owned_accessories_in_visible_steps():
    draft = RecipeDraft.from_dict(
        {
            "title": "Accessory workflow",
            "ingredients": ["8 eggs", "600 g potatoes"],
            "steps": [
                "Fill the eight cavities of the TM7 Nester with 8 eggs.",
                "Use the Thermomix Sensor to monitor the external oven step.",
                "Fit the Cutter+ and select Thick Slice manually for 600 g potatoes.",
            ],
        }
    )

    result = validate_tm7_recipe(draft)

    assert result["metrics"]["accessories"] == ["cutter+", "nester", "sensor"]


def test_validator_rejects_open_cooking_with_blade_rotation():
    draft = RecipeDraft.from_dict(
        {
            "title": "Open sauce",
            "ingredients": ["500 g tomatoes"],
            "steps": [
                {
                    "text": "Select Open Cooking manually.",
                    "program": "Open Cooking",
                    "time_seconds": 600,
                    "temperature_c": 100,
                    "speed": 1,
                }
            ],
        }
    )

    result = validate_tm7_recipe(draft)

    assert result["valid"] is False
    assert any("cannot rotate" in error for error in result["errors"])
    assert any("ordinary TTS" in warning for warning in result["warnings"])


def test_validator_rejects_guided_only_sugar_stages():
    draft = RecipeDraft.from_dict(
        {
            "title": "Caramel",
            "ingredients": ["200 g sugar"],
            "steps": [{"text": "Use Sugar Stages.", "program": "Sugar Stages"}],
        }
    )

    result = validate_tm7_recipe(draft)

    assert result["valid"] is False
    assert any("official Guided Cooking" in error for error in result["errors"])


def test_validator_detects_guided_only_mode_from_prose():
    draft = RecipeDraft.from_dict(
        {
            "title": "Caramel",
            "ingredients": ["200 g sugar"],
            "steps": ["Use Sugar Cooking to make the caramel."],
        }
    )

    result = validate_tm7_recipe(draft)

    assert result["valid"] is False
    assert any("official Guided Cooking" in error for error in result["errors"])


@pytest.mark.parametrize(
    ("program", "temperature", "expected_boundary_error"),
    [
        ("Turbo", 60, False),
        ("Turbo", 65, True),
        ("Dough", 55, False),
        ("Dough", 60, True),
    ],
)
def test_validator_distinguishes_turbo_and_dough_temperature_boundaries(program, temperature, expected_boundary_error):
    draft = RecipeDraft.from_dict(
        {
            "title": "Mode boundary",
            "ingredients": ["500 g mixture"],
            "steps": [
                {
                    "text": f"Select {program} manually.",
                    "program": program,
                    "temperature_c": temperature,
                }
            ],
        }
    )

    result = validate_tm7_recipe(draft)

    boundary_errors = [error for error in result["errors"] if "above 60°C" in error or "below 60°C" in error]
    assert bool(boundary_errors) is expected_boundary_error


def blend_recipe(step_text: str) -> RecipeDraft:
    return RecipeDraft.from_dict(
        {
            "title": "Soup",
            "ingredients": ["500 g cauliflower", "650 g water"],
            "steps": [
                {"text": "Place 500 g cauliflower in the mixing bowl."},
                {"text": step_text, "program": "Blend"},
            ],
            "tm_model": "TM7",
        }
    )


@pytest.mark.parametrize(
    "step_text",
    [
        "Select Blend manually and blend for 1 minute, gradually increasing the speed from 5 to 10.",
        "Select Blend manually and ramp the speed up gradually for 1 minute.",
        "Blend for 1 minute, increasing the speed gradually to 10.",
    ],
)
def test_validator_warns_on_gradual_speed_ramp_in_blend(step_text):
    result = validate_tm7_recipe(blend_recipe(step_text))
    assert any("gradually changing the speed" in warning for warning in result["warnings"])


def test_validator_accepts_fixed_blend_settings():
    result = validate_tm7_recipe(blend_recipe("Select Blend manually. Blend 1 min/speed 10."))
    assert not any("gradually changing the speed" in warning for warning in result["warnings"])
