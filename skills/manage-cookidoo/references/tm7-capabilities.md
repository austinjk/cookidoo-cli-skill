# TM7 capability matrix

Reviewed against official Vorwerk and Cookidoo material on 2026-08-03. TM7 software, region, subscription, and accessories can change availability; verify the linked official source when a mode is central to the user's request.

## Keep the layers separate

1. **TM7 hardware/manual cooking**: what a person can select on the appliance.
2. **Official Cookidoo Guided Cooking**: Vorwerk-tested recipes can invoke compatible modes and device-specific flows.
3. **Cookidoo My Creations**: user-created recipes sync to TM7 but are not safety-checked or success-guaranteed.
4. **This CLI's write path**: ordinary TTS fields persist; named `MODE` annotations are intentionally not emitted because they are not reliable through the unofficial API.

Never use a hardware capability as proof that this CLI can encode it. Never use a `TM7` recipe tag as proof of testing or compatibility.

## Manual TM7 modes and functions

Vorwerk France lists more than 20 functions, including Manual Cooking, Open Cooking, Browning, Steam, Dough, Blend, Egg Boiler, Kettle, Sauce, Rice Cooker, Slow Cook, Sous-vide, Fermentation, Warm Up, Turbo, and Pre-clean. Peeler, Grater, Slicer, Spiralizer, and Thermomix Sensor require their matching accessories. Sugar Stages is available only in official Guided Cooking.

Availability can differ by region, installed software, accessory, temperature, and current machine state. If a mode is absent on the user's device, do not invent a substitute.

## What this CLI can persist as ordinary TTS

| Setting | CLI representation | Important boundary |
|---|---|---|
| Time | `time_seconds`, 1–5940 | 99-minute ordinary-step limit; this is not Slow Cook. |
| Temperature | `OFF`, `37`, `40`, then supported increments through `120` | Never round a source temperature. Named modes can use different controls. |
| Steam token | `varoma` | Wire representation only. TM7 treats Varoma cooking as Steam mode, not a temperature above 120°C. |
| Blade speed | `soft`, `0.5`–`5` | Created-recipe TTS limit. TM7 hardware has higher manual speeds, but they are not ordinary TTS here. |
| Direction | `reverse: true` | Counter-clockwise; useful for preserving chunks. |

A TTS annotation does not select a named mode. Do not encode mode-only behavior as a normal temperature/speed approximation.

## Mode-specific rules

| Mode or function | TM7 reality | Rule for a CLI-created recipe |
|---|---|---|
| Open Cooking | No lid, no blade rotation, maximum 100°C. | Prose-only manual handoff. Never set speed or reverse; never exceed 100°C. |
| Browning | TM7 manual mode with Gentle and Intense levels; different from normal 120°C cooking. | Prose-only manual handoff. Never approximate Browning with 105/120°C TTS or claim an automatic mode step. |
| Steam / Varoma | Varoma is Steam mode, not a temperature. Vorwerk says speed 5 maximum for steam. | Name Steam and required Varoma setup in prose. `varoma` TTS may preserve the token, but do not describe it as >120°C. |
| Dough | Mode does not start when the bowl is at or above 60°C and does not heat. | Prose-only manual handoff; require cooling below 60°C. |
| Turbo | Mode is disabled when the bowl is above 60°C. | Prose-only manual handoff with fixed settings; never encode Turbo as speed 10 TTS. Never describe gradually increasing or ramping the speed: the TM7 cannot ramp speed in Turbo mode. |
| Blend / high-speed mixing | TM7 can run above speed 5. | Prose-only manual handoff with fixed time and speed for speed 5.5–10 or Blend. Ordinary TTS stops at 5. Never describe gradually increasing or ramping the speed: TM7 Blend mode does not support speed ramps. |
| Slow Cook | Controls long, gentle cooking as a mode. | Prose-only manual handoff. Do not replace it with repeated 99-minute ordinary steps. |
| Sous-vide | Mode-specific low-temperature behavior; blade cover may be required by recipe/accessory configuration. | Preserve the exact source mode, temperature, time, fill, and accessory instructions in prose. Never snap 63°C to 65°C. |
| Fermentation | Dedicated controlled mode. | Prose-only manual handoff; preserve vessel/accessory and source settings. |
| Rice Cooker, Sauce, Kettle, Egg Boiler, Warm Up | Dedicated algorithms, not ordinary time/temp/speed presets. | Prose-only manual handoff; do not reverse-engineer settings. Warm Up is not a general keep-warm mode. |
| Sugar Stages / Sugar Cooking | Official Guided Cooking only. | Not available to a CLI-created recipe; choose an official recipe or an external method. |
| Peeler, Grater, Slicer, Spiralizer, Sensor, Nester | Requires the named compatible accessory. | For Austin, consult `owned-accessories.md`; otherwise verify ownership and compatibility. Keep the action as a visible manual handoff. |
| Pre-clean | Cleaning mode, not a cooking step. | Do not embed as recipe automation. Mention as optional aftercare only. |

## Physical and safety boundaries

- The mixing bowl capacity is 2.2 L. The manual lists 100 ml maximum oil for Browning.
- Open Cooking permits no blade rotation and no temperature above 100°C.
- The butterfly whisk is limited to speed 4, at most 100°C, for at most 2 hours.
- The TM7 is not an oven, hob, microwave, deep fryer, or grill. It can steam some cakes in Varoma, but it cannot bake a quiche or roast a gratin.
- TM7 has no TM6-style measuring cup. The over-lid/splash cover is normally used; Varoma is the documented exception. Preserve the official recipe's lid/accessory language instead of translating TM6 instructions literally.
- Created Recipes do not detect unsafe quantities, temperatures, mixing power, overfilling, burning, or overheating. The user owns the risk; the validator is structural only.
- Austin owns the TM7 Cutter+, Blade Cover & Peeler, Thermomix Sensor, and TM7 Nester. Availability does not make them mandatory; consult `owned-accessories.md` and use them only when they improve the workflow.
- Do not skip cooling or unlocking delays. Do not claim food is safely cooked from time/temperature alone.

## Recipe and compatibility claims

- An official page's TM7 compatibility badge supports only that exact recipe id/locale/variant.
- Most TM6 recipes are compatible with TM7, but Vorwerk says some require hardware-specific adjustments. Do not mechanically replace TM6 lid, measuring-cup, or mode instructions.
- The CLI's official recipe response currently omits preparation steps. Without source steps, do not invent exact times, temperatures, speed, direction, or mode usage.
- Search results can mix regional variants even when titles match. Check recipe id, ingredient language, utensils, and official public page before calling a result the French version.
- Search rank is not popularity. Use a returned rating count or an official Cookidoo popularity page if popularity matters.

## French examples that expose common mistakes

These examples are for reasoning patterns, not instruction reconstruction:

- **Soupe de courgette et carotte au Kiri**: an official French staple rated 4.9 from 5.6K ratings and compatible with TM5/TM6/TM7. A soup may finish with high-speed blending; do not invent its Blend settings when the CLI has not returned preparation steps.
- **Ratatouille**: official French TM5/TM6/TM7 recipe. Chunk preservation commonly motivates low speed/reverse, but ingredient shape does not prove the exact Guided Cooking setting. Obtain source steps before adapting.
- **Blanquette de veau cuisson lente**: official French TM6/TM7 recipe built around Slow Cook. A normal 99-minute TTS step is not equivalent to Slow Cook.
- **Quiche lorraine**: official TM5/TM6/TM7 recipe, but baking still requires an oven and suitable tin. Compatibility does not mean the TM7 bakes.
- **Bœuf bourguignon**: several regional variants exist. One fetched variant listed a pan and hob; Cookidoo also publishes a Slow Cook version. Identify the exact recipe id before describing the workflow.

## Official sources

- [Vorwerk France: TM7 modes](https://support-france.vorwerk.com/hc/fr-fr/articles/18502424785948-Quels-sont-les-modes-disponibles-sur-le-nouveau-Thermomix-TM7)
- [Vorwerk France: TM7 mode restrictions](https://support-france.vorwerk.com/hc/fr-fr/articles/19115137336092-Ce-qu-il-faut-savoir-sur-les-modes-et-les-fonctionnalit%C3%A9s-du-TM7)
- [Vorwerk France: TM7 user manual](https://assets.vorwerk.com/content/dam/general/zendesk-guide/manuals/tm7_2025-04/user%20manual_TM7_11004_V1.0_FR.pdf)
- [Cookidoo: Thermomix compatibility](https://cookidoo.thermomix.com/foundation/en-US/thermomix-compatibility)
- [Vorwerk France: Created Recipes safety](https://support-france.vorwerk.com/hc/fr-fr/articles/17380924964764-Informations-sur-le-partage-de-recettes-l-utilisation-de-photos-le-succ%C3%A8s-et-la-s%C3%A9curit%C3%A9-des-recettes-cr%C3%A9%C3%A9es)
- [Vorwerk France: Created Recipes on TM7](https://support-france.vorwerk.com/hc/fr-fr/articles/19199918206236-Les-recettes-peuvent-elles-%C3%AAtre-cr%C3%A9%C3%A9es-%C3%A9valu%C3%A9es-et-traduites-directement-sur-le-TM7)
- [Cookidoo France: essential recipes](https://cookidoo.fr/foundation/fr-FR/articles/nos-recettes-incontournables)
- [Cookidoo France: Blanquette Slow Cook](https://cookidoo.fr/recipes/recipe/fr-fr/r511044)
- [Cookidoo France: Quiche lorraine](https://cookidoo.fr/recipes/recipe/fr-FR/r705634)
- [Cookidoo France: Ratatouille](https://cookidoo.fr/recipes/recipe/fr-fr/r431360)
- [Cookidoo France: Courgette/carrot soup](https://cookidoo.fr/recipes/recipe/fr-FR/r145191)
