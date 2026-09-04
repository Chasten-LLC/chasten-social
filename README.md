# chasten-social

Everything the daily Chasten Instagram post needs, and the public home of the
cards it publishes.

A Claude Code cloud routine fires daily at 12:00 UTC (7:00am America/Chicago
during daylight saving), renders three 1080x1350 verse cards, commits them here,
and publishes them to Instagram as a carousel using their public GitHub URLs.
It runs in Anthropic's cloud, so it does not need any particular machine awake.

## Why everything lives in git

This repo is the single source of truth on purpose. The system used to keep its
code, fonts, photos and rotation state in an Artifact database, but every read
that wrote a file to disk raised a permission prompt, and those grants do not
persist between runs. An unattended 7am run cannot answer a prompt, so it would
stall. Keeping it all in git means the routine reads files it already has and
touches no permissioned API. Zero prompts.

## Layout

```
studio/config/settings.json      caption rules, hashtags, audio map, email rules
studio/state/pointer.json        rotation state, the only file the run mutates
studio/verses/sets.json          the verse sets, in rotation order
studio/library/backgrounds.json  background manifest: ink, scrim, credit
studio/bg/<id>.jpg               67 background photos
tools/ig_run.py                  orchestration: bootstrap, plan, render, preview, package
tools/chasten_cards.py           the renderer
tools/assets/fonts/*.ttf         Literata and Inter
tools/assets/img/*.png           wordmarks
posts/<YYYY-MM-DD>/1.jpg 2.jpg 3.jpg   the published cards
posts/<YYYY-MM-DD>/post.json           what was posted, with caption and permalink
docs/routine-prompt.md           the prompt the routine runs
```

Public URL pattern:

```
https://raw.githubusercontent.com/Chasten-LLC/chasten-social/main/posts/<YYYY-MM-DD>/1.jpg
```

## Running it by hand

```bash
W=$PWD/.igrun
rm -rf "$W"; mkdir -p "$W/db" "$W/work"
cp -r studio/config studio/state studio/verses studio/library "$W/db/"
python3 tools/ig_run.py bootstrap "$W"
CHASTEN_DATE=$(date +%F) python3 tools/ig_run.py plan "$W"
python3 tools/ig_run.py render "$W"
python3 tools/ig_run.py preview "$W"
```

Needs Pillow. `render` reads backgrounds from `studio/bg` via `CHASTEN_REPO`,
defaulting to the parent of the work directory.

## The routine

Managed at https://claude.ai/code/routines

Cron is UTC and does not follow daylight saving, so `0 12 * * *` is 7:00am
Central only during daylight time. It needs to move to `0 13 * * *` when Central
returns to standard time on 2026-11-01.

## The dashboard

The "Chasten Instagram Studio" artifact still holds the history written before
this migration. It is no longer updated by the run. Post records now live beside
their cards in `posts/<date>/post.json`.
