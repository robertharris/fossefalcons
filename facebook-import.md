# Facebook import: how it works

Setup, secrets and consent checks are in the [README](README.md#facebook-news-imports-approval-required).
Hashtag-to-tag rules are in [facebook.md](facebook.md). This page explains what
the workflow and scripts do, and how to import a post that was skipped.

## Overview

| File | Purpose |
| --- | --- |
| `.github/workflows/sync-facebook.yml` | Scheduled (hourly) and manual workflow **Review Facebook news**. |
| `scripts/sync_facebook.py` | Importer. Standard library only. Reads the Page via the Graph API and writes Hugo bundles. |
| `scripts/test_sync_facebook.py` | Offline unit tests (no network). Run on every workflow run before importing. |
| `scripts/facebook-state.json` | Tracks imported posts so editor changes are never overwritten. Commit it with the news. |
| `content/news/<slug>/` | Output: `index.md` plus `photo-N.<ext>` files per post. |

Nothing is published automatically. The workflow commits to the
`automation/facebook-news` branch and opens (or updates) a pull request. A
person reviews and merges it; merging publishes through the normal Hugo workflow.

## What gets imported

A post is imported only if **all** of these hold:

- Public: `is_published` is true, `is_hidden` is false and privacy is `EVERYONE`.
- Dated on or after `FACEBOOK_IMPORT_SINCE`.
- Contains the marker (`FACEBOOK_IMPORT_MARKER`, default `#news`), unless
  `FACEBOOK_IMPORT_ALL` is `true`.
- Has text and/or only supported photo attachments. Videos, shared links and
  other attachment types are skipped. Posts with neither text nor photos are skipped.

Posts named explicitly with the `posts` input (below) skip the date and marker
checks only; the public and attachment checks still apply.

## Run flow

1. Check out `master` and prepare the `automation/facebook-news` branch
   (created, or fetched and merged with `master`).
2. Run the unit tests.
3. Run `scripts/sync_facebook.py`:
   - Load `scripts/facebook-state.json`.
   - Fetch Page posts since the cutoff (paginated, with size limits), plus any
     explicitly requested posts and any tracked posts missing from the feed.
   - Filter, download photos, and render each post. All network work finishes
     before any file is written, so a failure leaves nothing half-written.
   - Write `content/news/<slug>/` bundles and update the state file.
4. Build with Hugo to validate the site.
5. Commit `content/news` and the state file, push the branch and open a PR if
   none exists.

## Protecting editor changes

For each imported post the state file stores a hash of the Facebook source and a
hash of the generated bundle. On later runs:

- Unchanged source: nothing happens.
- Changed source, bundle untouched: the bundle is regenerated.
- Bundle edited locally: the bundle is **kept**, and a warning is recorded in
  the state file for a reviewer.
- Post unavailable, no longer public, or no longer selected: the bundle is kept
  and a warning is recorded. Nothing is ever deleted automatically.
- An untracked folder already in the way: preserved, warning printed.

Always check `scripts/facebook-state.json` for `warning` entries in the PR.

## Importing a skipped post manually

Open **Actions → Review Facebook news → Run workflow**. Inputs:

| Input | Use |
| --- | --- |
| `list` | Tick to list recent untracked posts instead of importing. |
| `list_since` | With `list`: look back to this date (`YYYY-MM-DD`). Defaults to the cutoff. |
| `posts` | Post IDs or URLs to import, comma-separated. |

Typical use:

1. Run with **list** ticked. The log prints
   `post id | date | why not imported | text` for each untracked post, with
   reasons such as `missing #news`, `not public` or `unsupported attachment`.
   This mode only reads; it writes nothing and opens no PR.
2. Run again with the chosen ID in **posts**, e.g. `123456_789012`.

Accepted `posts` entries (page ID `123456` shown as an example):

- `123456_789012` (full ID) or `789012` (post number only)
- `https://www.facebook.com/123456/posts/789012`

`pfbid...` URLs and page-name URLs cannot be converted; use the numeric ID from
the list output. A requested post that cannot be found stops the run with an
error; one that is found but not public is skipped with a warning.

From the CLI:

```sh
gh workflow run sync-facebook.yml -f list=true
gh workflow run sync-facebook.yml -f posts="123456_789012"
```

The workflow job only runs when the repository variable
`FACEBOOK_IMPORT_ENABLED` is `true`.

## Running locally

```sh
export FACEBOOK_PAGE_ID=... FACEBOOK_API_VERSION=v23.0 \
       FACEBOOK_IMPORT_SINCE=2026-01-01 FACEBOOK_PAGE_ACCESS_TOKEN=...
python3 scripts/sync_facebook.py            # import
python3 scripts/sync_facebook.py --list     # list untracked posts only
FACEBOOK_IMPORT_POSTS="789012" python3 scripts/sync_facebook.py
python3 -m unittest discover -s scripts -p 'test_sync_facebook.py'
```

Optional: `FACEBOOK_IMPORT_MARKER` (default `#news`, empty to disable).

## Generated article format

- Front matter: `title` (first line of the post), `date`, `description`, and
  `tags` derived from hashtags.
- Body: remaining text with Markdown/HTML/shortcodes neutralised; `http(s)` URLs
  become links.
- Photos as `photo-N.<ext>` (JPEG, PNG, GIF or WebP, validated by content).
- A closing link to the original Facebook post.

Safety limits cap pages, posts, photos and image sizes. Error messages never
include tokens or signed URLs.
