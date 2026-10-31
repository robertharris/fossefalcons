#!/usr/bin/env python3
"""Import marked public Facebook Page posts as locally owned Hugo bundles.

Only standard-library modules are used. Network work completes before any files
are written; an unavailable tracked post is a review signal, never a deletion.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import string
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
FIELDS = ("id,message,created_time,permalink_url,is_published,is_hidden,privacy,"
          "attachments{media_type,type,media,subattachments{type,media_type,media}}")
TIMEOUT = 30
MAX_PAGES = 100
MAX_POSTS = 1000
MAX_PHOTOS = 50
MAX_TOTAL_PHOTOS = 1000
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_IMAGE_BYTES = 100 * 1024 * 1024
MAX_API_BYTES = 10 * 1024 * 1024
MAX_REDIRECTS = 5


class SyncError(Exception):
    """An error whose underlying network details must not reach CLI logs."""


class Unavailable(SyncError):
    """A tracked object lookup returned Graph error 100."""


def timestamp(value):
    if not isinstance(value, str) or not re.match(r"^\d{4}-\d\d-\d\d(?:T|$)", value):
        raise SyncError("Invalid ISO cutoff or post timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        raise SyncError("Invalid ISO cutoff or post timestamp") from None


def config(env):
    page = env.get("FACEBOOK_PAGE_ID", "")
    token = env.get("FACEBOOK_PAGE_ACCESS_TOKEN", "")
    version = env.get("FACEBOOK_API_VERSION", "")
    since = env.get("FACEBOOK_IMPORT_SINCE", "")
    if (not re.fullmatch(r"[0-9]+", page)
            or not re.fullmatch(r"v[0-9]+\.[0-9]+", version)
            or not token.strip() or any(c.isspace() for c in token)):
        raise SyncError("Invalid Facebook configuration")
    cutoff = timestamp(since)
    return {
        "page": page, "token": token, "version": version,
        "since": cutoff.isoformat(), "cutoff": cutoff,
        "marker": env.get("FACEBOOK_IMPORT_MARKER", "#news"),
    }


def image_url(url):
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        valid = (parts.scheme == "https"
                 and any(host.endswith("." + domain)
                         for domain in ("fbcdn.net", "fbsbx.com"))
                 and not parts.username and not parts.password
                 and parts.port in (None, 443) and not parts.fragment)
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise SyncError("Unsafe image URL")
    return url


class SafeRedirects(HTTPRedirectHandler):
    def __init__(self, images=False):
        super().__init__()
        self.images = images
        self.count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.count += 1
        if not self.images or self.count > MAX_REDIRECTS:
            raise SyncError("Unexpected or excessive redirects")
        image_url(newurl)
        # Construct a fresh request: never forward Graph authorization headers.
        return Request(newurl, headers={"User-Agent": "Facebook-Hugo-Importer"})


def request_bytes(url, *, token=None, image=False):
    if image:
        image_url(url)
    else:
        parts = urlsplit(url)
        if (parts.scheme != "https" or parts.netloc != "graph.facebook.com"
                or "access_token" in parse_qs(parts.query)):
            raise SyncError("Unsafe Graph URL")
    headers = {"User-Agent": "Facebook-Hugo-Importer"}
    if token is not None and not image:
        headers["Authorization"] = "Bearer " + token
    opener = build_opener(SafeRedirects(images=image))
    limit = MAX_IMAGE_BYTES if image else MAX_API_BYTES
    try:
        response = opener.open(Request(url, headers=headers), timeout=TIMEOUT)
    except HTTPError as error:
        if image:
            raise SyncError("Image request failed") from None
        response = error
    except (URLError, OSError, ValueError):
        raise SyncError("Network request failed") from None
    with response:
        payload = response.read(limit + 1)
        if len(payload) > limit:
            raise SyncError("Response size limit exceeded")
        mime = response.headers.get_content_type()
        status = response.code
    return status, mime, payload


class Graph:
    def __init__(self, cfg):
        self.cfg = cfg

    def get(self, resource, params, *, lookup=False):
        url = ("https://graph.facebook.com/" + self.cfg["version"] + "/"
               + resource + "?" + urlencode(params))
        status, _, payload = request_bytes(url, token=self.cfg["token"])
        try:
            data = json.loads(payload)
        except (ValueError, UnicodeError):
            raise SyncError("Invalid Graph response") from None
        if not isinstance(data, dict):
            raise SyncError("Invalid Graph response")
        error = data.get("error")
        if error:
            if isinstance(error, dict) and error.get("code") == 100 and lookup:
                raise Unavailable("Tracked post unavailable")
            raise SyncError("Graph request failed")
        if status != 200:
            raise SyncError("Graph request failed")
        return data

    def posts(self):
        result = {}
        seen_cursors = set()
        params = {"fields": FIELDS, "since": self.cfg["since"], "limit": "100"}
        for _ in range(MAX_PAGES):
            data = self.get(self.cfg["page"] + "/posts", params)
            rows = data.get("data")
            if not isinstance(rows, list):
                raise SyncError("Invalid post list")
            for post in rows:
                if not isinstance(post, dict):
                    raise SyncError("Invalid post")
                post_id = validate_id(post.get("id"), self.cfg["page"])
                if post_id in result and result[post_id] != post:
                    raise SyncError("Conflicting duplicate post")
                result[post_id] = post
                if len(result) > MAX_POSTS:
                    raise SyncError("Post limit exceeded")
            paging = data.get("paging", {})
            if not isinstance(paging, dict):
                raise SyncError("Invalid pagination")
            if not paging.get("next"):
                return result
            # The supplied next URL is deliberately never parsed or followed.
            cursors = paging.get("cursors", {})
            after = cursors.get("after") if isinstance(cursors, dict) else None
            if not isinstance(after, str) or not after or after in seen_cursors:
                raise SyncError("Invalid pagination cursor")
            seen_cursors.add(after)
            params = dict(params, after=after)
        raise SyncError("Page limit exceeded")

    def post(self, post_id):
        return self.get(post_id, {"fields": FIELDS}, lookup=True)


def validate_id(post_id, page):
    if not isinstance(post_id, str) or not re.fullmatch(
            re.escape(page) + r"_[0-9]+", post_id):
        raise SyncError("Invalid post identity")
    return post_id


def permalink(url, post_id, page):
    try:
        parts = urlsplit(url)
        valid = (parts.scheme == "https"
                 and parts.netloc in ("facebook.com", "www.facebook.com", "m.facebook.com")
                 and not parts.fragment)
        path_match = re.fullmatch(r"/[A-Za-z0-9.]+/posts/([A-Za-z0-9]+)/?", parts.path)
        suffix = post_id.split("_")[1]
        if path_match:
            target = path_match.group(1)
            valid = valid and (target == suffix or re.fullmatch(r"pfbid[A-Za-z0-9]+", target))
        elif parts.path in ("/permalink.php", "/story.php"):
            query = parse_qs(parts.query)
            targets = query.get("story_fbid", [])
            valid = (valid and len(targets) == 1
                     and (targets[0] == suffix or re.fullmatch(r"pfbid[A-Za-z0-9]+", targets[0]))
                     and query.get("id") == [page])
        else:
            valid = False
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise SyncError("Invalid Facebook permalink")
    # Drop tracking parameters from normal post permalinks.
    if path_match:
        return "https://www.facebook.com" + parts.path
    return ("https://www.facebook.com" + parts.path + "?"
            + urlencode({"story_fbid": targets[0], "id": page}))


def attachment_rows(container):
    if not isinstance(container, dict) or not isinstance(container.get("data"), list):
        raise SyncError("Invalid attachments")
    if container.get("paging", {}).get("next"):
        # Never silently publish an incomplete album or attachment set.
        raise SyncError("Paginated attachments are not supported")
    return container["data"]


def photos(post):
    """Return image specs, or None for a shared/link/video/unknown post."""
    if "attachments" not in post:
        return []
    result = []
    for attachment in attachment_rows(post["attachments"]):
        if not isinstance(attachment, dict):
            raise SyncError("Invalid attachment")
        media_type = attachment.get("media_type", "").lower()
        kind = attachment.get("type", "").lower()
        if kind == "album" and media_type in ("album", "photo"):
            children = attachment_rows(attachment.get("subattachments"))
        elif kind == "photo" and media_type == "photo":
            children = [attachment]
        else:
            return None
        for child in children:
            if (not isinstance(child, dict) or child.get("type") != "photo"
                    or child.get("media_type", "photo") != "photo"):
                return None
            try:
                image = child["media"]["image"]
                src = image_url(image["src"])
            except (KeyError, TypeError):
                raise SyncError("Invalid photo attachment") from None
            # CDN query signatures and hosts expire/change without source edits.
            identity = urlsplit(src).path.rsplit("/", 1)[-1]
            if not identity:
                raise SyncError("Missing photo identity")
            result.append({"url": src, "identity": identity,
                           "width": image.get("width"), "height": image.get("height")})
            if len(result) > MAX_PHOTOS:
                raise SyncError("Photo limit exceeded")
    return result


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def source_hash(post, specs, url):
    return digest(json_bytes({
        "message": post.get("message", ""), "created_time": post["created_time"],
        "permalink_url": url,
        "photos": [{k: v for k, v in spec.items() if k != "url"} for spec in specs],
    }))


def bundle_hash(files):
    hasher = hashlib.sha256()
    for name, payload in sorted(files.items()):
        hasher.update(name.encode("utf-8") + b"\0")
        hasher.update(len(payload).to_bytes(8, "big"))
        hasher.update(payload)
    return hasher.hexdigest()


def local_files(directory):
    if directory.is_symlink():
        raise SyncError("Symlinked bundle")
    if not directory.exists():
        return {}
    result = {}
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise SyncError("Symlinked bundle file")
        if path.is_file():
            result[path.relative_to(directory).as_posix()] = path.read_bytes()
    return result


def escape_text(text):
    # Numeric entities survive Markdown as literal text and neutralize Hugo's
    # shortcode parser as well as HTML, links, images and Markdown directives.
    return "".join("&#%d;" % ord(c) if c in string.punctuation else c for c in text)


def describe(lines, title, limit=155):
    words = []
    for line in lines[1:]:
        tokens = [t for t in line.split() if not t.startswith(("#", "http://", "https://"))]
        words.extend(tokens)
    text = " ".join(words) or title
    if len(text) <= limit:
        return text
    cut = text[:limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:-") or text[:limit - 1]
    return cut + "\u2026"


def render(post, url, image_names):
    message = post.get("message", "")
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    title = lines[0][:160] if lines else "Facebook update"
    lowered = message.lower()
    tags = sorted(set(re.findall(r"(?<!\w)#(u12|u14|u16|u18)(?!\d)", lowered))
                  | {t for t in ("community", "joinus", "sponsor")
                     if re.search(r"(?<!\w)#" + t + r"\b", lowered)})
    front = ("---\ntitle: " + json.dumps(title, ensure_ascii=False)
             + "\ndate: " + json.dumps(post["created_time"])
             + "\ndescription: " + json.dumps(describe(lines, title), ensure_ascii=False)
             + "\ntags: " + json.dumps(tags) + "\n---\n\n")
    body = "  \n".join(escape_text(line) for line in message.splitlines())
    images = "\n".join("![Facebook photo %d](%s)" % (i + 1, name)
                         for i, name in enumerate(image_names))
    return (front + body + "\n\n" + images + "\n\n"
            + "[Originally published on Facebook](" + url + ").\n").encode("utf-8")


def download_image(url):
    status, mime, payload = request_bytes(url, image=True)
    if status != 200:
        raise SyncError("Image request failed")
    if mime == "image/jpeg" and payload.startswith(b"\xff\xd8\xff"):
        return "jpg", payload
    if mime == "image/png" and payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", payload
    if mime == "image/gif" and payload[:6] in (b"GIF87a", b"GIF89a"):
        return "gif", payload
    if (mime == "image/webp" and payload.startswith(b"RIFF")
            and payload[8:12] == b"WEBP"):
        return "webp", payload
    raise SyncError("Unsupported or invalid image")


def load_state(path, cfg):
    if not path.exists():
        return {"version": 1, "page_id": cfg["page"], "since": cfg["since"], "posts": {}}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if (state["version"] != 1 or state["page_id"] != cfg["page"]
                or state["since"] != cfg["since"] or not isinstance(state["posts"], dict)):
            raise SyncError("State identity does not match configuration")
        if len(state["posts"]) > MAX_POSTS:
            raise SyncError("Tracked post limit exceeded")
        for post_id, record in state["posts"].items():
            validate_id(post_id, cfg["page"])
            if not isinstance(record, dict) or any(
                not re.fullmatch(r"[0-9a-f]{64}", record.get(key, ""))
                for key in ("source_hash", "bundle_hash")
            ):
                raise SyncError("Invalid state record")
        return state
    except (ValueError, KeyError, TypeError):
        raise SyncError("Invalid state") from None


def sync(env=None, root=None):
    cfg = config(os.environ if env is None else env)
    root = ROOT if root is None else Path(root)
    state_path = root / "scripts/facebook-state.json"
    news = root / "content/news"
    # Do not allow a symlinked parent to escape the repository.
    for path in (root / "scripts", state_path, root / "content", news):
        if path.is_symlink():
            raise SyncError("Symlinked output path")
    state = load_state(state_path, cfg)
    graph = Graph(cfg)
    posts = graph.posts()
    warnings = []
    for post_id in sorted(set(state["posts"]) - set(posts)):
        try:
            post = graph.post(post_id)
            if post.get("id") != post_id:
                raise SyncError("Mismatched tracked post")
            posts[post_id] = post
        except Unavailable:
            state["posts"][post_id]["warning"] = "unavailable: review on Facebook; retained locally"
            warnings.append(post_id + ": unavailable; review required")
    if len(posts) > MAX_POSTS:
        raise SyncError("Post limit exceeded")
    staged = {}
    photo_count = 0
    image_bytes = 0
    for post_id, post in sorted(posts.items()):
        validate_id(post_id, cfg["page"])
        created = timestamp(post.get("created_time"))
        message = post.get("message", "")
        if not isinstance(message, str):
            raise SyncError("Invalid post text")
        record = state["posts"].get(post_id)
        privacy = post.get("privacy")
        public = (post.get("is_published") is True and post.get("is_hidden") is False
                  and isinstance(privacy, dict) and privacy.get("value") == "EVERYONE")
        eligible = public and created >= cfg["cutoff"] and (
            not cfg["marker"] or cfg["marker"].casefold() in message.casefold())
        specs = photos(post) if eligible else None
        if specs is None or (not message.strip() and not specs):
            if record:
                record["warning"] = "unsupported or no longer selected: review; retained locally"
            warnings.append(post_id + ": unsupported or not selected; skipped")
            continue
        url = permalink(post.get("permalink_url"), post_id, cfg["page"])
        source = source_hash(post, specs, url)
        directory = news / ("facebook-" + post_id)
        existing = local_files(directory)
        current_hash = bundle_hash(existing)
        if record and current_hash != record["bundle_hash"]:
            record["warning"] = "locally edited: review source changes; retained locally"
            warnings.append(post_id + ": local edits preserved; review required")
            continue
        if record and source == record["source_hash"]:
            record.pop("warning", None)
            continue
        if not record and existing:
            warnings.append(post_id + ": untracked local bundle preserved")
            continue
        files = {}
        for i, spec in enumerate(specs):
            photo_count += 1
            if photo_count > MAX_TOTAL_PHOTOS:
                raise SyncError("Total photo limit exceeded")
            ext, payload = download_image(spec["url"])
            image_bytes += len(payload)
            if image_bytes > MAX_TOTAL_IMAGE_BYTES:
                raise SyncError("Total image size limit exceeded")
            files["photo-%d.%s" % (i + 1, ext)] = payload
        files["index.md"] = render(post, url, list(files))
        staged[directory] = (existing, files)
        state["posts"][post_id] = {"source_hash": source, "bundle_hash": bundle_hash(files)}
    # No network operations, validation or rendering may happen after this point.
    for directory, (existing, files) in staged.items():
        directory.mkdir(parents=True, exist_ok=True)
        for name in existing.keys() - files.keys():
            (directory / name).unlink()
        for name, payload in files.items():
            (directory / name).write_bytes(payload)
    encoded = json_bytes(state)
    if not state_path.exists() or state_path.read_bytes() != encoded:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_bytes(encoded)
    return warnings


def main():
    try:
        warnings = sync()
    except Exception:
        # urllib/JSON/filesystem exceptions can contain signed URLs or tokens.
        print("Facebook sync failed. Check configuration, API access and input limits; no secrets logged.",
              file=sys.stderr)
        return 1
    for warning in warnings:
        print("Warning: " + warning)
    print("Facebook sync complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
