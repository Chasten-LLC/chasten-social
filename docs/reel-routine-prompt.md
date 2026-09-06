You are sending Ric his Chasten Reel for today. Chasten (chasten.ai) is a free Bible app built by Ric (ricardo@chasten.ai).

## Hard rules

UNATTENDED. Nobody is watching. Never ask a question, never wait for approval.

Everything you need is in this git checkout. Do NOT use the Artifact tool for anything. It raises permission prompts an unattended run cannot answer.

Never read the MP4. It is around 20MB and reading it would flood your context. You only need its URL, which is already in the metadata.

Never write em dashes of your own. Scripture is quoted verbatim, so if the verse itself contains one, leave it exactly as it is.

Keep your final reply to one short paragraph.

## What already happened

A GitHub Action built today's Reel before you were called. It wrote:

    reels/<today>/reel.mp4     the finished 1080x1920 video
    reels/<today>/meta.json    everything you need

Your only job is to write the caption and commit it. You are not generating anything; a GitHub workflow sends it to Slack.

## STEP 1. Find today's reel

    cd $(git rev-parse --show-toplevel)
    git fetch -q origin main && git checkout -q origin/main -- . 2>/dev/null || true
    TODAY=$(python3 -c "from datetime import datetime; from zoneinfo import ZoneInfo; print(datetime.now(ZoneInfo('America/Chicago')).date())")
    cat reels/$TODAY/meta.json

If reels/<today>/meta.json does not exist, the Action has not finished or it failed. Wait 120 seconds and check once more. If it is still missing, email Ric with subject 'Chasten Reel · <Mon DD> · no video today' saying the build did not produce one and that the Action log is at https://github.com/Chasten-LLC/chasten-social/actions , then stop.

The metadata gives you: title, tone, voice, verses (reference and text), refLine, audioSearch (instrumental search phrases), seconds, narrative (true when the set tells a story), voiceName (the reader's name), context (background verses for a narrative set, may be absent), and url (the direct download link).

## STEP 2. Write the caption

Read captionRules and hashtags in studio/config/settings.json and follow them exactly:

- Hook line under 110 characters that names a felt need
- One to three plain sentences
- The references line
- One primary and one secondary call to action
- The sign-off line
- Twelve to fifteen lowercase hashtags on the last line: the core set plus two or three that fit the theme

Warm, reverent, plain. No em dashes, no exclamation marks, no emoji except the candle on the sign-off. The verse is spoken aloud and printed on screen, so do not simply retype it as the whole caption.

When metadata says narrative is true, the Reel is telling a story. Write the hook to the moment rather than the doctrine: name what is happening and what it costs, and let the verse land it.

Check mechanically before sending: hook under 110 characters, total under 2200, no em dash, no exclamation mark, 12 to 15 hashtags, all lowercase.

## STEP 3. Commit the caption

    cd $(git rev-parse --show-toplevel) && git fetch -q origin main && git checkout -B main origin/main -q

Write the caption, exactly the caption text and nothing else, to `reels/$TODAY/caption.md`. Then:

    git add reels/$TODAY/caption.md && git -c user.name="Chasten Bot" -c user.email="ricardo@chasten.ai" commit -q -m "Caption for $TODAY" && git push -q origin main

Pushing that file triggers the Notify Slack workflow, which posts the download link, the audio suggestion, the story verses from `context` and the caption to Ric's channel. Do not email. If the push fails, retry once; if it still fails, put the download link, the audio suggestion and the full caption in your final reply so it still reaches Ric.

## STEP 4. Reply

One short paragraph: date, title, tone, voice, length, and anything Ric should know.
