# Fosse Falcons Girls Rugby website

Static site built with [Hugo](https://gohugo.io/) and hosted on GitHub Pages at <https://www.fossefalcons.co.uk/>.

## Project layout

| Path | Purpose |
|------|---------|
| `content/` | Page text (Markdown): `_index.md` (home), `about.md`, `age-groups/`, `training.md`, `join.md`, `sponsors.md`, `news/` |
| `data/sponsors.yaml` | Sponsor details shared by the Sponsors page and footer |
| `data/documents.yaml` | Titles, file paths and descriptions for the Documents page |
| `layouts/` | HTML templates and partials (header, footer) |
| `assets/css/main.css` | Site styles |
| `static/` | Files copied as-is, e.g. `static/images/` and `static/files/` |
| `hugo.toml` | Site title, base URL, contact email and navigation menu |
| `.github/workflows/hugo.yml` | Build and deploy workflow |

## Running locally

Install Hugo (extended edition, v0.168.0 or newer, e.g. `brew install hugo`), then:

```sh
hugo server
```

Open <http://localhost:1313/>. The page reloads as you edit files. To do a one-off production build into `public/`, run `hugo --gc --minify`.

## Editing content

- **Edit a page:** change the matching file in `content/`. Each file starts with a front matter block (`title: ...`) followed by Markdown text. Include a unique `description` summarising the page; the site uses it as the page's meta description for search engines.
- **Add a news post:** create a file in `content/news/`, e.g. `content/news/match-report.md`:

  ```markdown
  ---
  title: "Match report"
  description: "A brief summary of the match, including the teams and key highlights."
  date: 2026-11-01
  ---

  Post text here.
  ```

  Or run `hugo new content news/match-report.md`.
- **Add images:** put them in `static/images/` and reference them as `/images/your-file.jpg`.
- **Add documents:** put each file in `static/files/`, then add its title, path, and description to `data/documents.yaml`. The Documents page is available at `/documents/`, and each title links directly to its file. For example:

  ```yaml
  - title: "Club registration form"
    path: "files/club-registration-form.pdf"
    description: "Registration form for new players."
  ```

- **Edit coach profiles:** update the profile bundles in `content/coaches/` and replace `static/images/coaches/profile-placeholder.svg` with approved coach photos. Change each profile's `photo` and `photo_alt` fields to match its image, replace its placeholder biography, and set `age_group_id` to the matching age-group `group` ID. Age-group coach lists are generated from these IDs; set `head_coach` to a listed coach's profile slug.
- **Favicon:** `static/images/favicon.png` is a square, opaque white image with the falcon and text in black. It is separate from `logo-transparent.png`, which is still used in the header and home page.
- **Change the menu or contact email:** edit `hugo.toml`.
- **Edit sponsors:** update `data/sponsors.yaml` to change sponsor descriptions, website links and logos. The footer shows linked logos and sponsor roles; descriptions appear only on the Sponsors page. Keep the headline sponsor first with `headline: true`. Logos are stored locally in `static/images/sponsors/`, sourced from the sponsors' official websites: [Jewson](https://www.jewson.co.uk/) and [RPGL](https://rpgl.co.uk/).
- **Add sponsor news:** add `tags: [sponsor]` to a news post's front matter. It will appear on the Sponsors page, newest first, as well as in the usual news listings. Posts can also have other tags and `age_groups`.

## Publishing

Publishing is automatic. Pushing to the `master` branch runs the **Deploy Hugo site to GitHub Pages** workflow, which builds the site and deploys it.

1. Make your changes on a branch and open a pull request.
2. Merge the pull request into `master`.
3. Watch progress under the repository's **Actions** tab. The site updates in a minute or two.

You can also run the workflow manually from **Actions → Deploy Hugo site to GitHub Pages → Run workflow**.

### One-time setup

- In **Settings → Pages**, set **Source** to **GitHub Actions**.
- For the custom domain, set `www.fossefalcons.co.uk` under **Settings → Pages → Custom domain** and point a `CNAME` DNS record for `www` at `robertharris.github.io`. Enable **Enforce HTTPS** once the certificate is issued.

### Legacy URLs

Hugo aliases preserve the original Google Sites URLs: `/home/` redirects to `/`, `/welcome/` to `/join/`, and `/contact/` to `/about/`. These are generated HTML pages with immediate meta-refresh redirects and canonical links, not HTTP 301 redirects. The aliases are defined in the destination pages' front matter and take effect when the Hugo site is deployed on the custom domain.

## Spond sync

`.github/workflows/sync-spond.yml` runs every 4 hours, runs `scripts/sync_spond.py` and commits `data/spond.json` (next fixture + next 2 training sessions per age group), then triggers the deploy.

- Add repo secrets `SPOND_USERNAME` and `SPOND_PASSWORD` (use a dedicated Spond account that is a member of the three groups).
- Fixtures are Spond events marked as a match; training is any non-match event whose title contains "train".
- Tag news posts for an age group with `age_groups: [u12]` (or `u14`, `u16`) in front matter.
- Local run: `pip install -r scripts/requirements.txt && SPOND_USERNAME=… SPOND_PASSWORD=… python scripts/sync_spond.py`
