# CLI commands

All successful and failed commands emit one JSON document on stdout. Add global `--pretty` before the resource name for formatted output.

## Authentication

```text
cookidoo login [--email EMAIL] [--country us] [--locale en-US]
               [--url URL] [--tm-model TM7]
cookidoo auth status [--live]
```

Login is interactive. No password argument or password environment variable is supported.

## Catalogue reads

```text
cookidoo search QUERY [--language LOCALE] [--country CODE]
                [--ingredient TEXT]... [--exclude-ingredient TEXT]...
                [--max-total-minutes N] [--servings N] [--min-rating N]
                [--tm-model TM5|TM6|TM7] [--page N] [--limit N]
cookidoo recipe get ID [--custom]
cookidoo recipe list-created
cookidoo collection get ID
cookidoo plan show YYYY-MM-DD
```

## Recipe files and mutations

```text
cookidoo recipe validate --file PATH|-
cookidoo recipe create --file PATH|- [--confirm TOKEN]
cookidoo recipe set-image ID --file PATH [--dry-run]
cookidoo recipe delete ID [--confirm TOKEN]
cookidoo plan add YYYY-MM-DD ID [--custom] [--confirm TOKEN]
cookidoo plan remove YYYY-MM-DD ID [--custom] [--confirm TOKEN]
```

For recipe creation, deletion, and meal-plan changes, omitting `--confirm` always creates a dry run. A confirmation token is short-lived, single-use, and valid only for the exact operation and payload that generated it.

`recipe set-image` accepts PNG, JPEG, or WebP files up to 10 MiB and uploads immediately without confirmation. It hashes and uploads the bytes read during that invocation, then patches only `image` and `isImageOwnedByUser`; it does not rewrite ingredients, steps, TM model, or timings. Pass `--dry-run` only when a non-uploading local preview is useful.

## Exit codes

- `0`: successful request or dry run
- `1`: Cookidoo request failure
- `2`: invalid input, configuration, JSON, or file permissions
- `3`: authentication is missing or stale
