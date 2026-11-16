# SL News 247 — Sri Lankan Sinhala news automation

Native Sinhala RSS headlines → fast Telegram + Facebook text alerts → Sinhala voice and 1080×1920 video → Telegram + Facebook + optional authorized TikTok.

## Production

`Auto News Bot` scans every five minutes, at UTC minutes 02, 07, 12, … 57. GitHub may delay scheduled jobs; this is not guaranteed real-time delivery. Code deployments also publish after the automated checks pass. Manual runs default to preview; select `publish` to send posts.

Every run collects these publisher feeds concurrently:

- Ada Derana Sinhala: https://sinhala.adaderana.lk/rss.php
- Dinamina: https://www.dinamina.lk/feed/
- Divaina: https://divaina.lk/feed/
- Lankadeepa latest: https://www.lankadeepa.lk/rss/latest_news/1
- Lankadeepa business: https://www.lankadeepa.lk/rss/business/9

The source health report records HTTP failures, feed counts and fresh Sinhala story counts. No firewall bypass is attempted. Native Sinhala avoids translation delays and translation quotas. Sri Lankan publishers cover national, regional, political, business, sport and international stories; this does not guarantee every article from every Sri Lankan outlet. Feed coverage and publisher delay affect availability.

Up to five fresh, undelivered stories are sent per run. Only dated stories from the past 12 hours are eligible. Exact normalized headline fingerprints suppress duplicate titles across sources. Similar stories with different headlines may still appear. Posts include a short excerpt, publisher link and publication time in Asia/Colombo. No full article or publisher photograph is republished. Headlines are source reporting, not independently verified claims.

One new video is attempted every 30 minutes after headline delivery. Videos use original graphics, native Sinhala feed text and gTTS Sinhala voice. Free speech services can fail or be rate-limited. A video failure does not prevent text alerts.

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
