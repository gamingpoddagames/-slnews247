# SL News 247 — Sri Lankan Sinhala news automation

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

Reviewed moving footage is fitted into the Sinhala news layout, with original clip audio retained and a maximum duration of 90 seconds. No clip looping, stock fallback, freeze-frame extension or generated footage is used. This branch does not add Sinhala TTS over the original clip. A missing verified video skips video publication while news text and eligible exact-event photos continue. There is currently no authorized exact-event clip provider connected and no reviewed clip in the registry; no real-event clip has been published as part of this change.

## Original editorial briefs and official video links

`data/editorial_briefs.json` stores original Sinhala summaries keyed by exact story ID. Entries must include the matching `article_url`, `body_si`, `source_refs`, and `facts_reviewed: true`. These expand new posts when available; previously published posts are not edited or re-sent. If no reviewed brief exists, the existing feed summary remains. This is a separate editorial process, not an LLM API in the GitHub job.

An entry can also include an exact-story `official_video_url` (YouTube watch link), `official_video_verified: true`, and `official_video_evidence` recording how the original channel and event match were checked. When no licensed uploadable footage exists, the pipeline can share that official video link with a preview on Telegram/Facebook. This is a link to the publisher's original player, not an MP4 upload, and is reported as `official_video_link`. Do not mark an unrelated channel livestream, search result or compilation as an exact-story clip. No official video link has been approved yet. TikTok cannot receive these link posts through this uploader.

Reviewed briefs are sent once as a separate `විස්තරාත්මක පුවත` update on Telegram/Facebook. Existing fast posts are preserved. `editorial_updates` records each attempt; lost responses are not blindly re-sent. At most one new editorial update is sent per scan. These are original factual summaries rather than full copies of publisher articles. The editorial task can prepare up to three reviewed briefs per hourly run; this is distinct from the five-minute RSS scans.
