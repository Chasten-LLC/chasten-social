# chasten-social

Everything the daily Chasten Instagram post needs, and the public home of the
cards it publishes.

A Claude Code cloud routine fires daily at 12:00 UTC (7:00am America/Chicago
during daylight saving), renders three 1080x1350 verse cards and a closing follow card, commits them here,
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
studio/library/backgrounds.json  the photos in rotation: ink, scrim, dim, credit
studio/library/backgrounds-retired.json  the earlier pool, kept to restore
studio/bg/<id>.jpg               background photos, cut to 1080x1350
tools/ig_run.py                  orchestration: bootstrap, plan, render, preview, package
tools/chasten_cards.py           the renderer
tools/add_backgrounds.py         cuts new photos for Instagram and adds them
tools/assets/fonts/*.ttf         Literata and Inter
tools/assets/img/*.png           wordmarks
posts/<YYYY-MM-DD>/1.jpg 2.jpg ...    the published cards, one per slide
posts/<YYYY-MM-DD>/post.json           what was posted, with caption and permalink
docs/routine-prompt.md           the prompt the routine runs
```

Public URL pattern:

```
https://raw.githubusercontent.com/Chasten-LLC/chasten-social/main/posts/<YYYY-MM-DD>/1.jpg
```

## Backgrounds

Since 2026-09-29 the photos in rotation are the app's Verse of the Day photos,
so the feed looks like the app. To add more, put the originals in a folder and
run:

```bash
python3 tools/add_backgrounds.py ~/Downloads/chasten-florals
```

It cuts each photo to 1080x1350 around its subject (a `FOCUS_X` override fixes
the rare wrong pick), chooses light or dark ink from how bright the verse area
is, and gives busy or patchy photos an extra `dim` veil so the verse always
reads. Photos already in the pool are skipped. The earlier pool is listed in
`studio/library/backgrounds-retired.json`; its photos are still in `studio/bg`.

## Verse sets

Every set carries at least three verses, so every carousel has three verse
cards and the follow card. Story sets (kind `narrative`) keep their key verse
first and add the verses that finish the moment; the reel builder reads only
the first `verseCount` of them, so a story's reel is unchanged.

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

## The 11 AM post: Scripture in the world

A second routine, "Chasten 11 AM Instagram post" (`0 16 * * *`, 11:00am Central in
daylight time; move it to `0 17 * * *` on 2026-11-01), posts a carousel of photographs
with one short line placed in each scene: a billboard, a cafe chalkboard, a note on a
dashboard, a departure board. Its prompt is `docs/world-routine-prompt.md`, which must
match the live one.

- **Lines** live in `studio/world/lines.json`. Most are word-for-word BSB fragments;
  `python3 tools/check_world_lines.py` checks every one against the app's Bible
  (`../chasten-bible-app/assets/bible/bible.db`) and must pass before a line ships.
  Two a day are our own conversational lines, printed with the verse they come from.
  Those are never signed "God", never presented as Scripture, and never promise what
  Scripture does not.
- **Scenes** live in `studio/world/scenes.json`. Every scene forbids other words, and
  boards state their row count, or the model adds headers and nonsense letters.
  Scenes never include a phone, app or website screen: Scripture on a screen must look
  like Chasten's own app.
- **Drawing** is Google's `gemini-3-pro-image`, about $0.13 a slide at 2K. The key is an
  API credential on the routines' shared cloud environment (header `x-goog-api-key`,
  host `generativelanguage.googleapis.com`), so no file or variable holds it. On a Mac,
  `tools/world_run.py` reads `GEMINI_API_KEY` or `--env-file`.
- **Checking:** the routine reads every slide back, and `world_run.py verify` compares
  the words with the plan. A failed slide is redrawn once and then left out.
- **Staging:** a post Ric approves in advance goes in `world/<date>/` with its cards
  and a `staged.json`; the routine publishes it as is that day.
- **State** is `studio/state/world-pointer.json` (theme rotation, the lines and scenes
  of the last posts). Records live in `world/<date>/post.json`, which triggers the
  Slack notice.

Try a day's plan without drawing: `python3 tools/world_run.py plan /tmp/w --date 2026-10-01`.

## The dashboard

The "Chasten Instagram Studio" artifact still holds the history written before
this migration. It is no longer updated by the run. Post records now live beside
their cards in `posts/<date>/post.json`.
