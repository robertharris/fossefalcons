# Photo gallery

The gallery lives at `/gallery/` and is built automatically from the photos in `assets/gallery/`.

## Adding photos

1. Copy JPG, PNG or WebP files into `assets/gallery/` (or a subfolder, see [Credits](#credits)).
2. Run `hugo server` to preview, then commit and push.

Notes:

- Originals can be full size. Hugo creates a 600px-wide thumbnail and a 1800px-wide full-screen version (both WebP) at build time, so large originals only slow the build, not the page.
- Photos are sorted by folder, then filename. Prefix filenames with a date or number (`2025-03-01-match-01.jpg`) to control order.
- Photos are not served as static files; only the generated versions are published.
- With no photos, the page shows "No photos have been added yet".

## Credits

To credit one photographer for many photos, put their photos in a subfolder named after them:

```
assets/gallery/studio-spicer/IMG_0001.jpg
assets/gallery/studio-spicer/IMG_0002.jpg
```

Then add one entry in `data/gallery.yaml`, using the folder name as the key:

```yaml
photographers:
  studio-spicer:
    credit: "Studio Spicer"
    credit_url: "https://studiospicer.com"   # optional; must start with http(s)://
```

All photos in that folder show the credit. Photos directly in `assets/gallery/` have no credit unless listed under `photos`.

## Per-photo details

Optional details and overrides go under `photos` in `data/gallery.yaml`, keyed by path inside `assets/gallery/`:

```yaml
photos:
  "studio-spicer/IMG_0001.jpg":
    alt: "Falcons U13s lining up for a scrum"
    caption: "U13s v Leicester Lionesses"
    credit: "Someone else"        # overrides the folder's credit
    credit_url: "https://example.com"
```

| Field | Used for |
| --- | --- |
| `alt` | Image alt text for screen readers (falls back to `caption`). Please add one where possible. |
| `caption` | Shown under the photo in the lightbox. |
| `credit` | Shown as "Photo: …" on the grid and in the lightbox. |
| `credit_url` | Links the credit in the lightbox. |

Per-photo values override the folder's values field by field.

## Behaviour

- **Grid:** responsive masonry columns with lazy-loaded thumbnails. On hover or keyboard focus the credit appears over the photo; on touch devices it is always visible.
- **Lightbox:** clicking a photo opens it full screen. Use the arrows, ← / →, or swipe to move between photos (it wraps around), and the close button, Esc or a click outside the photo to close. Focus is kept inside the viewer and returned to the thumbnail on close.
- **No JavaScript:** thumbnails link directly to the full-size image.
- Ctrl/Cmd/Shift-click opens the full-size image normally instead of the lightbox.

## Files

| File | Purpose |
| --- | --- |
| `content/gallery.md` | The page itself (uses the `gallery` layout) |
| `layouts/gallery.html` | Builds the grid, thumbnails and credits |
| `assets/js/gallery.js` | Lightbox |
| `assets/css/main.css` | Grid and lightbox styles (`.gallery-*`, `.lightbox`, `.lb-*`) |
| `data/gallery.yaml` | Photographer credits and per-photo details |
