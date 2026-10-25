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
