# Cookidoo CLI + Skill

A local JSON CLI and reusable Agent Skill for Cookidoo and Thermomix TM7 workflows—without an MCP server.

It can search and inspect Cookidoo recipes, manage the meal plan, validate TM7-aware recipe drafts, create private recipes, and upload custom recipe images. The included Skill teaches Codex or Claude the important difference between TM7 hardware, official Guided Cooking, and what a Cookidoo My Creations recipe can actually persist.

> Cookidoo does not publish an API for these workflows. This project uses reverse-engineered endpoints through `cookidoo-api`; Cookidoo changes can break it without notice. Review the terms applicable to your account.

## Install

Install the CLI and personal Skill for Codex:

```bash
curl -fsSL https://raw.githubusercontent.com/austinjk/cookidoo-cli-skill/main/install.sh | bash
```

For Claude Code instead:

```bash
curl -fsSL https://raw.githubusercontent.com/austinjk/cookidoo-cli-skill/main/install.sh | bash -s -- --target claude
```

For both:

```bash
curl -fsSL https://raw.githubusercontent.com/austinjk/cookidoo-cli-skill/main/install.sh | bash -s -- --target both
```

The installer:

- installs `uv` from Astral's official installer when necessary;
- installs the `cookidoo` CLI in an isolated Python 3.12 tool environment;
- installs `manage-cookidoo` under `$CODEX_HOME/skills` or `~/.codex/skills` for Codex;
- installs it under `$CLAUDE_HOME/skills` or `~/.claude/skills` for Claude Code;
- preserves an existing Skill as a timestamped backup when updating.

Re-run the same command to update. Use `--dry-run` to preview the resolved locations without changing anything.

## Authenticate

Cookidoo login is deliberately terminal-only:

```bash
cookidoo login --email you@example.com
cookidoo auth status --live
```

The password is read through a hidden interactive prompt, is never accepted as a CLI argument, and is never stored. Session cookies and configuration are stored with owner-only permissions beneath `~/.config/cookidoo-cli/` by default.

## Use

```bash
cookidoo search "chicken curry" --tm-model TM7
cookidoo recipe get RECIPE_ID
cookidoo plan show 2026-08-03
cookidoo recipe validate --file recipe.json
cookidoo recipe create --file recipe.json
cookidoo recipe set-image CREATED_RECIPE_ID --file dish.png
```

Recipe creation, deletion, and meal-plan changes return a short-lived, payload-bound dry-run token. Repeat the unchanged command with `--confirm TOKEN` only after reviewing the preview. Image upload is the intentionally narrow exception: it updates only the image fields and executes directly.

In Codex, ask naturally—for example, “Find a popular French TM7 chicken recipe” or “Create this recipe on Cookidoo.” In Claude Code, ask naturally or invoke `/manage-cookidoo`.

## TM7 behavior

The Skill avoids common TM7 mistakes:

- ordinary My Creations TTS supports only persistent time, supported temperature, speed through 5, and reverse;
- named modes and accessory functions remain visible manual handoffs instead of fake automatic actions;
- oven, hob, grill, resting, chilling, and accessory steps remain explicit;
- TM7 Cutter+, Blade Cover & Peeler, Thermomix Sensor, and TM7 Nester are treated as available but optional;
- generated recipe images are uploaded as user-owned content, not represented as official Cookidoo photography.

## Develop

```bash
uv sync --extra test
uv run --extra test pytest
uv run --extra test ruff check src tests
uv build
```

Install from a checkout while developing:

```bash
./install.sh --source . --target both
```

The CLI is MIT licensed. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the upstream projects that informed the implementation.
