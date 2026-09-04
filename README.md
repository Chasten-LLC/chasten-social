# chasten-social

Image host for Chasten's daily Instagram verse post.

This repo exists for one reason: Instagram's Graph API can only publish an image
it can fetch from a public URL. The daily routine renders three 1080x1350 JPEG
cards, commits them here, and hands the `raw.githubusercontent.com` URLs to
Instagram. Nothing else lives here.

## Layout

```
posts/<YYYY-MM-DD>/1.jpg   slide 1
posts/<YYYY-MM-DD>/2.jpg   slide 2
posts/<YYYY-MM-DD>/3.jpg   slide 3
```

Public URL pattern:

```
https://raw.githubusercontent.com/Chasten-LLC/chasten-social/main/posts/<YYYY-MM-DD>/1.jpg
```

## Where the rest of the system lives

| Piece | Location |
|---|---|
| Verse sets, backgrounds, fonts, wordmarks | Artifact DB, collections `verses` `library` `bg` `fonts` `assets` |
| Renderer (`ig_run.py`, `chasten_cards.py`) | Artifact DB, collection `code` |
| Settings (caption rules, hashtags, audio, host mode) | Artifact DB, `config/settings` |
| Rotation state (which set is next) | Artifact DB, `state/pointer` |
| Post archive | Artifact DB, collections `posts` and `cards` |
| Dashboard | https://claude.ai/code/artifact/5c46d039-2e10-43b4-a8d4-993d9645f4c2 |

The Artifact database is the source of truth. This repo is a CDN.

## The routine

A Claude Code cloud routine fires daily at 12:00 UTC (7:00am America/Chicago
during daylight saving). It runs in Anthropic's cloud, so it does not need this
machine to be awake. Manage it at https://claude.ai/code/routines

Because cron is UTC and does not follow daylight saving, the cron needs to move
from `0 12 * * *` to `0 13 * * *` when Central switches to standard time on
2026-11-01, to stay at 7:00am local.
