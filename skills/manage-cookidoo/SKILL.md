---
name: manage-cookidoo
description: Search and inspect Cookidoo recipes, validate and create TM7-aware custom recipes, upload custom recipe images, browse collections, and read or change Cookidoo meal plans through the bundled local JSON CLI. Use when a user mentions Cookidoo, Thermomix, TM7 recipes, weekly meal planning, translating/adapting recipes, saving custom recipes, recipe photos, or removing created recipes. Never use MCP for these workflows.
---

# Manage Cookidoo

Use `scripts/cookidoo` for every Cookidoo account operation. Parse its stdout as JSON. Do not invoke an MCP server. Use official Vorwerk/Cookidoo pages only to verify current device facts or public recipe compatibility when the bundled reference says verification is needed.

## Safety

- Never request or accept a Cookidoo password in chat. Direct the user to run `scripts/cookidoo login` in an interactive terminal.
- Never read, print, copy, or attach the cookie/config files.
- Treat recipe creation, deletion, and meal-plan changes as confirmation-gated mutations.
- Treat created-recipe image upload as the standing exception: upload directly without requesting approval or creating a confirmation token. This exception applies only to image fields, not other recipe edits.
- Run every confirmation-gated mutation without `--confirm` first. Show the returned preview and ask for explicit approval in the current conversation.
- After approval for a confirmation-gated mutation, repeat the exact command and exact input with the returned `--confirm TOKEN`.
- Never recompute, bypass, or reuse a confirmation token. Tokens expire after 15 minutes and bind to the exact payload.

## Authentication

Check local authentication before account work:

```bash
scripts/cookidoo auth status
```

Use `--live` only when a read-only Cookidoo request is needed to verify that cookies remain valid. If login is required, tell the user to run:

```bash
scripts/cookidoo login --email USER@example.com
```

The password prompt is terminal-only. The CLI stores session cookies with owner-only permissions and does not store the password.

## Read workflows

Search TM7 recipes:

```bash
scripts/cookidoo search "chicken curry" --tm-model TM7 --limit 10
```

Fetch a recipe or collection:

```bash
scripts/cookidoo recipe get RECIPE_ID
scripts/cookidoo collection get COLLECTION_ID
```

Read the week containing a date:

```bash
scripts/cookidoo plan show 2026-08-03
```

Use filters only when the user asks for them. Fetch full recipe details before relying on nutrition, ingredients, utensils, timings, or notes.

For cross-language discovery, first search the dish name with only the requested TM model. Strict country/language facets can return an empty set across regional catalogues. If a faceted search is empty, remove country, then language, and disclose the fallback. Never infer a recipe's language, region, popularity, or exact preparation steps from its title or search rank.

The CLI's official-recipe detail response does not expose Guided Cooking preparation steps. Report only returned fields such as ingredients, utensils, timings, nutrition, compatibility metadata, and notes. Do not reconstruct or invent machine settings. Ask the user for the source steps when adapting a recipe whose instructions are unavailable.

## TM7 recipe workflow

Read [references/tm7-capabilities.md](references/tm7-capabilities.md) and [references/owned-accessories.md](references/owned-accessories.md) before making any TM7 capability claim or generating/adapting a recipe. Then read [references/recipe-format.md](references/recipe-format.md) before writing recipe JSON.

1. Draft a recipe JSON file in a temporary workspace location. Review every step against the TM7 screen-writing rules below before validation.
2. Validate it with `scripts/cookidoo recipe validate --file PATH`.
3. Fix all errors. Explain warnings that materially affect guided cooking.
4. Run `scripts/cookidoo recipe create --file PATH` to obtain a dry-run preview.
5. Show the title, ingredients, steps, TM model, structured settings, manual-mode handoffs, external appliances/accessories, warnings, and payload digest.
6. Ask for explicit approval.
7. Repeat with the exact file plus `--confirm TOKEN`.
8. Fetch the returned recipe id and verify the saved recipe.

Classify every machine action before writing it:

- Ordinary created-recipe TTS: encode only persistent time, allowed temperature, speed soft/0.5–5, and reverse.
- Named TM7 mode: write the step as a direct instruction naming the mode with its fixed settings, plus `program`. Mode settings are always fixed values; never describe gradually increasing or ramping the speed or temperature during a mode, because the TM7 does not support that. Do not promise a Play button or encode a normal TTS step as though it activates the mode.
- Guided-only, accessory-dependent, or external operation: state the requirement explicitly. Never replace it with an invented TM7 setting.

Assume Austin has the TM7 Cutter+, Blade Cover & Peeler, Thermomix Sensor, and TM7 Nester available. Do not use them by default. When one materially simplifies prep, improves consistency or doneness, protects delicate food, or enables useful individual portions, incorporate it into the visible recipe instructions with the exact accessory, function/cut, quantity or capacity, and any external appliance. Prefer the simpler non-accessory method when setup and cleanup outweigh the benefit.

TM7 hardware reaches speeds above 5, but this CLI's ordinary TTS annotation does not. Write higher-speed Blend/Turbo work as a direct mode instruction with fixed time and speed settings, for example `Blend 1 min/speed 10.` with `program: Blend`. Never describe gradually increasing or ramping the speed inside Blend or Turbo: the TM7 cannot do that. `varoma` is a Cookidoo wire token; on TM7, Varoma cooking is the Steam mode, not a temperature above 120°C. Do not emit Cookidoo `MODE` annotations.

Make each structured TTS action its own step containing only the setting marker, such as `15 sec/speed 3`. Put ingredient additions and essential action instructions in preceding short, unstructured steps. The CLI may strip a single action verb such as `Mix` or `Chop`, but rejects other surrounding prose because Cookidoo can otherwise render a checkbox instead of a TM7 Start button.

An official recipe's TM7 badge does not mean every operation happens in the mixing bowl. Preserve oven, hob, pan, resting, chilling, and accessory steps. A recipe tagged `TM7` by this CLI is user-created content, not Vorwerk-tested or TM7-certified.

The TM7 score measures structural usability, not food safety or recipe quality. Never present it as certification.

## Writing for the TM7 screen

- Write each recipe step as a short, actionable screen. Use one action or tightly related action group per step, normally one short sentence; at most two short sentences. Aim for 10–25 words and split longer instructions into separate steps rather than packing a paragraph into one step.
- Apply this to every step, including preparation, pan/oven work, accessory setup, manual modes, checks, and finishing. Split at changes of action, appliance, or cooking stage. Do not combine several stages with “meanwhile” in one long instruction; keep any necessary timing cue in the relevant short step.
- Include only what the cook needs to do now: ingredients and quantities, equipment/setup, settings, duration, a useful endpoint, or a necessary safety instruction. Keep those details explicit when splitting steps; brevity must not remove them.
- Omit commentary about expected eating experience, comparisons with other dishes, recipe-development rationale, provenance, validation, and API limitations from cooking steps. Do not write filler such as “Finely chopped stew beef will have a more substantial bite than ordinary ground beef.” Put genuinely useful background in `notes` or the chat; delete information that adds no practical value.
- Keep an optional correction in its own short step, starting with its condition, such as “If the sauce is too thick, stir in a splash of water.” Do not combine doneness checks, texture commentary, reduction, and thinning in one instruction.
- Keep ordinary structured TTS steps as the setting marker alone. For named modes, name the mode directly with its exact fixed settings; explain technical limitations outside the cooking steps.
- Review for readability separately from CLI validation. A valid payload or high TM7 score does not establish that the text is readable on the appliance. See the [short-step example](references/recipe-format.md#short-step-writing-example).

## Created-recipe images

Use a local PNG, JPEG, or WebP file no larger than 10 MiB. Prefer an original, crop-safe food photograph without text, logos, watermarks, branded packaging, or a Thermomix appliance unless the user explicitly requests a device in the scene. Do not imply that a generated image is an official Cookidoo photograph.

Upload directly after identifying the correct created recipe:

```bash
scripts/cookidoo recipe set-image CREATED_RECIPE_ID --file IMAGE_PATH
```

Do not ask for approval for image uploads. Show the generated or selected image when useful, identify the recipe id/title, upload it, then fetch the recipe with `--custom` and verify that its image is no longer the placeholder. Use `--dry-run` only when the user explicitly requests a preview without upload. The operation patches only the recipe image fields; if it reports that upload succeeded but attachment failed, report the failure before retrying because the uploaded asset may be orphaned.

## Meal-plan mutations

Dry run first:

```bash
scripts/cookidoo plan add 2026-08-05 RECIPE_ID
scripts/cookidoo plan remove 2026-08-05 RECIPE_ID
```

After approval, repeat with the returned token. Add `--custom` for user-created recipe ids.

## Deletion

List created recipes and identify the exact id before preparing deletion:

```bash
scripts/cookidoo recipe list-created
scripts/cookidoo recipe delete CREATED_RECIPE_ID
```

Show the exact id and title to the user before requesting approval. Commit only with the dry-run token.

## Errors

- Exit `2` or `input_error`: fix input, permissions, configuration, or JSON.
- Exit `3` or `relogin_needed=true`: ask the user to log in interactively; do not retry repeatedly.
- Cookidoo request failure: report the operation and that the unofficial internal API may have changed. Do not guess missing data.

See [references/commands.md](references/commands.md) for the complete CLI surface.
