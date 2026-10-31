"""Offline tests with automatically cleaned TemporaryDirectory roots in /tmp."""

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request
from email.message import Message


sys.path.insert(0, str(Path(__file__).resolve().parent))
import sync_facebook as fb


ENV = {
    "FACEBOOK_PAGE_ID": "123",
    "FACEBOOK_PAGE_ACCESS_TOKEN": "test-secret-token",
    "FACEBOOK_API_VERSION": "v23.0",
    "FACEBOOK_IMPORT_SINCE": "2026-01-01",
}
JPEG = b"\xff\xd8\xff" + b"example photo"


def post(number="456", message="Match news #news #u12", attachments=None):
    value = {
        "id": "123_" + number,
        "message": message,
        "created_time": "2026-06-01T12:34:56+0000",
        "permalink_url": "https://www.facebook.com/fosse/posts/" + number,
        "is_published": True,
        "is_hidden": False,
        "privacy": {"value": "EVERYONE"},
    }
    if attachments is not None:
        value["attachments"] = {"data": attachments}
    return value


def photo(url="https://scontent.xx.fbcdn.net/photos/123_456_n.jpg?signature=one"):
    return {"media_type": "photo", "type": "photo",
            "media": {"image": {"src": url, "width": 800, "height": 600}}}


class SyncTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="fosse-facebook-", dir="/tmp")
        self.root = Path(temp.name)
        self.addCleanup(temp.cleanup)
        self.env = dict(ENV)
        self.feed = [post()]
        self.lookups = {}
        self.images = []
        self.graph_calls = []
        self.network = patch.object(fb, "request_bytes", side_effect=self.request)
        self.network.start()
        self.addCleanup(self.network.stop)

    def request(self, url, *, token=None, image=False):
        if image:
            self.assertIsNone(token)
            self.images.append(url)
            return 200, "image/jpeg", JPEG
        self.assertEqual(token, ENV["FACEBOOK_PAGE_ACCESS_TOKEN"])
        self.assertNotIn(token, url)
        self.assertNotIn("access_token", url)
        self.graph_calls.append(url)
        resource = urlsplit(url).path.rsplit("/", 1)[-1]
        if resource == "posts":
            data = {"data": self.feed}
        else:
            data = self.lookups.get(resource, {"error": {"code": 100, "message": "not found"}})
        return 200, "application/json", json.dumps(data).encode()

    def run_sync(self):
        return fb.sync(self.env, self.root)

    def bundle(self, number="456"):
        state_file = self.root / "scripts/facebook-state.json"
        posts = self.state()["posts"] if state_file.exists() else {}
        record = posts.get("123_" + number, {})
        return self.root / "content/news" / record.get("dir", "facebook-123_" + number)

    def state(self):
        return json.loads((self.root / "scripts/facebook-state.json").read_text())

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes()
                for p in self.root.rglob("*") if p.is_file()}

    def test_text_duplicate_and_deterministic_state(self):
        self.feed *= 2
        self.assertEqual(self.run_sync(), [])
        text = (self.bundle() / "index.md").read_text()
        self.assertIn('date: "2026-06-01T12:34:56+0000"', text)
        self.assertIn('tags: ["u12"]', text)
        self.assertIn("Originally published on Facebook", text)
        self.assertEqual(len(self.state()["posts"]), 1)
        before = self.snapshot()
        self.run_sync()
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.images, [])

    def test_conflicting_duplicate_aborts(self):
        self.feed.append(post(message="Different #news"))
        with self.assertRaises(fb.SyncError):
            self.run_sync()
        self.assertEqual({}, self.snapshot())

    def test_source_change_updates_unedited_bundle(self):
        self.run_sync()
        old_hash = self.state()["posts"]["123_456"]["source_hash"]
        self.feed[0]["message"] = "New result #news #u16"
        self.run_sync()
        self.assertIn("New result", (self.bundle() / "index.md").read_text())
        self.assertNotEqual(old_hash, self.state()["posts"]["123_456"]["source_hash"])

    def test_editor_changes_are_preserved_and_warning_persisted(self):
        self.run_sync()
        path = self.bundle() / "index.md"
        path.write_text("An editor's replacement")
        (self.bundle() / "notes.txt").write_text("editor notes")
        self.feed[0]["message"] = "Changed source #news"
        warnings = self.run_sync()
        self.assertIn("local edits preserved", warnings[0])
        self.assertEqual(path.read_text(), "An editor's replacement")
        self.assertIn("locally edited", self.state()["posts"]["123_456"]["warning"])
        before = self.snapshot()
        self.run_sync()
        self.assertEqual(before, self.snapshot())

    def test_unchanged_source_detects_local_edits(self):
        self.run_sync()
        (self.bundle() / "index.md").write_text("Editorial")
        self.assertIn("local edits preserved", self.run_sync()[0])

    def test_text_neutralizes_shortcodes_html_markdown_and_frontmatter(self):
        self.feed = [post(message=(
            'A "title": value #news #u14\n'
            '{{< youtube "x" >}}\n<script>alert(1)</script>\n'
            '[click](javascript:evil) ![x](https://evil)\n---\n*bold* & raw'
        ))]
        self.run_sync()
        text = (self.bundle() / "index.md").read_text()
        body = text.split("---\n", 2)[2]
        for unsafe in ("{{", "<script", "[click]", "![x]", "*bold*", "\n---"):
            self.assertNotIn(unsafe, body)
        self.assertIn("&#123;&#123;", body)
        self.assertIn('title: "A \\"title\\": value #news #u14"', text)
        self.assertIn('tags: ["u14"]', text)

    def test_hashtags_become_tags(self):
        self.feed = [post(message="News #news #U14Rugby #u18 #Community #JoinUs #Sponsor #u123")]
        self.run_sync()
        text = (self.bundle() / "index.md").read_text()
        self.assertIn('tags: ["community", "joinus", "sponsor", "u14", "u18"]', text)

    def test_folder_uses_friendly_title_slug(self):
        self.feed = [post(message="Big Win! \u00c9t\u00e9 #news")]
        self.run_sync()
        self.assertEqual(self.bundle().name, "big-win-ete-news")
        self.assertEqual(self.state()["posts"]["123_456"]["dir"], "big-win-ete-news")

    def test_description_skips_title_hashtags_and_links_and_truncates(self):
        self.feed = [post(message="Title line\nFirst & second https://x.example/y\n#news #u12\n" + "word " * 60)]
        self.run_sync()
        text = (self.bundle() / "index.md").read_text()
        desc = [l for l in text.splitlines() if l.startswith("description: ")][0]
        value = json.loads(desc[len("description: "):])
        self.assertTrue(value.startswith("First & second word word"))
        self.assertNotIn("http", value)
        self.assertNotIn("#", value)
        self.assertLessEqual(len(value), 155)
        self.assertTrue(value.endswith("\u2026"))

    def test_description_falls_back_to_title(self):
        self.feed = [post(message="Only a title #news")]
        self.run_sync()
        self.assertIn('description: "Only a title #news"', (self.bundle() / "index.md").read_text())

    def test_photo_bundle_and_signed_url_changes_do_not_redownload(self):
        self.feed = [post(attachments=[photo()])]
        self.run_sync()
        self.assertEqual((self.bundle() / "photo-1.jpg").read_bytes(), JPEG)
        self.assertIn("photo-1.jpg", (self.bundle() / "index.md").read_text())
        self.assertEqual(len(self.images), 1)
        before = self.snapshot()
        self.feed[0]["attachments"]["data"][0]["media"]["image"]["src"] = (
            "https://different.fbcdn.net/other/123_456_n.jpg?signature=two")
        self.run_sync()
        self.assertEqual(len(self.images), 1)
        self.assertEqual(before, self.snapshot())
        self.assertNotIn(b"signature", (self.root / "scripts/facebook-state.json").read_bytes())

    def test_album_handles_default_subattachment_fields(self):
        first = photo()
        second = photo("https://cdn.fbsbx.com/other.jpg?expires=42")
        second.pop("media_type")
        self.feed = [post(attachments=[{
            "type": "album", "media_type": "album",
            "subattachments": {"data": [first, second]},
        }])]
        self.run_sync()
        self.assertEqual(len(self.images), 2)
        self.assertTrue((self.bundle() / "photo-2.jpg").exists())

    def test_replacing_photo_removes_old_generated_file(self):
        self.feed = [post(attachments=[photo()])]
        self.run_sync()
        self.feed = [post(message="Now text only #news")]
        self.run_sync()
        self.assertFalse((self.bundle() / "photo-1.jpg").exists())

    def test_empty_marker_allows_photo_only_and_empty_post_is_skipped(self):
        self.env["FACEBOOK_IMPORT_MARKER"] = ""
        first = post(message="", attachments=[photo()])
        second = post("457", "")
        self.feed = [first, second, post("458", "Unmarked plain text")]
        self.run_sync()
        self.assertIn('title: "Facebook update"', (self.bundle() / "index.md").read_text())
        self.assertFalse(self.bundle("457").exists())
        self.assertIn("Unmarked plain text", (self.bundle("458") / "index.md").read_text())

    def test_custom_marker_overrides_default(self):
        self.env["FACEBOOK_IMPORT_MARKER"] = "#publish"
        self.feed = [post(), post("457", "A result #PUBLISH")]
        self.run_sync()
        self.assertEqual(list(self.state()["posts"]), ["123_457"])

    def test_visibility_gate_fails_closed_without_downloading_images(self):
        changes = (
            {"is_published": False}, {"is_hidden": True},
            {"is_published": 1}, {"is_hidden": 0},
            {"privacy": {"value": "ALL_FRIENDS"}},
            {"privacy": {"value": "CUSTOM"}}, {"privacy": {"value": "UNKNOWN"}},
            {"privacy": {"value": "everyone"}}, {"privacy": {}}, {"privacy": None},
        )
        for change in changes:
            with self.subTest(change=change):
                self.feed = [dict(post(attachments=[photo()]), **change)]
                self.assertIn("unsupported", self.run_sync()[0])
                self.assertEqual(self.state()["posts"], {})
                self.assertFalse(self.bundle().exists())
                self.assertEqual(self.images, [])
        for field in ("is_published", "is_hidden", "privacy"):
            with self.subTest(missing=field):
                value = post(attachments=[photo()])
                del value[field]
                self.feed = [value]
                self.assertIn("unsupported", self.run_sync()[0])
                self.assertEqual(self.state()["posts"], {})
                self.assertFalse(self.bundle().exists())
                self.assertEqual(self.images, [])

    def test_tracked_nonpublic_post_warns_without_updating_or_downloading(self):
        self.run_sync()
        original = (self.bundle() / "index.md").read_bytes()
        source_hash = self.state()["posts"]["123_456"]["source_hash"]
        self.feed = [post(message="Private source edit #news", attachments=[photo()])]
        self.feed[0]["privacy"] = {"value": "SELF"}
        self.assertIn("unsupported", self.run_sync()[0])
        self.assertEqual((self.bundle() / "index.md").read_bytes(), original)
        self.assertEqual(self.state()["posts"]["123_456"]["source_hash"], source_hash)
        self.assertIn("unsupported", self.state()["posts"]["123_456"]["warning"])
        self.assertEqual(self.images, [])

    def test_cutoff_and_marker_filter(self):
        self.feed = [post(message="Unmarked"), post("457"), post("458")]
        self.feed[1]["created_time"] = "2025-12-31T23:59:59Z"
        self.feed[2]["created_time"] = "2026-01-01T00:00:00Z"
        self.run_sync()
        self.assertEqual(list(self.state()["posts"]), ["123_458"])

    def test_missing_tracked_post_is_rechecked_and_not_deleted(self):
        self.run_sync()
        original = (self.bundle() / "index.md").read_bytes()
        self.feed = []
        self.run_sync()
        self.assertTrue(any("/123_456?" in call for call in self.graph_calls))
        self.assertEqual((self.bundle() / "index.md").read_bytes(), original)
        self.assertIn("unavailable", self.state()["posts"]["123_456"]["warning"])
        before = self.snapshot()
        self.run_sync()
        self.assertEqual(before, self.snapshot())

    def test_missing_from_feed_can_still_update_by_object_lookup(self):
        self.run_sync()
        self.feed = []
        self.lookups["123_456"] = post(message="Updated object #news")
        self.run_sync()
        self.assertIn("Updated object", (self.bundle() / "index.md").read_text())
        self.assertNotIn("warning", self.state()["posts"]["123_456"])

    def test_tracked_unsupported_post_warns_and_keeps_bundle(self):
        self.run_sync()
        original = (self.bundle() / "index.md").read_bytes()
        self.feed[0]["attachments"] = {"data": [{"type": "video", "media_type": "video"}]}
        self.run_sync()
        self.assertEqual((self.bundle() / "index.md").read_bytes(), original)
        self.assertIn("unsupported", self.state()["posts"]["123_456"]["warning"])

    def test_shared_video_and_links_are_skipped_without_downloads(self):
        self.feed = [
            post("456", attachments=[{"type": "share", "media_type": "photo"}]),
            post("457", attachments=[{"type": "video", "media_type": "video"}]),
            post("458", attachments=[{"type": "share", "media_type": "link"}]),
        ]
        self.assertEqual(len(self.run_sync()), 3)
        self.assertEqual(self.state()["posts"], {})
        self.assertEqual(self.images, [])

    def test_token_expiry_during_lookup_leaves_all_files_unchanged(self):
        self.run_sync()
        before = self.snapshot()
        self.feed = [post("457", attachments=[photo()])]
        self.lookups["123_456"] = {"error": {"code": 190, "message": ENV["FACEBOOK_PAGE_ACCESS_TOKEN"]}}
        with self.assertRaises(fb.SyncError):
            self.run_sync()
        self.assertEqual(before, self.snapshot())

    def test_image_failure_after_staging_other_post_writes_nothing(self):
        self.feed = [post(), post("457", attachments=[photo()])]
        with patch.object(fb, "download_image", side_effect=fb.SyncError("failure")):
            with self.assertRaises(fb.SyncError):
                self.run_sync()
        self.assertEqual(self.snapshot(), {})

    def test_state_is_bound_to_page_and_cutoff(self):
        self.run_sync()
        before = self.snapshot()
        for key, value in (("FACEBOOK_PAGE_ID", "999"),
                           ("FACEBOOK_IMPORT_SINCE", "2026-02-01")):
            with self.subTest(key=key):
                self.env = dict(ENV, **{key: value})
                with self.assertRaises(fb.SyncError):
                    self.run_sync()
                self.assertEqual(before, self.snapshot())

    def test_invalid_identity_and_permalink_abort_without_writes(self):
        for key, value in (
            ("id", "../escape"), ("id", "999_456"),
            ("permalink_url", "https://evil.example/123/posts/456"),
            ("permalink_url", "https://facebook.com.evil/123/posts/456"),
            ("permalink_url", "https://www.facebook.com/fosse/posts/999"),
            ("permalink_url", "https://www.facebook.com/fosse/posts/456)evil"),
        ):
            with self.subTest(value=value):
                self.feed = [dict(post(), **{key: value})]
                with self.assertRaises(fb.SyncError):
                    self.run_sync()
                self.assertEqual({}, self.snapshot())

    def test_unsafe_photo_host_aborts(self):
        self.feed = [post(attachments=[photo("https://evil.example/p.jpg")])]
        with self.assertRaises(fb.SyncError):
            self.run_sync()
        self.assertEqual(self.snapshot(), {})
        self.assertEqual(self.images, [])

    def test_late_invalid_photo_keeps_existing_files_and_new_bundle_unwritten(self):
        self.run_sync()
        before = self.snapshot()
        self.feed = [post(message="New text #news"), post("457", attachments=[photo()])]
        with patch.object(fb, "download_image", side_effect=fb.SyncError("invalid MIME")):
            with self.assertRaises(fb.SyncError):
                self.run_sync()
        self.assertEqual(self.snapshot(), before)

    def test_paginated_album_is_never_silently_truncated(self):
        self.feed = [post(attachments=[{
            "type": "album", "media_type": "album",
            "subattachments": {"data": [photo()], "paging": {"next": "untrusted"}},
        }])]
        with self.assertRaises(fb.SyncError):
            self.run_sync()
        self.assertEqual({}, self.snapshot())

    def test_permalink_query_and_opaque_post_identifier(self):
        self.feed[0]["permalink_url"] = (
            "https://www.facebook.com/permalink.php?story_fbid=pfbidExample123&id=123")
        self.run_sync()
        self.assertIn("story_fbid=pfbidExample123",
                      (self.bundle() / "index.md").read_text())

    def test_explicit_post_photo_and_page_limits_abort(self):
        self.feed = [post(), post("457")]
        with patch.object(fb, "MAX_POSTS", 1):
            with self.assertRaises(fb.SyncError):
                self.run_sync()
        self.feed = [post(attachments=[photo(), photo()])]
        with patch.object(fb, "MAX_PHOTOS", 1):
            with self.assertRaises(fb.SyncError):
                self.run_sync()
        with patch.object(fb, "MAX_TOTAL_PHOTOS", 1):
            with self.assertRaises(fb.SyncError):
                self.run_sync()
        with patch.object(fb, "MAX_TOTAL_IMAGE_BYTES", 1):
            with self.assertRaises(fb.SyncError):
                self.run_sync()
        self.assertEqual(self.snapshot(), {})

    def test_untracked_existing_bundle_not_overwritten(self):
        self.bundle().mkdir(parents=True)
        (self.bundle() / "index.md").write_text("existing")
        self.assertIn("untracked", self.run_sync()[0])
        self.assertEqual((self.bundle() / "index.md").read_text(), "existing")
        self.assertEqual(self.state()["posts"], {})

    def test_symlinked_bundle_cannot_escape_repository(self):
        target = self.root / "outside"
        target.mkdir()
        self.bundle().parent.mkdir(parents=True)
        self.bundle().symlink_to(target, target_is_directory=True)
        with self.assertRaises(fb.SyncError):
            self.run_sync()
        self.assertEqual(list(target.iterdir()), [])


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.cfg = fb.config(ENV)

    def response(self, data, status=200):
        return status, "application/json", json.dumps(data).encode()

    def test_pagination_uses_only_cursor_on_trusted_graph_url(self):
        replies = [
            self.response({"data": [post()], "paging": {
                "next": "https://evil.example/?access_token=do-not-follow",
                "cursors": {"after": "cursor&access_token=evil"},
            }}),
            self.response({"data": [post("457")]}),
        ]
        with patch.object(fb, "request_bytes", side_effect=replies) as request:
            self.assertEqual(len(fb.Graph(self.cfg).posts()), 2)
        url = request.call_args_list[1].args[0]
        self.assertEqual(urlsplit(url).netloc, "graph.facebook.com")
        query = parse_qs(urlsplit(url).query)
        self.assertEqual(query["after"], ["cursor&access_token=evil"])
        self.assertNotIn("access_token", query)
        self.assertEqual(query["fields"], [fb.FIELDS])
        self.assertIn("is_published,is_hidden,privacy", query["fields"][0])
        self.assertIn("subattachments{type,media_type,media}", query["fields"][0])

    def test_pagination_limits_and_missing_or_repeated_cursor_fail(self):
        for cursors, limit in (({}, 100), ({"after": "same"}, 2)):
            data = {"data": [], "paging": {"next": "ignored", "cursors": cursors}}
            with patch.object(fb, "request_bytes", return_value=self.response(data)):
                with patch.object(fb, "MAX_PAGES", limit):
                    with self.assertRaises(fb.SyncError):
                        fb.Graph(self.cfg).posts()

    def test_page_limit_fails_even_with_unique_cursors(self):
        replies = [
            self.response({"data": [], "paging": {"next": "ignored", "cursors": {"after": "1"}}}),
            self.response({"data": [], "paging": {"next": "ignored", "cursors": {"after": "2"}}}),
        ]
        with patch.object(fb, "request_bytes", side_effect=replies):
            with patch.object(fb, "MAX_PAGES", 2):
                with self.assertRaises(fb.SyncError):
                    fb.Graph(self.cfg).posts()

    def test_code_100_is_only_unavailable_for_object_lookup(self):
        response = self.response({"error": {"code": 100}}, 400)
        with patch.object(fb, "request_bytes", return_value=response):
            with self.assertRaises(fb.Unavailable):
                fb.Graph(self.cfg).post("123_456")
            with self.assertRaises(fb.SyncError) as caught:
                fb.Graph(self.cfg).posts()
            self.assertNotIsInstance(caught.exception, fb.Unavailable)

    def test_auth_failure_is_never_unavailable(self):
        with patch.object(fb, "request_bytes", return_value=self.response(
                {"error": {"code": 190}}, 400)):
            with self.assertRaises(fb.SyncError) as caught:
                fb.Graph(self.cfg).post("123_456")
            self.assertNotIsInstance(caught.exception, fb.Unavailable)

    def test_malformed_api_data_rejected(self):
        for data in ([], {"data": {}}, {"data": [None]}):
            with self.subTest(data=data):
                with patch.object(fb, "request_bytes", return_value=self.response(data)):
                    with self.assertRaises(fb.SyncError):
                        fb.Graph(self.cfg).posts()


class TransportAndConfigTests(unittest.TestCase):
    def test_invalid_config(self):
        changes = [
            ("FACEBOOK_PAGE_ID", ""), ("FACEBOOK_PAGE_ID", "../123"),
            ("FACEBOOK_PAGE_ACCESS_TOKEN", ""), ("FACEBOOK_PAGE_ACCESS_TOKEN", "x\nsecret"),
            ("FACEBOOK_API_VERSION", ""), ("FACEBOOK_API_VERSION", "latest"),
            ("FACEBOOK_API_VERSION", "v23"), ("FACEBOOK_IMPORT_SINCE", ""),
            ("FACEBOOK_IMPORT_SINCE", "yesterday"), ("FACEBOOK_IMPORT_SINCE", "2026-02-30"),
        ]
        for key, value in changes:
            with self.subTest(key=key, value=value):
                with self.assertRaises(fb.SyncError):
                    fb.config(dict(ENV, **{key: value}))
        self.assertEqual(fb.config(ENV)["marker"], "#news")
        self.assertEqual(fb.config(dict(ENV, FACEBOOK_IMPORT_MARKER=""))["marker"], "")
        self.assertEqual(fb.config(dict(ENV, FACEBOOK_IMPORT_SINCE="2026-01-01T02:00:00+02:00"))[
            "since"], "2026-01-01T00:00:00+00:00")

    def test_image_host_allowlist(self):
        for url in (
            "http://cdn.fbcdn.net/x", "https://fbcdn.net/x",
            "https://cdn.fbcdn.net.evil/x", "https://cdn.fbsbx.com@evil/x",
            "******cdn.fbcdn.net/x", "https://cdn.fbcdn.net:444/x",
            "file:///image", "https://cdn.fbcdn.net/x#fragment",
        ):
            with self.subTest(url=url):
                with self.assertRaises(fb.SyncError):
                    fb.image_url(url)
        fb.image_url("https://cdn.fbcdn.net/image")
        fb.image_url("https://cdn.fbsbx.com/image")

    def test_image_redirects_validate_target_and_drop_authorization(self):
        handler = fb.SafeRedirects(images=True)
        original = Request("https://cdn.fbcdn.net/x", headers={"Authorization": "******"})
        redirected = handler.redirect_request(
            original, None, 302, "", {}, "https://other.fbsbx.com/photo")
        self.assertIsNone(redirected.get_header("Authorization"))
        with self.assertRaises(fb.SyncError):
            handler.redirect_request(original, None, 302, "", {}, "https://evil.example/x")
        with self.assertRaises(fb.SyncError):
            fb.SafeRedirects().redirect_request(original, None, 302, "", {},
                                                "https://graph.facebook.com/x")
        limited = fb.SafeRedirects(images=True)
        limited.count = fb.MAX_REDIRECTS
        with self.assertRaises(fb.SyncError):
            limited.redirect_request(original, None, 302, "", {}, "https://cdn.fbcdn.net/x")

    def response(self, payload=JPEG, mime="image/jpeg", status=200):
        response = Mock()
        response.code = status
        response.headers = Message()
        response.headers["Content-Type"] = mime
        response.read.return_value = payload
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return response

    def test_graph_authorization_header_not_query_and_images_no_auth(self):
        opener = Mock()
        opener.open.return_value = self.response()
        with patch.object(fb, "build_opener", return_value=opener):
            fb.request_bytes("https://graph.facebook.com/v23.0/123/posts?fields=id", token="secret")
            req = opener.open.call_args.args[0]
            self.assertEqual(req.get_header("Authorization"), "Bearer " + "secret")
            self.assertNotIn("secret", req.full_url)
            self.assertEqual(opener.open.call_args.kwargs["timeout"], fb.TIMEOUT)
            fb.request_bytes("https://cdn.fbcdn.net/x", token="secret", image=True)
            self.assertIsNone(opener.open.call_args.args[0].get_header("Authorization"))
            for url in ("https://evil.example/x", "https://graph.facebook.com/x?access_token=secret"):
                with self.assertRaises(fb.SyncError):
                    fb.request_bytes(url, token="secret")

    def test_image_magic_and_mime_checks(self):
        samples = [
            ("image/jpeg", JPEG, "jpg"),
            ("image/png", b"\x89PNG\r\n\x1a\nrest", "png"),
            ("image/gif", b"GIF89arest", "gif"),
            ("image/webp", b"RIFFxxxxWEBPrest", "webp"),
        ]
        for mime, payload, extension in samples:
            with patch.object(fb, "request_bytes", return_value=(200, mime, payload)):
                self.assertEqual(fb.download_image("unused"), (extension, payload))
        for mime, payload in (("text/html", JPEG), ("image/jpeg", b"<html>"),
                              ("image/svg+xml", b"<svg/>")):
            with patch.object(fb, "request_bytes", return_value=(200, mime, payload)):
                with self.assertRaises(fb.SyncError):
                    fb.download_image("unused")

    def test_transport_response_limits_and_network_failure(self):
        opener = Mock()
        opener.open.return_value = self.response(payload=b"x" * 11)
        with patch.object(fb, "build_opener", return_value=opener):
            with patch.object(fb, "MAX_IMAGE_BYTES", 10):
                with self.assertRaises(fb.SyncError):
                    fb.request_bytes("https://cdn.fbcdn.net/x", image=True)
                opener.open.return_value.read.assert_called_once_with(11)
            opener.open.side_effect = URLError("secret-url")
            with self.assertRaises(fb.SyncError) as caught:
                fb.request_bytes("https://cdn.fbcdn.net/x", image=True)
            self.assertNotIn("secret-url", str(caught.exception))

    def test_http_graph_error_body_is_classified_without_exposing_details(self):
        opener = Mock()
        headers = Message()
        headers["Content-Type"] = "application/json"
        opener.open.side_effect = HTTPError(
            "https://graph.facebook.com/test", 400, "failure", headers,
            io.BytesIO(b'{"error":{"code":190,"message":"private-token"}}'))
        with patch.object(fb, "build_opener", return_value=opener):
            with self.assertRaises(fb.SyncError) as caught:
                fb.Graph(fb.config(ENV)).post("123_456")
        self.assertNotIsInstance(caught.exception, fb.Unavailable)
        self.assertNotIn("private-token", str(caught.exception))

    def test_cli_never_logs_exception_details(self):
        output = io.StringIO()
        with patch.object(fb, "sync", side_effect=ValueError("secret token and signed URL")):
            with contextlib.redirect_stderr(output):
                self.assertEqual(fb.main(), 1)
        self.assertNotIn("secret token", output.getvalue())
        self.assertNotIn("signed URL", output.getvalue())


if __name__ == "__main__":
    unittest.main()
