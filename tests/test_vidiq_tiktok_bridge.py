import copy
import json
import os
import shlex
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image
import vidiq_tiktok_bridge as direct
from scripts.merge_news_checkpoint import merge_state

ID = "a" * 24
class FakePublisher:
    def __init__(self, story):
        self.story = story
        self.calls = []
        self.is_connected = True
        self.lose_publish_response = False
    def connected(self):
        return self.is_connected
    def start(self):
        pass
    def tool(self, name, args):
        self.calls.append((name, copy.deepcopy(args)))
        if name == "vidiq_social_post_list":
            return {"destinations": []}
        if name == "vidiq_social_post_draft_create":
            return {"postId": "post", "revision": "r1", "ready": True,
                    "destinations": [{"platformAccountId": direct.ACCOUNT, "publicationId": "pub"}]}
        if name == "vidiq_social_post_publish":
            if self.lose_publish_response:
                raise direct.BridgeError("response_lost")
            return {"destinations": [{"publicationId": "pub", "status": "submitted"}]}
        if name == "vidiq_social_post_status":
            return {"destinations": [{"publicationId": args["publicationId"], "status": "completed",
                    "postUrl": "https://www.tiktok.com/@slnewstwentyfourseven/video/test"}]}
        raise AssertionError(name)

class DirectPublishingTests(unittest.TestCase):
    def article(self):
        return {"id": ID, "title_si": "නව පුවතක්", "summary_si": "සම්පූර්ණ සත්‍ය පුවතකි.",
                "published": time.time() - 60, "link": "https://example.com/news"}
    def state(self, article):
        return {"stories": {article["id"]: {"article": article,
            "receipts": {"facebook": {"id": "accepted"}}}}}
    def test_owner_connection_flag_prevents_all_connector_calls(self):
        article = self.article()
        with patch.dict(os.environ, {"SLNEWS_VIDIQ_BRIDGE_URL": direct.BRIDGE,
                                    "SLNEWS_VIDIQ_PUBLISH_ENABLED": "false"}), \
             patch.object(direct, "Publisher") as constructor:
            result = direct.publish_tiktok(self.state(article), [article], time.time())
        self.assertEqual(result["status"], "awaiting_owner_connection")
        constructor.assert_not_called()

    def test_filtered_empty_history_page_is_followed_before_creating(self):
        client = MagicMock()
        client.tool.side_effect = [{"destinations": [], "nextCursor": "page2"},
                                  {"destinations": [{"status": "completed", "postId": "old"}], "nextCursor": None}]
        rows = direct.matching_history(client, "news", time.time())
        self.assertEqual(rows[0]["postId"], "old")
        self.assertEqual(client.tool.call_args_list[1].args[1]["cursor"], "page2")

    def test_one_confirmed_destination_is_enough_and_publication_is_immediate(self):
        article = self.article()
        state = self.state(article)
        publisher = FakePublisher(ID + ":photo")
        old = os.getcwd()
        try:
            with tempfile.TemporaryDirectory() as folder:
                os.chdir(folder)
                path = Path("output/card_" + ID + ".png")
                path.parent.mkdir()
                path.write_bytes(b"image")
                with patch.dict(os.environ, {"SLNEWS_VIDIQ_BRIDGE_URL": direct.BRIDGE, "SLNEWS_VIDIQ_PUBLISH_ENABLED": "true"}), \
                     patch.object(direct, "Publisher", return_value=publisher), \
                     patch.object(direct, "upload_image", return_value={"id": "image-id", "type": "image"}), \
                     patch.object(direct, "caption_for", return_value="approved caption"), \
                     patch.object(direct.time, "sleep"):
                    result = direct.publish_tiktok(state, [article], time.time())
                    direct.publish_tiktok(state, [article], time.time())
                creates = [args for name, args in publisher.calls if name == "vidiq_social_post_draft_create"]
                publishes = [args for name, args in publisher.calls if name == "vidiq_social_post_publish"]
                self.assertEqual(len(creates), 1)
                self.assertEqual(len(publishes), 1)
                self.assertNotIn("publishAt", creates[0])
                self.assertEqual(creates[0]["destinations"], [direct.settings()])
                self.assertEqual(result["sent"], 1)
                self.assertEqual(state["vidiq_tiktok"][ID]["status"], "completed")
        finally:
            os.chdir(old)

    def test_blogger_receipt_is_eligible_without_facebook_or_telegram_receipt(self):
        article = self.article()
        state = {"blogger_posts": {ID: {"id": "blog-post"}}}
        publisher = FakePublisher(ID + ":photo")
        publisher.is_connected = False
        with patch.dict(os.environ, {"SLNEWS_VIDIQ_BRIDGE_URL": direct.BRIDGE, "SLNEWS_VIDIQ_PUBLISH_ENABLED": "true"}), \
             patch.object(direct, "Publisher", return_value=publisher) as constructor:
            result = direct.publish_tiktok(state, [article], time.time())
        constructor.assert_called_once()
        self.assertEqual(result["status"], "connection_required")

    def test_unconfirmed_or_stale_news_cannot_start_publication(self):
        article = self.article()
        with patch.dict(os.environ, {"SLNEWS_VIDIQ_BRIDGE_URL": direct.BRIDGE, "SLNEWS_VIDIQ_PUBLISH_ENABLED": "true"}), \
             patch.object(direct, "Publisher") as constructor:
            direct.publish_tiktok({}, [article], time.time())
            direct.publish_tiktok(self.state(article), [dict(article, published=time.time()-43201)], time.time())
            direct.publish_tiktok(self.state(article), [article], time.time(), preview=True)
        constructor.assert_not_called()

    def test_existing_public_reel_does_not_get_sent_again(self):
        article = dict(self.article(), id="cbf98e8c42bbfc5701da1041")
        state = self.state(article)
        publisher = FakePublisher(article["id"] + ":photo")
        with patch.dict(os.environ, {"SLNEWS_VIDIQ_BRIDGE_URL": direct.BRIDGE, "SLNEWS_VIDIQ_PUBLISH_ENABLED": "true"}), \
             patch.object(direct, "Publisher", return_value=publisher):
            direct.publish_tiktok(state, [article], time.time())
        self.assertEqual(state["vidiq_tiktok"][article["id"]]["status"], "completed")
        self.assertEqual(publisher.calls, [])

    def test_unknown_create_outcome_is_not_blindly_repeated(self):
        article = self.article()
        state = self.state(article)
        publisher = FakePublisher(ID + ":photo")
        with patch.dict(os.environ, {"SLNEWS_VIDIQ_BRIDGE_URL": direct.BRIDGE, "SLNEWS_VIDIQ_PUBLISH_ENABLED": "true"}), \
             patch.object(direct, "Publisher", return_value=publisher):
            for status in ("uncertain", "creating"):
                state["vidiq_tiktok"] = {ID: {"status": status}}
                direct.publish_tiktok(state, [article], time.time())
        self.assertEqual(publisher.calls, [])

    def test_known_processing_post_is_reconciled_without_creating_another(self):
        article = self.article()
        state = self.state(article)
        state["vidiq_tiktok"] = {ID: {"status": "uncertain", "kind": "reel",
                                    "postId": "post", "publicationId": "pub"}}
        publisher = FakePublisher(ID + ":reel")
        with patch.dict(os.environ, {"SLNEWS_VIDIQ_BRIDGE_URL": direct.BRIDGE, "SLNEWS_VIDIQ_PUBLISH_ENABLED": "true"}), \
             patch.object(direct, "Publisher", return_value=publisher):
            direct.publish_tiktok(state, [article], time.time())
        self.assertEqual([n for n, _ in publisher.calls], ["vidiq_social_post_status"])
        self.assertEqual(state["vidiq_tiktok"][ID]["status"], "completed")

    def test_confirmed_platform_limit_stops_further_attempts(self):
        article = self.article()
        state = self.state(article)
        state["vidiq_tiktok_limit_at"] = time.time()
        with patch.dict(os.environ, {"SLNEWS_VIDIQ_BRIDGE_URL": direct.BRIDGE, "SLNEWS_VIDIQ_PUBLISH_ENABLED": "true"}), \
             patch.object(direct, "Publisher") as constructor:
            self.assertEqual(direct.publish_tiktok(state, [article], time.time())["status"], "platform_limit")
        constructor.assert_not_called()

    def test_transfer_arguments_are_validated_without_executing_shell_code(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "own.mp4"
            path.write_bytes(b"test-video")
            args = ["sh", "-c", "ignored shell text", "vidiq-upload", str(path.resolve()),
                    str(path.stat().st_size), "https://storage.googleapis.com/own?signature=value",
                    "video/mp4", "upload-id"]
            command = shlex.join(args)
            self.assertIn("storage.googleapis.com", direct.transfer_parts(command, path, "upload-id"))
            args[6] = "https://attacker.example/upload"
            with self.assertRaises(direct.BridgeError):
                direct.transfer_parts(shlex.join(args), path, "upload-id")
            with self.assertRaises(direct.BridgeError):
                direct.transfer_parts(command, path, "another-upload")

    def test_connector_image_upload_preserves_design_and_uses_jpeg(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "poster.png"
            Image.new("RGB", (1080, 1350), "#ac1933").save(path)
            publisher = MagicMock()
            publisher.tool.side_effect = [
                {"uploadUrl": "https://mcp.vidiq.com/mcp/uploads/images/one-time", "transferId": "transfer"},
                {"imageId": "image-id"}]
            with patch.object(direct.requests, "put", return_value=MagicMock(ok=True)) as put:
                result = direct.upload_image(publisher, path)
            self.assertEqual(result, {"id": "image-id", "type": "image"})
            with Image.open(path.with_name("poster_tiktok.jpg")) as image:
                self.assertEqual(image.size, (864, 1080))
            self.assertEqual(put.call_args.kwargs["headers"]["Content-Type"], "image/jpeg")

    def test_actual_asset_attribution_is_used_instead_of_a_new_photo_lookup(self):
        article = self.article()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "reel.mp4"
            manifest = Path(str(path)+".attribution.json")
            manifest.write_text(json.dumps({"article_id": ID, "attribution": "\n\nCreator / CC BY 4.0"}))
            with patch("fast_news.caption", return_value="Original news"):
                self.assertIn("CC BY 4.0", direct.caption_for(article, path))
                manifest.write_text(json.dumps({"article_id": "b"*24, "attribution": "wrong"}))
                with self.assertRaises(direct.BridgeError):
                    direct.caption_for(article, path)

    def test_merge_preserves_confirmed_post_and_blogger_receipts(self):
        remote = {"vidiq_tiktok": {ID: {"status": "completed", "postId": "posted", "postUrl": "public"}},
                  "blogger_posts": {ID: {"id": "blog"}}}
        local = {"vidiq_tiktok": {ID: {"status": "importing"}}}
        merged = merge_state(remote, local)
        self.assertEqual(merged["vidiq_tiktok"][ID]["status"], "completed")
        self.assertEqual(merged["vidiq_tiktok"][ID]["postId"], "posted")
        self.assertEqual(merged["blogger_posts"][ID]["id"], "blog")
        conflict = merge_state(remote, {"vidiq_tiktok": {ID: {"status": "draft", "postId": "different"}}})
        self.assertTrue(conflict["vidiq_tiktok"][ID]["merge_conflict"])
        self.assertEqual(conflict["vidiq_tiktok"][ID]["postId"], "posted")

if __name__ == "__main__":
    unittest.main()
