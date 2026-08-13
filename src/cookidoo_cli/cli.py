from __future__ import annotations

import argparse
import asyncio
import getpass
import hashlib
import json
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from .auth import CookieStore
from .client import CookidooClient, CookidooError
from .config import DEFAULT_CONFIG_PATH, ConfigStore, CookidooConfig, cookidoo_base_url
from .confirmations import ConfirmationStore
from .models import RecipeDraft
from .tm7 import validate_tm7_recipe

ClientFactory = Callable[[CookidooConfig], CookidooClient]

MAX_RECIPE_IMAGE_BYTES = 10 * 1024 * 1024


def _json_input(path: str) -> dict[str, Any]:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise TypeError("Input must be a JSON object")
    return payload


def _day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid date {value!r}; expected YYYY-MM-DD") from exc


def _image_input(path: str) -> tuple[dict[str, Any], bytes]:
    image_path = Path(path).expanduser().resolve()
    image_bytes = image_path.read_bytes()
    if not image_bytes:
        raise ValueError("Recipe image is empty")
    if len(image_bytes) > MAX_RECIPE_IMAGE_BYTES:
        raise ValueError("Recipe image exceeds the 10 MiB upload limit")
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        content_type = "image/png"
    elif image_bytes.startswith(b"\xff\xd8\xff"):
        content_type = "image/jpeg"
    elif image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        content_type = "image/webp"
    else:
        raise ValueError("Recipe image must be a PNG, JPEG, or WebP file")
    metadata = {
        "path": str(image_path),
        "filename": image_path.name,
        "content_type": content_type,
        "size_bytes": len(image_bytes),
        "sha256": hashlib.sha256(image_bytes).hexdigest(),
    }
    return metadata, image_bytes


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cookidoo", description="Local JSON CLI for Cookidoo and TM7 workflows.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to the private Cookidoo config file.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    sub = parser.add_subparsers(dest="resource", required=True)

    login = sub.add_parser("login", help="Authenticate interactively and store only Cookidoo session cookies.")
    login.add_argument("--email")
    login.add_argument("--country", default="us")
    login.add_argument("--locale", default="en-US")
    login.add_argument("--url", help="Cookidoo foundation URL; normally derived from country and locale.")
    login.add_argument("--tm-model", default="TM7", choices=("TM5", "TM6", "TM7"))

    auth = sub.add_parser("auth", help="Inspect the Cookidoo session.")
    auth_sub = auth.add_subparsers(dest="action", required=True)
    auth_status = auth_sub.add_parser("status")
    auth_status.add_argument("--live", action="store_true", help="Make a read-only Cookidoo request to verify cookies.")

    search = sub.add_parser("search", help="Search the Cookidoo catalogue.")
    search.add_argument("query")
    search.add_argument("--language")
    search.add_argument("--country")
    search.add_argument("--ingredient", action="append", default=[])
    search.add_argument("--exclude-ingredient", action="append", default=[])
    search.add_argument("--max-total-minutes", type=int)
    search.add_argument("--servings", type=int)
    search.add_argument("--min-rating", type=float)
    search.add_argument("--tm-model", choices=("TM5", "TM6", "TM7"))
    search.add_argument("--page", type=int, default=1)
    search.add_argument("--limit", type=int, default=10)

    recipe = sub.add_parser("recipe", help="Read, validate, create, update, or delete recipes.")
    recipe_sub = recipe.add_subparsers(dest="action", required=True)
    recipe_get = recipe_sub.add_parser("get")
    recipe_get.add_argument("recipe_id")
    recipe_get.add_argument("--custom", action="store_true")
    recipe_sub.add_parser("list-created")
    recipe_validate = recipe_sub.add_parser("validate")
    recipe_validate.add_argument("--file", required=True, help="Recipe JSON path or - for stdin.")
    recipe_create = recipe_sub.add_parser("create")
    recipe_create.add_argument("--file", required=True, help="Recipe JSON path or - for stdin.")
    recipe_create.add_argument("--confirm", help="Confirmation token returned by the matching dry run.")
    recipe_image = recipe_sub.add_parser("set-image", help="Upload a local image to an existing created recipe.")
    recipe_image.add_argument("recipe_id")
    recipe_image.add_argument("--file", required=True, help="PNG, JPEG, or WebP image path (10 MiB maximum).")
    recipe_image.add_argument("--dry-run", action="store_true", help="Validate and preview without uploading.")
    recipe_delete = recipe_sub.add_parser("delete")
    recipe_delete.add_argument("recipe_id")
    recipe_delete.add_argument("--confirm")

    plan = sub.add_parser("plan", help="Read or change the Cookidoo meal plan.")
    plan_sub = plan.add_subparsers(dest="action", required=True)
    plan_show = plan_sub.add_parser("show")
    plan_show.add_argument("day")
    for action in ("add", "remove"):
        command = plan_sub.add_parser(action)
        command.add_argument("day")
        command.add_argument("recipe_id")
        command.add_argument("--custom", action="store_true")
        command.add_argument("--confirm")

    collection = sub.add_parser("collection", help="Read a Cookidoo collection.")
    collection_sub = collection.add_subparsers(dest="action", required=True)
    collection_get = collection_sub.add_parser("get")
    collection_get.add_argument("collection_id")

    return parser


def _dry_run(store: ConfirmationStore, operation: str, payload: dict[str, Any], preview: dict[str, Any]) -> dict[str, Any]:
    confirmation = store.create(operation, payload)
    return {
        "ok": True,
        "dry_run": True,
        "operation": operation,
        "preview": preview,
        "confirmation": confirmation.to_dict(),
        "next": f"Repeat the same command with --confirm {confirmation.token} only after explicit user approval.",
    }


async def _execute(args: argparse.Namespace, client_factory: ClientFactory = CookidooClient) -> tuple[int, dict[str, Any]]:
    config_store = ConfigStore(args.config)

    if args.resource == "login":
        if not sys.stdin.isatty():
            raise ValueError("Login requires an interactive terminal; run `cookidoo login --email you@example.com`")
        email = args.email or input("Cookidoo email: ").strip()
        password = getpass.getpass("Cookidoo password: ")
        config = CookidooConfig(
            country=args.country,
            locale=args.locale,
            url=args.url or cookidoo_base_url(args.country, args.locale),
            default_tm_model=args.tm_model,
        )
        await CookidooClient.login(email=email, password=password, config=config)
        config_store.save(config)
        return 0, {
            "ok": True,
            "authenticated": True,
            "site": {"country": config.country, "locale": config.locale, "url": config.url},
            "cookie_file": config.cookie_file,
            "password_stored": False,
        }

    if args.resource == "recipe" and args.action == "validate":
        existing_config = config_store.load_or_none()
        default_tm_model = existing_config.default_tm_model if existing_config else "TM7"
        draft = RecipeDraft.from_dict(_json_input(args.file), default_tm_model=default_tm_model)
        validation = validate_tm7_recipe(draft)
        return (0 if validation["valid"] else 2), {
            "ok": validation["valid"],
            "recipe": draft.to_dict(),
            "validation": validation,
        }

    config = config_store.load()
    client = client_factory(config)
    confirmation_store = ConfirmationStore(config.pending_dir)
    try:
        if args.resource == "auth" and args.action == "status":
            local = CookieStore(config.cookie_file).status().to_dict()
            if args.live and local["authenticated"]:
                local.update(await client.verify_session())
            return (0 if local["authenticated"] else 3), {"ok": local["authenticated"], **local}

        if args.resource == "search":
            result = await client.search(
                args.query,
                language=args.language,
                country=args.country,
                ingredients=args.ingredient,
                exclude_ingredients=args.exclude_ingredient,
                max_total_time_minutes=args.max_total_minutes,
                servings=args.servings,
                min_rating=args.min_rating,
                tm_model=args.tm_model,
                page=args.page,
                limit=args.limit,
            )
            return 0, {"ok": True, **result}

        if args.resource == "collection" and args.action == "get":
            return 0, {"ok": True, **await client.get_collection(args.collection_id)}

        if args.resource == "recipe":
            if args.action == "get":
                return 0, {"ok": True, **await client.get_recipe(args.recipe_id, custom=args.custom)}
            if args.action == "list-created":
                return 0, {"ok": True, **await client.list_created_recipes()}
            if args.action == "create":
                draft = RecipeDraft.from_dict(_json_input(args.file), default_tm_model=config.default_tm_model)
                validation = validate_tm7_recipe(draft)
                payload = draft.to_payload()
                operation = "recipe.create"
                if not args.confirm:
                    return 0, _dry_run(
                        confirmation_store,
                        operation,
                        payload,
                        {"recipe": draft.to_dict(), "validation": validation, "cookidoo_payload": payload},
                    )
                confirmation_store.consume(args.confirm, operation, payload)
                result = await client.create_recipe(draft)
                return 0, {"ok": True, "dry_run": False, "validation": validation, **result}
            if args.action == "set-image":
                image, image_bytes = _image_input(args.file)
                payload = {"recipe_id": args.recipe_id, "locale": config.locale, "image": image}
                if args.dry_run:
                    return 0, {"ok": True, "dry_run": True, "operation": "recipe.set-image", "preview": payload}
                result = await client.set_recipe_image(
                    args.recipe_id,
                    image_bytes=image_bytes,
                    filename=image["filename"],
                    content_type=image["content_type"],
                    sha256=image["sha256"],
                )
                return 0, {"ok": True, "dry_run": False, **result}
            if args.action == "delete":
                payload = {"recipe_id": args.recipe_id, "locale": config.locale}
                operation = "recipe.delete"
                if not args.confirm:
                    return 0, _dry_run(confirmation_store, operation, payload, payload)
                confirmation_store.consume(args.confirm, operation, payload)
                return 0, {"ok": True, "dry_run": False, **await client.delete_recipe(args.recipe_id)}

        if args.resource == "plan":
            selected_day = _day(args.day)
            if args.action == "show":
                return 0, {"ok": True, **await client.get_plan(selected_day)}
            payload = {
                "day": selected_day.isoformat(),
                "recipe_id": args.recipe_id,
                "custom": args.custom,
            }
            operation = f"plan.{args.action}"
            if not args.confirm:
                return 0, _dry_run(confirmation_store, operation, payload, payload)
            confirmation_store.consume(args.confirm, operation, payload)
            if args.action == "add":
                result = await client.add_to_plan(selected_day, args.recipe_id, custom=args.custom)
            else:
                result = await client.remove_from_plan(selected_day, args.recipe_id, custom=args.custom)
            return 0, {"ok": True, "dry_run": False, **result}

        raise ValueError("Unsupported command")
    finally:
        await client.close()


def main(argv: list[str] | None = None, *, client_factory: ClientFactory = CookidooClient) -> int:
    args = _parser().parse_args(argv)
    try:
        code, payload = asyncio.run(_execute(args, client_factory=client_factory))
    except CookidooError as exc:
        code = 3 if exc.relogin_needed else 1
        payload = {
            "ok": False,
            "error": {"type": "cookidoo_error", "message": str(exc), "relogin_needed": exc.relogin_needed},
        }
    except (FileNotFoundError, PermissionError, TypeError, ValueError, json.JSONDecodeError) as exc:
        code = 2
        payload = {"ok": False, "error": {"type": "input_error", "message": str(exc)}}
    print(json.dumps(payload, indent=2 if args.pretty else None, sort_keys=args.pretty, ensure_ascii=False))
    return code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
