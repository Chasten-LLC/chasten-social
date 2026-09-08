# Reel routine: retired 2026-09-07

The Mon/Wed/Fri Reel no longer uses a Claude routine. The GitHub Action
`.github/workflows/reel.yml` builds the Moment, writes the caption
(`tools/reels/caption.py`), commits, and posts to Slack itself
(`tools/notify_slack.py`), because:

- a push made with the workflow token triggers no other workflow, so the
  Action's own commit could never fire the Slack notifier;
- GitHub runs schedules late, hours late on this repo, so a routine timed to
  follow the build cannot be trusted to find the video;
- the routine's only fallback was email, and Ric wants Slack only.

The routine `trig_01DhGtNUJXtghzEeC8b31iaA` is disabled. Publishing still waits
for Ric's thumbs up in Slack.
