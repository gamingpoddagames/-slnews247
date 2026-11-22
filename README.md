# SL News 247 — Sri Lankan Sinhala news automation

## TikTok automation — existing SL NEWS 24/7 project (22 Nov 2026)

This update extends the **same** five-minute `Auto News Bot` and the already
working `story_reels.py` output. It does **not** create a separate account,
bot or repository. Original matching Sinhala vertical video is rendered from
approved event clips, a verified named photo, or factual illustrated scenes.
A reel first succeeds on Facebook and Telegram, then becomes an independent
TikTok news queue item. Upload history lives in the merged
`data/sri_lanka_delivery.json` under `tiktok_news`; it never blind-retries
ambiguous uploads and stops duplicate reels.

**IMPORTANT:** There is not yet a confirmed authorized **SL News 24/7** TikTok
account for this repository. Older `TIKTOK_ACCESS_TOKEN` is intentionally NOT
used because it may belong to another account. TikTok publishing is OFF by
default. The presence of code or a green GitHub run does not mean that TikTok
has published a public video.

### Connect the correct TikTok news account

1. Use the existing **Sinhala World News** TikTok developer app if its current
   configuration and review status allow it, and authorize a **dedicated SL News 24/7**
   TikTok profile (not the FreeSignal trading profile). Apply for Login Kit
   `user.info.basic` plus either Content Posting `video.upload` (draft
   handoff), or `video.publish` (direct-post mode, subject to TikTok audit
   and individual video consent).
2. In GitHub repository **Settings > Secrets and variables > Actions > Secrets**,
   set `SLNEWS_TIKTOK_ACCESS_TOKEN` using the news account's OAuth access
   token, and `SLNEWS_TIKTOK_EXPECTED_OPEN_ID` using the same OAuth account's
   returned `open_id`. Never copy a trading account token here. The open ID
   is checked before *any* TikTok upload.
3. For private draft handoff, set repository **Variable**
   `SLNEWS_TIKTOK_MODE=draft`. Videos may be uploaded to the TikTok inbox,
   but the account owner must click the inbox notification and publish them
   in TikTok. Scope `video.upload` and app authorization are needed.
4. For Direct Post (which requires `video.publish` and TikTok app audit for
   public viewership), choose `SLNEWS_TIKTOK_MODE=direct`, set
   `SLNEWS_TIKTOK_EXPECTED_USERNAME` to the exact news account handle
   (without `@`), and use `data/tiktok_approved_posts.json` for
   creator-approved **individual** videos. Review each actual rendered video,
   post title, privacy, copyright disclosures and interaction controls.
   Example approval once the specific video has been reviewed:

   ```json
   {"articles":{"EXACT_ARTICLE_ID":{
     "approved":true,
     "article_url":"https://same-original-article-url.example/news",
     "privacy_level":"SELF_ONLY"
   }}}
   ```

   TikTok automatically limits unaudited Direct Posts to private visibility;
   **do not** set `SLNEWS_TIKTOK_APP_AUDITED=true` unless TikTok actually
   approved the app for Direct Post. A public post needs
   `PUBLIC_TO_EVERYONE` as an offered creator privacy choice and
   corresponding approval for that exact video. Some accounts or apps may be
   ineligible for Direct Post despite correct credentials.

5. Go to **Actions > SL News TikTok connection check > Run workflow** for a
   safe non-publishing account and permission check. The five-minute news
   workflow subsequently publishes only authorized, queued TikTok media.
   `SLNEWS_TIKTOK_MAX_PER_DAY` is restricted to two attempts per 24 hours
   in GitHub Actions, with at least three hours between attempts.
   Existing Facebook and Telegram publishing is unaffected.

TikTok draft upload is **not** public publication. The program records
`publish_id`, checks `status/fetch` on future runs, and distinguishes
`SEND_TO_USER_INBOX`, `PUBLISH_COMPLETE`, in-progress and failed attempts.
A source-rights credit legally required by the image or clip's license remains
in the TikTok caption. No unrelated image is used.

**Token life cycle:** TikTok user access tokens expire, and refreshing may
rotate the refresh token. The OAuth account connection must provide a secure
token-refresh service for indefinite unattended operation; a static GitHub
secret alone is not permanent. This repository deliberately does not store
tokens or unencrypted refresh tokens in its version-controlled files.

Official API documentation:
- https://developers.tiktok.com/docs/en/content-posting-api-get-started
- https://developers.tiktok.com/docs/en/content-posting-api-get-started-upload-content
- https://developers.tiktok.com/docs/en/oauth-user-access-token-management/
- https://developers.tiktok.com/docs/en/content-sharing-guidelines

## Current production upgrade — 22 November 2026

The **existing** repository and configured Facebook Page / Telegram channel are
used; this is **not a new project**. The live entrypoint is fast_news.py and the
Auto News Bot GitHub Actions workflow runs on a best-effort 5-minute schedule.

- **Every eligible story:** verify Sinhala headline and factual summary, send
  a consistent SL NEWS 24/7 image post on both platforms, and persist receipts.
  Prefer approved exact-event photographs, then vetted *named-institution*
  photographs (for example the real Central Bank building only for CBSL news).
  If neither is usable, publish an original headline graphic without a fake
  event image.
- **Every new completed story:** queue a separate vertical video in
  story_reels.py. Authorized same-event clips can be edited with original
  Sinhala narration; otherwise use real approved images with motion graphics,
  or fully original animated scenes. If online voice fails, produce a playable
  motion-graphic video without invented narration. The queue survives RSS scans.
- **Duplicate protection:** do not publish an older completed original
  bulletin again as an additional reel. Preserve per-platform intent/receipts
  in data/sri_lanka_delivery.json; ambiguous API results must be inspected
  before another attempt.
- **Presentation:** one consistent branded style, no irrelevant event clips,
  misleading pictures or unnecessary source/about-image text in public news.
  Mandatory Creative Commons attribution remains where a media licence
  requires it; full provenance and evidence stay in private workflow records.
- **Practical limits:** a green workflow confirms execution, not necessarily
  delivery; check the output delivery_report.json and platform receipts.
  Source outages, missing verified facts, external voice/API outages, platform
  permissions and GitHub scheduling can delay publication; do not pretend to
  have delivered when a platform has not acknowledged it.

Relevant files: fast_news.py, real_photo.py, institution_photo.py, image.py,
animated_bulletin.py, story_reels.py, media.py, facebook.py, telegram.py,
and .github/workflows/news.yml. No additional bot tokens are required beyond
the existing account secrets. The older sections below describe legacy steps
and may refer to superseded posting modes.


Native Sinhala RSS headlines → fast Telegram + Facebook alerts with optional verified event photos → Sinhala voice and 1080×1920 video → Telegram + Facebook + optional authorized TikTok.

## Production

`Auto News Bot` scans every five minutes, at UTC minutes 02, 07, 12, … 57. GitHub may delay scheduled jobs; this is not guaranteed real-time delivery. Code deployments also publish after the automated checks pass. Manual runs default to preview; select `publish` to send posts.

Every run collects these publisher feeds concurrently:

- Ada Derana Sinhala: https://sinhala.adaderana.lk/rss.php
- Dinamina: https://www.dinamina.lk/feed/
- Divaina: https://divaina.lk/feed/
- Lankadeepa latest: https://www.lankadeepa.lk/rss/latest_news/1
- Lankadeepa business: https://www.lankadeepa.lk/rss/business/9

The source health report records HTTP failures, feed counts and fresh Sinhala story counts. No firewall bypass is attempted. Native Sinhala avoids translation delays and translation quotas. Sri Lankan publishers cover national, regional, political, business, sport and international stories; this does not guarantee every article from every Sri Lankan outlet. Feed coverage and publisher delay affect availability.

Up to five fresh, undelivered stories are sent per run. Only dated stories from the past 12 hours are eligible. Exact normalized headline fingerprints suppress duplicate titles across sources. Similar stories with different headlines may still appear. Public captions include a short excerpt and publication time in Asia/Colombo, without visible publisher names or article links. Publisher URLs remain in internal story records. No full article or publisher photograph is republished. Headlines are source reporting, not independently verified claims.

One new video is attempted every 30 minutes after headline delivery. Videos are made only when a reviewed exact-event photo exists, using native Sinhala feed text and gTTS Sinhala voice. Free speech services can fail or be rate-limited. A video failure does not prevent text alerts.

## Accounts and credentials

The existing news accounts are used through repository secrets `TG_TOKEN`, `TG_CHAT_ID`, `FB_PAGE_ID`, `FB_PAGE_TOKEN`. Telegram bot channel admin access and Facebook Page posting permissions must remain valid. Credentials are never committed. The intended news Telegram channel was previously confirmed as `@slnews247` from historical delivery logs.

TikTok remains disabled until the intended news account is authorized. Set secret `TIKTOK_ACCESS_TOKEN`, then explicitly set repository variables `TIKTOK_ENABLED=true` and `TIKTOK_PRIVACY_LEVEL` to an approved privacy option. Default privacy is `SELF_ONLY`. Public Direct Posting requires TikTok app approval; an available public privacy option alone does not prove approval. Current TikTok integration does not refresh expired tokens automatically. Do not substitute the FreeSignal account for the news account. Until authorization and app approval are completed, this is not fully automated public TikTok publishing.

## Receipts, failures and retries

`data/sri_lanka_delivery.json` records headline receipts and video attempts. Each destination is checkpointed separately, preventing routine duplicate retries. A confirmed rejected request can retry later. A lost or undecodable response is marked uncertain and is not automatically resent; other stories continue. Inspect the actual channel/Page before removing that story's `uncertain` destination flag. This avoids blindly duplicating a post that may have succeeded. Video attempts are recorded before uploading; failed/unconfirmed attempts are reported for inspection, rather than automatically resent. State saves run even when the pipeline fails. Remote posting and GitHub commits cannot be atomic, so a state-save failure still requires inspection.

The Actions summary and downloadable `sinhala-news-…` artifact contain `delivery_report.json`, selected stories, and any rendered MP4/PNG. No fresh stories is a normal no-op. All feeds failing, or rejected/unconfirmed text delivery, makes the job fail visibly.

## Preview and checks

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
PREVIEW_ONLY=true python fast_news.py
```

Python 3.11, FFmpeg and Noto Sinhala fonts are required. Preview creates output without posting or persisting production delivery state. The previous `main.py` remains as a legacy world-news entry point; the workflow now uses `fast_news.py`.

## Exact-event visuals only

Generic stock photos, topic-based photos and unrelated footage are disabled. Missing, unavailable or unverified media produces a text-only Telegram/Facebook post; no placeholder photo or video is published. Without a verified event photo, video generation is skipped before voice generation.

`data/verified_event_media.json` is an exact-story approval registry, initially empty. Each entry must match the story ID and full article URL, and record `verified_event: true`, `rights_verified: true`, `attribution_required: false`, `verification_notes`, `rights_evidence`, HTTPS `url` and the original file `sha256`. A publisher thumbnail alone is neither event verification nor a reuse license. No automatic scraper supplies these approvals. This means automatic event-photo acquisition is not currently available: until an asset has been reviewed and entered, that story remains text-only.

Downloaded bytes must match the approved SHA-256. `data/event_media_usage.json` binds each photo hash to one story. The same photo may accompany the same story on Telegram, Facebook and its video, but cannot be used for a different story. The usage ledger is retained across runs. A failed download falls back to text.

Public captions omit publisher names and article links, while internal story records retain them. Only media whose verified permission does not require visible attribution is eligible. Removing a credit does not grant reuse rights. Existing previously published posts are not automatically deleted or edited. Newly deployed and scheduled runs use this strict policy.

## Genuine video clips

The automated video branch now requires `choose_video`, not a still photograph. It never converts a photo into a news video. Add a `video` object under the exact article ID in `data/verified_event_media.json`; it requires all the exact-event/right-to-use fields above plus `real_footage_verified: true`. A photo can coexist under `photo`. Video files are checked with FFprobe, their approved SHA-256 and the cross-story reuse ledger. A registry entry is evidence of a prior review, not an automatic truth classifier.

Reviewed moving footage is fitted into the Sinhala news layout, with original clip audio muted and a maximum duration of 90 seconds. No clip looping, stock fallback, freeze-frame extension or generated footage is used. This branch adds Sinhala TTS from the matching reviewed original editorial brief. Missing briefs or failed narration skip the video. Complete narration must fit the available footage and 90 seconds; longer narration is rejected rather than cut, looped or padded. A missing verified video skips video publication while news text and eligible exact-event photos continue. There is currently no authorized exact-event clip provider connected and no reviewed clip in the registry; no real-event clip has been published as part of this change.

## Original editorial briefs and official video links

`data/editorial_briefs.json` stores original Sinhala summaries keyed by exact story ID. Entries must include the matching `article_url`, `body_si`, `source_refs`, and `facts_reviewed: true`. These expand new posts when available; previously published posts are not edited or re-sent. If no reviewed brief exists, the existing feed summary remains. This is a separate editorial process, not an LLM API in the GitHub job.

An entry can also include an exact-story `official_video_url` (YouTube watch link), `official_video_verified: true`, and `official_video_evidence` recording how the original channel and event match were checked. When no licensed uploadable footage exists, the pipeline can share that official video link with a preview on Telegram/Facebook. This is a link to the publisher's original player, not an MP4 upload, and is reported as `official_video_link`. Do not mark an unrelated channel livestream, search result or compilation as an exact-story clip. No official video link has been approved yet. TikTok cannot receive these link posts through this uploader.

Reviewed briefs are sent once as a separate `විස්තරාත්මක පුවත` update on Telegram/Facebook. Existing fast posts are preserved. `editorial_updates` records each attempt; lost responses are not blindly re-sent. At most one new editorial update is sent per scan. These are original factual summaries rather than full copies of publisher articles. The editorial task can prepare up to three reviewed briefs per hourly run; this is distinct from the five-minute RSS scans.

## Broader source coverage and speed

The scanner now configures nine feed endpoints: the original five plus Siyatha News, ITN News, Lankasara Sinhala and Newsfirst Sinhala. Each endpoint is attempted concurrently, with timeouts and HTTP/fresh-story counts reported independently. Configured does not mean reachable: several publishers reject GitHub cloud requests. `data/source_health.json` records the latest production source status. All-channel or all-article coverage is not guaranteed. No firewall bypass or copied TV broadcast is used. Reviewed real-footage videos are eligible every 15 minutes when a new approved clip exists. The scan remains every five minutes (GitHub can delay schedules), and the delivery batch is increased from five to ten unique stories per scan.

Video-labelled stories from supported publisher sites are checked for a single YouTube player within the exact article content. Sidebar/global livestream embeds and multi-player ambiguity are rejected. Up to three article pages are checked per scan; results are cached for an hour. The resulting publisher-embedded video link is shared on Telegram/Facebook with link preview enabled, not uploaded as our own clip. A real MP4 still requires reviewed reuse permission. This does not guarantee player availability, embedding rights on every platform, or a video for every story.

Sri Lankan TV publishers researched include Ada Derana, Hiru, Newsfirst, Siyatha, ITN, Rupavahini and Swarnavahini. Only sources whose configured feed can actually be retrieved contribute stories. The last two do not yet have verified working RSS connectors in this project; their entire TV output is not connected. Do not describe this deployment as all Sri Lankan TV channels connected.
