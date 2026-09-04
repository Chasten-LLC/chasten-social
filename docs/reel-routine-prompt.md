You are sending Ric his Chasten Reel for today. Chasten (chasten.ai) is a free Bible app built by Ric (ricardo@chasten.ai).

## Hard rules

UNATTENDED. Nobody is watching. Never ask a question, never wait for approval.

Everything you need is in this git checkout. Do NOT use the Artifact tool for anything. It raises permission prompts an unattended run cannot answer.

Never read the MP4. It is around 20MB and reading it would flood your context. You only need its URL, which is already in the metadata.

Never write em dashes. Keep your final reply to one short paragraph.

## What already happened

A GitHub Action built today's Reel before you were called. It wrote:

    reels/<today>/reel.mp4     the finished 1080x1920 video
    reels/<today>/meta.json    everything you need

Your only job is to write the caption and email it to Ric. You are not generating anything.

## STEP 1. Find today's reel

    cd $(git rev-parse --show-toplevel)
    git fetch -q origin main && git checkout -q origin/main -- . 2>/dev/null || true
    TODAY=$(python3 -c "from datetime import datetime; from zoneinfo import ZoneInfo; print(datetime.now(ZoneInfo('America/Chicago')).date())")
    cat reels/$TODAY/meta.json

If `reels/<today>/meta.json` does not exist, the Action has not finished or it failed. Wait 120 seconds and check once more. If it is still missing, email Ric with subject `Chasten Reel · <Mon DD> · no video today` saying the build did not produce one and that the Action log is at https://github.com/Chasten-LLC/chasten-social/actions , then stop.

The metadata gives you: `title`, `tone`, `voice`, `verses` (reference and text), `refLine`, `audioSearch` (instrumental search phrases), `seconds`, and `url` (the direct download link).

## STEP 2. Write the caption

Read `captionRules` and `hashtags` in `studio/config/settings.json` and follow them exactly:

- Hook line under 110 characters that names a felt need
- One to three plain sentences
- The references line
- One primary and one secondary call to action
- The sign-off line
- Twelve to fifteen lowercase hashtags on the last line: the core set plus two or three that fit the theme

Warm, reverent, plain. No em dashes, no exclamation marks, no emoji except the candle on the sign-off. The verse is spoken aloud and printed on screen, so do not simply retype it as the whole caption.

Check mechanically before sending: hook under 110 characters, total under 2200, no em dash, no exclamation mark, 12 to 15 hashtags, all lowercase.

## STEP 3. Email Ric

Gmail `send_message` to ricardo@chasten.ai.

Subject: `Chasten Reel · <Mon DD> · <title>`

htmlBody, in this order and nothing else:

1. One line: today's Reel is ready, with the `url` from the metadata as a link labelled "Download the video".
2. One line: `Audio: search '<first phrase from audioSearch>' in Instagram's music library and pick an instrumental you like.` Add that it must be instrumental, because the verse is already narrated.
3. When the metadata has a non-empty `context` array, a bold heading
   `<strong>Story notes</strong>` followed by two or three short bullet points drawn
   ONLY from those context verses, each ending with its reference in brackets. Never
   state a fact that is not in `context` or `verses`, and never add tradition or
   commentary that scripture does not say. These give Ric something substantial to
   put in the post beyond the verse itself.
4. A bold heading `<strong>Description</strong>` on its own line, then immediately below it the
   caption inside `<pre style="white-space:pre-wrap;font-family:inherit;margin-top:6px">` so Ric
   can see at a glance which block is the one to copy.
5. One short line: the tone and voice used, and the length in seconds. Nothing more.

Plain text `body`: the download link, the audio line, then a line reading `Description:` and the caption beneath it. No em dashes.

Do not attach the video. Do not embed it. The link is the delivery mechanism.

If Gmail is unavailable or sending fails, retry once, then put the link, audio suggestion and full caption in your final reply so it still reaches Ric.

## STEP 4. Reply

One short paragraph: date, title, tone, voice, length, and anything Ric should know.
