from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, date, datetime
from http import HTTPStatus
from pathlib import Path
from typing import Any

from .auth import CookieStore
from .config import CookidooConfig
from .http import cookidoo_connector
from .models import RecipeDraft, jsonable

CLOUDINARY_API_KEY = "993585863591145"
CLOUDINARY_UPLOAD_PRESET = "prod-customer-recipe-signed"
CLOUDINARY_UPLOAD_URL = "https://api-eu.cloudinary.com/v1_1/vorwerk-users-gc/image/upload"


class CookidooError(RuntimeError):
    def __init__(self, message: str, *, relogin_needed: bool = False) -> None:
        super().__init__(message)
        self.relogin_needed = relogin_needed


def _sanitize_error(operation: str, exc: Exception) -> CookidooError:
    name = exc.__class__.__name__.lower()
    text = str(exc).lower()
    authentication = any(
        marker in name or marker in text
        for marker in ("auth", "unauthor", "forbidden", "401", "403", "redirect", "login")
    )
    if authentication:
        return CookidooError(
            f"{operation} failed because the Cookidoo session is missing or stale; run `cookidoo login`",
            relogin_needed=True,
        )
    status = getattr(exc, "status", None)
    suffix = f" (HTTP {status})" if isinstance(status, int) else ""
    return CookidooError(f"{operation} failed{suffix}; Cookidoo rejected the request or changed its internal API")


class CookidooClient:
    def __init__(
        self,
        config: CookidooConfig,
        upstream: Any | None = None,
    ) -> None:
        self.config = config
        self.cookie_store = CookieStore(config.cookie_file)
        self._upstream = upstream

    @staticmethod
    async def login(
        *,
        email: str,
        password: str,
        config: CookidooConfig,
    ) -> None:
        try:
            from aiohttp import ClientSession, CookieJar
            from cookidoo_api import Cookidoo
            from cookidoo_api.types import CookidooConfig as UpstreamConfig
            from cookidoo_api.types import CookidooLocalizationConfig
        except Exception as exc:  # pragma: no cover - import environment failure
            raise CookidooError("Cookidoo dependencies are not installed") from exc

        cookie_store = CookieStore(config.cookie_file)
        async with ClientSession(cookie_jar=CookieJar(unsafe=True), connector=cookidoo_connector(), trust_env=True) as session:
            upstream_config = UpstreamConfig(
                localization=CookidooLocalizationConfig(
                    country_code=config.country,
                    language=config.locale,
                    url=config.url,
                ),
                email=email,
                password=password,
            )
            upstream = Cookidoo(session, upstream_config)
            try:
                await upstream.login()
            except Exception as exc:
                raise _sanitize_error("login", exc) from exc
            entries = [
                {
                    "key": cookie.key,
                    "value": cookie.value,
                    "domain": cookie["domain"],
                    "path": cookie["path"],
                }
                for cookie in session.cookie_jar
            ]
        cookie_store.save_entries(entries)

    async def _get_upstream(self) -> Any:
        if self._upstream is not None:
            return self._upstream
        status = self.cookie_store.status()
        if not status.authenticated:
            raise CookidooError(status.message, relogin_needed=True)
        try:
            from aiohttp import ClientSession, CookieJar
            from cookidoo_api import Cookidoo
            from cookidoo_api.types import CookidooConfig as UpstreamConfig
            from cookidoo_api.types import CookidooLocalizationConfig
        except Exception as exc:  # pragma: no cover - import environment failure
            raise CookidooError("Cookidoo dependencies are not installed") from exc
        session = ClientSession(cookie_jar=CookieJar(unsafe=True), connector=cookidoo_connector(), trust_env=True)
        upstream_config = UpstreamConfig(
            localization=CookidooLocalizationConfig(
                country_code=self.config.country,
                language=self.config.locale,
                url=self.config.url,
            )
        )
        upstream = Cookidoo(session, upstream_config)
        upstream.load_cookies(Path(self.config.cookie_file).expanduser())
        self._upstream = upstream
        return upstream

    async def close(self) -> None:
        session = getattr(self._upstream, "_session", None)
        if session is not None and not session.closed:
            await session.close()

    async def verify_session(self) -> dict[str, Any]:
        upstream = await self._get_upstream()
        try:
            result = await upstream.get_recipes_in_calendar_week(datetime.now(UTC).date())
        except Exception as exc:
            raise _sanitize_error("session verification", exc) from exc
        return {"authenticated": True, "verified_live": True, "calendar_days": len(result or [])}

    async def search(
        self,
        query: str,
        *,
        language: str | None = None,
        country: str | None = None,
        ingredients: list[str] | None = None,
        exclude_ingredients: list[str] | None = None,
        max_total_time_minutes: int | None = None,
        servings: int | None = None,
        min_rating: float | None = None,
        tm_model: str | None = None,
        page: int = 1,
        limit: int = 10,
    ) -> dict[str, Any]:
        upstream = await self._get_upstream()
        params = {
            "query": query,
            "locale": (language or self.config.locale).split("-")[0].lower(),
            "languages": [language.split("-")[0].lower()] if language else None,
            "countries": [country.lower()] if country else None,
            "ingredients": ingredients or None,
            "exclude_ingredients": exclude_ingredients or None,
            "total_time": max_total_time_minutes * 60 if max_total_time_minutes else None,
            "portions": servings,
            "ratings": [str(int(min_rating))] if min_rating else None,
            "tmv": [(tm_model or self.config.default_tm_model).upper()] if (tm_model or self.config.default_tm_model) else None,
            "page": max(1, page),
            "page_size": min(50, max(1, limit)),
        }
        try:
            try:
                response = await upstream.search_recipes(**params)
            except TypeError:
                response = await upstream.search_recipes(query=query, locale=params["locale"])
        except Exception as exc:
            raise _sanitize_error("search", exc) from exc
        hits = response.recipes if hasattr(response, "recipes") else response
        requested_limit = params["page_size"]
        limited_hits = list(hits or [])[:requested_limit]
        return {"query": params, "results": [jsonable(item) for item in limited_hits]}

    async def get_recipe(self, recipe_id: str, *, custom: bool = False) -> dict[str, Any]:
        upstream = await self._get_upstream()
        primary = getattr(upstream, "get_custom_recipe", None) if custom else getattr(upstream, "get_recipe_details", None)
        secondary = getattr(upstream, "get_recipe_details", None) if custom else getattr(upstream, "get_custom_recipe", None)
        last_error: Exception | None = None
        for fetch in (primary, secondary):
            if fetch is None:
                continue
            try:
                return {"recipe": jsonable(await fetch(recipe_id)), "custom": fetch == getattr(upstream, "get_custom_recipe", None)}
            except Exception as exc:  # noqa: BLE001 - third-party client exposes inconsistent exception types
                last_error = exc
        raise _sanitize_error("get recipe", last_error or RuntimeError("No recipe endpoint"))

    async def list_created_recipes(self) -> dict[str, Any]:
        upstream = await self._get_upstream()
        try:
            if hasattr(upstream, "list_created_recipes"):
                result = await upstream.list_created_recipes(self.config.locale)
            else:
                result = await upstream._request_json(
                    "get",
                    upstream.api_endpoint / "created-recipes" / self.config.locale,
                    "list created recipes",
                )
        except Exception as exc:
            raise _sanitize_error("list created recipes", exc) from exc
        if isinstance(result, dict):
            items = result.get("items") or result.get("recipes") or result.get("data") or []
        else:
            items = result or []
        return {"results": [jsonable(item) for item in items]}

    async def get_collection(self, collection_id: str) -> dict[str, Any]:
        upstream = await self._get_upstream()
        try:
            result = await upstream._request_json(
                "get",
                upstream.api_endpoint / "collection" / collection_id,
                "get collection",
                accepted_statuses=(HTTPStatus.OK,),
            )
        except Exception as exc:
            raise _sanitize_error("get collection", exc) from exc
        return {"collection": jsonable(result)}

    async def get_plan(self, day: date) -> dict[str, Any]:
        upstream = await self._get_upstream()
        try:
            result = await upstream.get_recipes_in_calendar_week(day)
        except Exception as exc:
            raise _sanitize_error("get meal plan", exc) from exc
        return {"week_containing": day.isoformat(), "days": jsonable(result or [])}

    async def add_to_plan(self, day: date, recipe_id: str, *, custom: bool = False) -> dict[str, Any]:
        upstream = await self._get_upstream()
        try:
            if custom:
                result = await upstream.add_custom_recipes_to_calendar(day, [recipe_id])
            else:
                result = await upstream.add_recipes_to_calendar(day, [recipe_id])
        except Exception as exc:
            raise _sanitize_error("add recipe to meal plan", exc) from exc
        return {"added": True, "day": day.isoformat(), "recipe_id": recipe_id, "custom": custom, "result": jsonable(result)}

    async def remove_from_plan(self, day: date, recipe_id: str, *, custom: bool = False) -> dict[str, Any]:
        upstream = await self._get_upstream()
        try:
            if custom:
                result = await upstream.remove_custom_recipe_from_calendar(day, recipe_id)
            else:
                result = await upstream.remove_recipe_from_calendar(day, recipe_id)
        except Exception as exc:
            raise _sanitize_error("remove recipe from meal plan", exc) from exc
        return {"removed": True, "day": day.isoformat(), "recipe_id": recipe_id, "custom": custom, "result": jsonable(result)}

    async def create_recipe(self, draft: RecipeDraft) -> dict[str, Any]:
        upstream = await self._get_upstream()
        payload = draft.to_payload()
        try:
            created = await upstream._request_json(
                "post",
                upstream.api_endpoint / "created-recipes" / draft.language,
                "create recipe",
                json=payload["cookidoo"]["create"],
                accepted_statuses=(HTTPStatus.OK, HTTPStatus.CREATED),
            )
        except Exception as exc:
            raise _sanitize_error("create recipe shell", exc) from exc
        recipe_id = created.get("recipeId") or created.get("id") if isinstance(created, dict) else None
        if not recipe_id:
            raise CookidooError("Cookidoo create response did not contain a recipe id")

        await asyncio.sleep(5)
        try:
            updated = await upstream._request_json(
                "patch",
                upstream.api_endpoint / "created-recipes" / draft.language / str(recipe_id),
                "update recipe",
                json=payload["cookidoo"]["patch"],
                accepted_statuses=(HTTPStatus.OK, HTTPStatus.NO_CONTENT),
            )
        except Exception as exc:
            rollback_failed = False
            try:
                if hasattr(upstream, "remove_custom_recipe"):
                    await upstream.remove_custom_recipe(str(recipe_id))
                else:
                    await upstream._request_json(
                        "delete",
                        upstream.api_endpoint / "created-recipes" / draft.language / str(recipe_id),
                        "rollback recipe",
                        parse_response=False,
                    )
            except Exception:  # noqa: BLE001 - preserve the original update failure
                rollback_failed = True
            error = _sanitize_error("update created recipe", exc)
            if rollback_failed:
                raise CookidooError(
                    f"{error}; rollback also failed, so check Created Recipes for partial recipe {recipe_id}"
                ) from exc
            raise error from exc
        return {
            "created": True,
            "id": str(recipe_id),
            "locale": draft.language,
            "result": jsonable(updated or {"ok": True}),
        }

    async def set_recipe_image(
        self,
        recipe_id: str,
        *,
        image_bytes: bytes,
        filename: str,
        content_type: str,
        sha256: str,
    ) -> dict[str, Any]:
        """Upload an exact local image and attach it to an existing created recipe."""
        upstream = await self._get_upstream()
        timestamp = int(time.time())
        try:
            signature_payload = await upstream._request_json(
                "post",
                upstream.api_endpoint / "created-recipes" / self.config.locale / "image" / "signature",
                "sign recipe image upload",
                json={"source": "uw", "timestamp": timestamp},
                accepted_statuses=(HTTPStatus.OK,),
            )
            signature = signature_payload.get("signature") if isinstance(signature_payload, dict) else None
            if not signature:
                raise CookidooError("Cookidoo returned an invalid image-upload signature")
            uploaded = await self._upload_image_to_cloudinary(
                upstream,
                image_bytes=image_bytes,
                filename=filename,
                content_type=content_type,
                timestamp=timestamp,
                signature=str(signature),
            )
        except CookidooError:
            raise
        except Exception as exc:
            raise _sanitize_error("upload recipe image", exc) from exc

        public_id = uploaded.get("public_id") if isinstance(uploaded, dict) else None
        image_format = uploaded.get("format") if isinstance(uploaded, dict) else None
        if not public_id or not image_format:
            raise CookidooError("Cookidoo image upload did not return a usable image key")
        image_key = f"{public_id}.{image_format}"

        try:
            updated = await upstream._request_json(
                "patch",
                upstream.api_endpoint / "created-recipes" / self.config.locale / recipe_id,
                "attach recipe image",
                json={"image": image_key, "isImageOwnedByUser": True},
                accepted_statuses=(HTTPStatus.OK, HTTPStatus.NO_CONTENT),
            )
        except Exception as exc:
            error = _sanitize_error("attach recipe image", exc)
            raise CookidooError(
                f"{error}; the image upload succeeded but the recipe was not changed"
            ) from exc

        return {
            "updated": True,
            "recipe_id": recipe_id,
            "locale": self.config.locale,
            "image": image_key,
            "image_sha256": sha256,
            "result": jsonable(updated or {"ok": True}),
        }

    async def _upload_image_to_cloudinary(
        self,
        upstream: Any,
        *,
        image_bytes: bytes,
        filename: str,
        content_type: str,
        timestamp: int,
        signature: str,
    ) -> dict[str, Any]:
        try:
            from aiohttp import FormData
        except Exception as exc:  # pragma: no cover - required dependency import failure
            raise CookidooError("aiohttp is required for Cookidoo image uploads") from exc

        session = getattr(upstream, "_session", None)
        if session is None:
            raise CookidooError("Cookidoo client does not expose an authenticated upload session")
        form = FormData()
        form.add_field("file", image_bytes, filename=filename, content_type=content_type)
        form.add_field("api_key", CLOUDINARY_API_KEY)
        form.add_field("timestamp", str(timestamp))
        form.add_field("source", "uw")
        form.add_field("upload_preset", CLOUDINARY_UPLOAD_PRESET)
        form.add_field("signature", signature)
        async with session.post(CLOUDINARY_UPLOAD_URL, data=form) as response:
            response_text = await response.text()
            if response.status > 299:
                raise CookidooError("Cookidoo's image host rejected the upload")
        try:
            payload = json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise CookidooError("Cookidoo's image host returned an invalid response") from exc
        if not isinstance(payload, dict):
            raise CookidooError("Cookidoo's image host returned an invalid response")
        return payload

    async def delete_recipe(self, recipe_id: str) -> dict[str, Any]:
        upstream = await self._get_upstream()
        try:
            if hasattr(upstream, "remove_custom_recipe"):
                await upstream.remove_custom_recipe(recipe_id)
            else:
                await upstream._request_json(
                    "delete",
                    upstream.api_endpoint / "created-recipes" / self.config.locale / recipe_id,
                    "delete recipe",
                    parse_response=False,
                )
        except Exception as exc:
            raise _sanitize_error("delete recipe", exc) from exc
        return {"deleted": True, "recipe_id": recipe_id, "locale": self.config.locale}
