# Fosse Falcons Girls Rugby website

Static site built with [Hugo](https://gohugo.io/) and hosted on GitHub Pages at <https://www.fossefalcons.co.uk/>.

## Project layout

| Path | Purpose |
|------|---------|
| `content/` | Page text (Markdown): `_index.md` (home), `about.md`, `age-groups.md`, `training.md`, `join.md`, `news/` |
| `layouts/` | HTML templates and partials (header, footer) |
| `assets/css/main.css` | Site styles |
| `static/` | Files copied as-is, e.g. `static/images/` |
| `hugo.toml` | Site title, base URL, contact email and navigation menu |
| `.github/workflows/hugo.yml` | Build and deploy workflow |

## Running locally

Install Hugo (extended edition, v0.168.0 or newer, e.g. `brew install hugo`), then:

```sh
hugo server
```

Open <http://localhost:1313/>. The page reloads as you edit files. To do a one-off production build into `public/`, run `hugo --gc --minify`.

## Editing content

- **Edit a page:** change the matching file in `content/`. Each file starts with a front matter block (`title: ...`) followed by Markdown text.
- **Add a news post:** create a file in `content/news/`, e.g. `content/news/match-report.md`:

  ```markdown
  ---
  title: "Match report"
  date: 2026-11-01
  ---

  Post text here.
  ```

  Or run `hugo new content news/match-report.md`.
- **Add images:** put them in `static/images/` and reference them as `/images/your-file.jpg`.
- **Change the menu or contact email:** edit `hugo.toml`.

## Publishing

Publishing is automatic. Pushing to the `master` branch runs the **Deploy Hugo site to GitHub Pages** workflow, which builds the site and deploys it.

1. Make your changes on a branch and open a pull request.
2. Merge the pull request into `master`.
3. Watch progress under the repository's **Actions** tab. The site updates in a minute or two.

You can also run the workflow manually from **Actions → Deploy Hugo site to GitHub Pages → Run workflow**.

### One-time setup

- In **Settings → Pages**, set **Source** to **GitHub Actions**.
- For the custom domain, set `www.fossefalcons.co.uk` under **Settings → Pages → Custom domain** and point a `CNAME` DNS record for `www` at `robertharris.github.io`. Enable **Enforce HTTPS** once the certificate is issued.

## Spond sync

`.github/workflows/sync-spond.yml` runs every 4 hours, runs `scripts/sync_spond.py` and commits `data/spond.json` (next fixture + next 2 training sessions per age group), then triggers the deploy.

- Add repo secrets `SPOND_USERNAME` and `SPOND_PASSWORD` (use a dedicated Spond account that is a member of the three groups).
- Fixtures are Spond events marked as a match; training is any non-match event whose title contains "train".
- Tag news posts for an age group with `age_groups: [u12]` (or `u14`, `u16`) in front matter.
- Local run: `pip install -r scripts/requirements.txt && SPOND_USERNAME=… SPOND_PASSWORD=… python scripts/sync_spond.py`

## Facebook news imports (approval required)

The **Review Facebook news** workflow checks approximately hourly (scheduled
Actions can be delayed) or on manual dispatch. It imports Page-authored text and
supported photos into news bundles and opens or updates a single pull request
from `automation/facebook-news`. **It never merges or publishes automatically.**
A human reviews and merges the PR into `master`; the existing Hugo workflow then
publishes it. The importer uses Python's standard library, with no extra packages.

### Access and one-time setup

1. Confirm that the club authorises republication of text and photographs on the
   public website, including appropriate safeguarding consent. Do not assume
   that Facebook publication grants permission to reuse a photograph.
2. A Page administrator should create a Meta developer app and obtain a Page
   access token for the club's Page. Typically `pages_show_list` is needed to
   select the managed Page and `pages_read_engagement` to read its posts/media.
   Verify requirements against Meta's current documentation and test retrieval
   of both a text post and a multi-photo post before enabling automation.
   No Facebook publishing or advertising permissions are required.
3. Meta developer registration and standard Graph API access are generally free.
   Depending on app roles and production usage, Advanced Access, App Review,
   business verification, a privacy policy and data-deletion information may be
   required. Development-mode access is not a guarantee of production approval.
4. In repository **Settings → Secrets and variables → Actions**, add the secret
   `FACEBOOK_PAGE_ACCESS_TOKEN`. Never put tokens in Git, issue comments or PRs.
   Add the repository variables below.
5. Under **Settings → Actions → General → Workflow permissions**, allow GitHub
   Actions to create pull requests. The workflow requests `contents: write` and
   `pull-requests: write`; organisation policies and branch rules must permit the
   automation branch. Protect `master` with human review as appropriate.

| Repository variable | Value |
| --- | --- |
| `FACEBOOK_IMPORT_ENABLED` | Set to `true` only after setup and consent checks; otherwise the job is skipped. |
| `FACEBOOK_PAGE_ID` | Numeric Page ID confirmed through Meta. The website currently links to `61551078683239`; verify that this is the Page you manage. |
| `FACEBOOK_API_VERSION` | An explicitly selected, currently supported Graph API version, in `vN.N` format. |
| `FACEBOOK_IMPORT_SINCE` | Required inclusive cutoff: `YYYY-MM-DD` or an ISO timestamp with timezone. Set a launch date to avoid importing the full history. |
| `FACEBOOK_IMPORT_MARKER` | Optional marker, default `#website`. Only matching posts are initially imported. |
| `FACEBOOK_IMPORT_ALL` | Set to `true` to import all supported Page-authored posts after the cutoff instead of filtering by marker. |

The source must be a managed **Page**, not a personal profile or private group.
The workflow needs neither your Facebook password nor a GitHub personal access
token. Keep the Page token restricted to the required read permissions.

### Review and content handling

- Articles retain the Facebook date, text, source link and a simple first-line
  title. Age-group markers `#u12`, `#u14` and `#u16` can associate news with teams.
- Supported photos are downloaded into the article bundle rather than hotlinked
  using expiring Facebook URLs. Shared posts, videos and other unsupported
  attachment types are skipped; check the workflow output and import state.
- `scripts/facebook-state.json` tracks source IDs, generated-file hashes and
  review warnings. Commit it with the articles and do not delete it to retry:
  it prevents duplicate imports and protects editorial changes.
- Source changes update previously generated articles only when their local
  bundles have not been edited. Otherwise the importer preserves the local
  version and flags the conflict for a human to reconcile. An unavailable
  Facebook post is flagged for review, never automatically deleted from the
  website. Absence or inaccessibility does not prove that a post was deleted.
- Review the state warnings alongside the news articles before merging.
  A review-only warning does not itself change the published article.
  Existing hand-written news is left alone.
- A later run updates the same open PR. Closing a PR without merging is not an
  opt-out: pause the integration or change the source selection to stop imports.
- Branch merge conflicts fail safely and require manual reconciliation. If
  repository policies require CI on bot-created PRs, note that the default
  `GITHUB_TOKEN` does not trigger other workflows; this workflow runs importer
  tests and a Hugo build itself before proposing changes.

### Maintenance and pausing

Set `FACEBOOK_IMPORT_ENABLED` to `false` to pause, and close any unwanted open
import PR. This does not remove published content. Disable the workflow entirely
if scheduled runs are no longer wanted.

Page tokens can expire or be revoked when account, app or Page permissions
change. On an authentication failure, obtain a replacement through Meta and
update the Actions secret; do not paste the token into logs. Investigate failed
workflow runs and review PRs regularly. API and download failures abort imports
before writing articles, keeping existing news intact. There are no live
Facebook credentials in this repository, so actual Page access and consent must
be verified by an administrator.

For local use, supply the same environment variables securely and run
`python scripts/sync_facebook.py`; an unset marker defaults to `#website`, and an
explicitly empty marker imports all supported posts. Run its offline tests with
`python -m unittest discover -s scripts -p 'test_sync_facebook.py'`.
