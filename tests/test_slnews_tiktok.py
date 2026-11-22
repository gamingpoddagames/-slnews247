import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import slnews_tiktok as tt


class TikTokNewsTests(unittest.TestCase):
    def setUp(self):
        self.article = {
            "id": "fresh-news",
            "title_si": "නොවැම්බර් 30 ගුරු විදුහල්පති වර්ජනයක් සැලසුම්",
            "summary_si": "වෘත්තීය සමිති නොවැම්බර් 30 වැනිදා වැඩ වර්ජනයක් පැවැත්වීමට සැලසුම් කර තිබේ.",
            "link": "https://example.com/factual-education-news",
            "published": 1795357000,
        }
        self.now = 1795357200
        self.state = {"tiktok_started_at": self.now - 500,
                      "reels": {"fresh-news": {
                          "at": self.now - 120, "status": "delivered",
                          "article": self.article,
                          "destinations": {"facebook": "accepted", "telegram": "accepted"}}}}

    def reply(self, data, code="ok", status=200):
        r = MagicMock(status_code=status)
        r.json.return_value = {"data": data,
                               "error": {"code": code, "message": ""}}
        return r

    def test_default_mode_does_not_call_api_and_keeps_queue(self):
        session = MagicMock()
        with patch.dict("os.environ", {"SLNEWS_TIKTOK_MODE": "off"}, clear=True):
            out = tt.process_tiktok_queue(self.state, self.now, session=session)
        self.assertEqual(out["status"], "setup_required")
        self.assertEqual(out["queued"], 1)
        session.get.assert_not_called()
        session.post.assert_not_called()

    def test_no_draft_upload_without_separate_news_credentials(self):
        session = MagicMock()
        with patch.dict("os.environ", {"SLNEWS_TIKTOK_MODE": "draft"}, clear=True):
            out = tt.process_tiktok_queue(self.state, self.now, session=session)
        self.assertEqual(out["status"], "account_authorization_required")
        self.assertEqual(out["errors"], ["missing_news_account_token"])
        session.post.assert_not_called()

    def test_wrong_account_is_rejected_before_video_upload(self):
        session = MagicMock()
        session.get.return_value = self.reply(
            {"user": {"open_id": "some-other-account"}})
        settings = {"SLNEWS_TIKTOK_MODE": "draft",
                    "SLNEWS_TIKTOK_ACCESS_TOKEN": "dummy",
                    "SLNEWS_TIKTOK_EXPECTED_OPEN_ID": "news-account"}
        with patch.dict("os.environ", settings, clear=True):
            out = tt.process_tiktok_queue(self.state, self.now, session=session)
        self.assertEqual(out["errors"], ["wrong_tiktok_account"])
        session.post.assert_not_called()

    def test_draft_upload_is_journalled_then_status_checked_without_duplicates(self):
        session = MagicMock()
        session.get.return_value = self.reply(
            {"user": {"open_id": "news-account"}})
        session.post.side_effect = [
            self.reply({"publish_id": "v_inbox_file~123",
                        "upload_url": "https://open-upload.tiktokapis.com/video/?x=1"}),
            self.reply({"status": "SEND_TO_USER_INBOX"}),
        ]
        settings = {"SLNEWS_TIKTOK_MODE": "draft",
                    "SLNEWS_TIKTOK_ACCESS_TOKEN": "dummy",
                    "SLNEWS_TIKTOK_EXPECTED_OPEN_ID": "news-account"}
        events = []
        with patch.dict("os.environ", settings, clear=True), \
             patch("slnews_tiktok._file_info", return_value=32000), \
             patch("slnews_tiktok._put_video", return_value=True) as send, \
             patch("story_reels._media_attribution", return_value=""), \
             patch("story_reels._approved_asset_attribution", return_value=""):
            first = tt.process_tiktok_queue(
                self.state, self.now, session=session,
                render=lambda article, path: (path, "branded_sinhala_voice_reel"),
                save=lambda state: events.append(state["tiktok_news"]["fresh-news"]["status"]))
            second = tt.process_tiktok_queue(
                self.state, self.now + 180,
                session=session)
        self.assertEqual(first["submitted"], 1)
        self.assertEqual(first["status"], "uploaded_waiting_tiktok_status")
        self.assertIn("submission_unconfirmed", events)
        self.assertEqual(self.state["tiktok_news"]["fresh-news"]["status"],
                         "inbox_ready_for_creator")
        self.assertEqual(second["inbox"], 1)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(session.post.call_count, 2)

    def test_direct_post_needs_reviewed_article_consent(self):
        session = MagicMock()
        session.get.return_value = self.reply(
            {"user": {"open_id": "news-account"}})
        session.post.return_value = self.reply({
            "creator_username": "slnews247",
            "privacy_level_options": ["SELF_ONLY"],
            "max_video_post_duration_sec": 600,
        })
        settings = {"SLNEWS_TIKTOK_MODE": "direct",
                    "SLNEWS_TIKTOK_ACCESS_TOKEN": "dummy",
                    "SLNEWS_TIKTOK_EXPECTED_OPEN_ID": "news-account",
                    "SLNEWS_TIKTOK_EXPECTED_USERNAME": "slnews247"}
        with tempfile.TemporaryDirectory() as folder:
            manifest=Path(folder,"approvals.json")
            manifest.write_text('{"articles":{}}',encoding="utf-8")
            with patch.dict("os.environ", settings, clear=True), \
                 patch.object(tt, "APPROVALS",manifest):
                out=tt.process_tiktok_queue(self.state,self.now,session=session)
        self.assertEqual(out["status"], "awaiting_per_video_creator_approval")
        self.assertEqual(session.post.call_count,1)  # Creator info only

    def test_unapproved_public_mode_is_not_initiated(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest=Path(folder,"approved.json")
            manifest.write_text(json.dumps({"articles": {"fresh-news":{
                "approved":True, "article_url":self.article["link"],
                "privacy_level":"PUBLIC_TO_EVERYONE"}}}))
            with patch.object(tt,"APPROVALS",manifest), \
                 patch.dict("os.environ", {"SLNEWS_TIKTOK_EXPECTED_USERNAME":"slnews247",
                                           "SLNEWS_TIKTOK_APP_AUDITED":"false"}, clear=True):
                result=tt._approved_direct(self.article,{
                  "creator_username":"slnews247",
                  "privacy_level_options":["PUBLIC_TO_EVERYONE"]})
            self.assertIsNone(result)

    def test_never_put_video_to_unknown_upload_server(self):
        with self.assertRaises(tt.TikTokError) as err:
            tt._put_video("https://malicious.example/upload","video.mp4")
        self.assertEqual(err.exception.code,"unsafe_upload_destination")

    def test_caption_only_contains_actual_news_and_brand(self):
        public=tt.build_caption(self.article,"📷 Creator / CC BY 4.0")
        self.assertIn("නොවැම්බර් 30", public)
        self.assertIn("#SLNews247", public)
        self.assertIn("Creator / CC BY 4.0", public)
        self.assertNotIn("example.com",public)


if __name__ == "__main__":
    unittest.main()
