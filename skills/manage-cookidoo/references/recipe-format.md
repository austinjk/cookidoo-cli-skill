# Recipe JSON format

## Example

```json
{
  "title": "Tomato chicken with rice",
  "language": "en-US",
  "tm_model": "TM7",
  "servings": 4,
  "serving_unit": "portion",
  "prep_time_seconds": 900,
  "total_time_seconds": 2700,
  "ingredients": [
    "100 g onion, halved",
    "20 g olive oil",
    "400 g chicken breast, diced"
  ],
  "steps": [
    {"text": "Place 100 g onion, halved in the mixing bowl."},
    {
      "text": "5 sec/speed 5",
      "time_seconds": 5,
      "speed": 5,
      "anchor": "5 sec/speed 5"
    },
    {
      "text": "Cook the chicken using Browning for 8 minutes; set the program manually.",
      "program": "Browning"
    }
  ],
  "notes": "Check that the chicken is cooked through before serving."
}
```

## Step fields

- `text` is required visible prose.
- `time_seconds` must be `1..5940`.
- `temperature_c` must be `OFF`, `varoma`, or one of `37, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 98, 100, 105, 110, 115, 120`.
- `speed` must be `soft` or `0.5..5` in half-step increments. This is the created-recipe TTS enum, not the TM7 hardware's complete manual speed range. Put speed 5.5–10, Blend, or Turbo instructions in visible prose and select the mode/settings manually.
- `reverse` emits counter-clockwise blade direction and requires another machine setting.
- `anchor` may identify the exact visible setting substring. The CLI rejects the step if it cannot find the anchor or canonical marker; it never appends a setting silently.
- `program` documents a manually selected TM7 mode. It does not create a structured mode annotation or activate that mode on the appliance.

Do not provide `mode`, `power`, `pulse_count`, or raw `annotations`. Cookidoo currently strips special `MODE` annotations from recipes created through this path. Preserve named modes and all of their settings as visible instructions instead.

Use one machine setting per step. Keep source quantities and safety-critical temperatures/times exact; never silently approximate an unsupported value.

For an ordinary structured TTS action, make the setting marker the entire step text:

```json
{"text": "15 sec/speed 3", "time_seconds": 15, "speed": 3}
```

Put `Place 200 g yogurt in the mixing bowl` in the preceding unstructured step. Cookidoo can render a structured action with surrounding prose as a checkbox instead of a TM7 Start button. The CLI normalizes a single action verb plus punctuation (`Mix 15 sec/speed 3.`), but rejects ingredient or explanatory prose around the marker.

## Mode steps

A named mode is not an ordinary TTS step. Prefer prose-only settings:

```json
{
  "text": "Select Slow Cook manually and cook for 2 hours using the exact source settings.",
  "program": "Slow Cook"
}
```

Do not add `time_seconds`, `temperature_c`, `speed`, or `reverse` merely to make a named-mode step look structured. Those fields launch ordinary TTS behavior and do not select Slow Cook, Browning, Open Cooking, Dough, Blend, Turbo, Sous-vide, Fermentation, Sauce, Kettle, Egg Boiler, or another mode. Use them on the same step only when the source explicitly provides a safe ordinary-manual fallback, and label that fallback unambiguously in the prose.

Reject Sugar Stages/Sugar Cooking for a created recipe: it is available only inside official Guided Cooking. Open Cooking must use no lid, no blade rotation, and at most 100°C. Dough requires the bowl below 60°C; Turbo is disabled above 60°C. See [tm7-capabilities.md](tm7-capabilities.md) for the complete matrix.

## Accessory and Sensor steps

Do not add an unverified `accessories`, `utensils`, or accessory-mode field to recipe JSON. Put accessory actions in visible prose. Reserve `program` for the named TM7 modes documented above; Cutter+, Peeler, Sensor, and Nester handoffs do not need it:

```json
{
  "text": "Fit the TM7 Cutter+ slicing assembly and select Thick Slice manually to slice 600 g potatoes into 4–5 mm rounds."
}
```

State the exact accessory, assembly or cut/function, ingredient quantity and preparation, batch/capacity limit when relevant, and where the food goes next. For Sensor steps, state the external appliance and verified core-temperature target and tell the cook to monitor it through Cooking Center. Never imply that a My Creations step automatically launches Cutter+, Peeler, Sensor, Slow Cook, Sous-vide, or another accessory-dependent function. See [owned-accessories.md](owned-accessories.md) for Austin's inventory and the verified selection rules.
