# Sinhala World News automation

RSS → short Sinhala translation → Sinhala gTTS voice → 1080×1920 MP4 → Telegram and Facebook; optional authorized TikTok delivery.

## Run

The existing `Auto News Bot` workflow runs every three hours at minute 17 UTC (Sri Lanka: 02:47, 05:47, 08:47, 11:47, 14:47, 17:47, 20:47, 23:47). GitHub may delay scheduled jobs. Pushes build a preview without publishing. For a manual preview use Actions → Auto News Bot → Run workflow with publish unchecked. Download the `sinhala-news-…` artifact. Check its Sinhala pronunciation, translation and layout before production use.

Scheduled runs publish to the existing news destinations defined by repository secrets `TG_TOKEN`, `TG_CHAT_ID`, `FB_PAGE_ID`, `FB_PAGE_TOKEN`. Never use trading or store credentials for news. Tokens are not committed. Facebook Page permissions and Telegram bot channel admin access must remain valid.

## Reliability

Feeds have HTTP timeouts. Only articles dated within 24 hours are selected, newest first. Each job has a 20-minute limit. The renderer builds one original graphic rather than repeatedly processing every video frame. Captions include the original publisher and article link. No publisher photos are automatically reused. Summaries are short machine translations, not independently verified reporting.

`data/delivery.json` stores the pending article and confirmed destinations; `used.json` records completed stories. Both are committed after production runs, including failures. The translation cache is also preserved. The Actions summary and `delivery_report.json` distinguish failures from successes. A failed destination keeps the current story pending instead of losing it. Repair its credentials to resume. Before clearing pending state, inspect the platform for any upload that succeeded despite a lost network response. Remote uploads and GitHub commits cannot form one atomic transaction, so duplicates remain possible after ambiguous timeouts or state-save failure.

## TikTok setup

TikTok is disabled by default. Repository variable `TIKTOK_ENABLED=true` enables it only after authorizing the intended news account and setting `TIKTOK_ACCESS_TOKEN` as a secret. Set `TIKTOK_PRIVACY_LEVEL` explicitly to a privacy option approved for that account. Default is `SELF_ONLY`. Public posting requires TikTok approval; availability of a public option alone does not prove app approval. Unapproved apps are restricted by TikTok. Do not reuse the FreeSignal account automatically. This pipeline does not implement token refresh; expired authorization must be renewed. Videos over 64 MiB are rejected. Unconfirmed processing is not counted as successful delivery. Inspect TikTok before retrying a pending upload.

## Local preview

Python 3.11, FFmpeg and Noto Sinhala fonts are required.

```bash
pip install -r requirements.txt
PREVIEW_ONLY=true python main.py
```

Free translation and speech services have quotas and availability limits. No API expense is configured. This is scheduled automation, not a guarantee of uninterrupted lifetime operation. No confirmed live-delivery claim is made until workflow results and destination posts have been checked.
