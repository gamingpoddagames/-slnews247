# SL NEWS 24/7 direct Public TikTok delivery

The existing Auto News Bot and Blogger mirror runs call `vidiq_tiktok_bridge.py`
after a confirmed Facebook, Telegram or Blogger receipt. There is no separate
TikTok workflow, timer, scheduled post, or creator-inbox upload. One TikTok item
per story uses the existing original image or narrated reel, including the
existing design, Sinhala voice and mandatory media credits. Only stories within
12 hours qualify. Previous public TikTok items and uncertain submissions are
protected against duplicate creation.

The dedicated encrypted publishing connection is hosted at:

https://everydaykit.gamingpoddagames.workers.dev/slnews247/vidiq/connect

The owner connects the existing vidIQ account that already owns TikTok
`@slnewstwentyfourseven`. The callback verifies the exact account and publishing
eligibility. GitHub authenticates using short-lived OIDC restricted to this
repository's main-branch news and Blogger workflows. The runner receives no
vidIQ refresh token. Existing TikTok sandbox and FreeSignal connections remain
independent.

Both workflows initially set `SLNEWS_VIDIQ_PUBLISH_ENABLED: 'false'`. After the
owner completes the connection, set that value to `'true'` in both workflows.
The news workflow change triggers the existing production run. Before that,
`tiktok_direct.status` reports `awaiting_owner_connection`; this is not evidence
of TikTok publication. Facebook and Telegram continue normally.

The approved TikTok values are Public, comments enabled, original Sinhala audio
and no added TikTok music. Read the independent `vidiq_tiktok` journal and its
confirmed public URL; a successful Actions job alone does not prove publication.
The older native `SLNEWS_TIKTOK_MODE` may remain off while this connection is used.
Never reset delivery journals or blindly retry an unknown publication outcome.
GitHub scheduling remains best-effort and the existing recovery check remains in
place. The owner's PC can be off while GitHub and Cloudflare run.
