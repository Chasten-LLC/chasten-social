You are checking Chasten's daily word reel routine inside this cloud sandbox. This is a DRY RUN. Never publish anything, never push, never commit, never call Composio, Instagram, PushNotification or any notification tool, and never use the Artifact tool. Never write em dashes. Never look for or print any key. Counts from PostHog only: never look up or print a person, an id or any other property.

The live routine's prompt is docs/word-routine-prompt.md. This run follows its steps up to the point of posting, on the date given below, and reports what each step printed.

Run exactly this, then reply:

    cd $(git rev-parse --show-toplevel) && R=$PWD
    python3 --version; git log --oneline -1
    python3 -c "from datetime import datetime; from zoneinfo import ZoneInfo; n=datetime.now(ZoneInfo('America/Chicago')); print(n.date(), n.hour)"
    D=$(python3 -c "import json; d=json.load(open('word/schedule.json'))['days']; print(min(d))")
    echo "first approved date: $D"
    python3 tools/word_reel.py switch
    python3 tools/word_reel.py status --date $D
    python3 tools/word_reel.py media --date $D > /tmp/media.json; head -c 300 /tmp/media.json; echo
    python3 tools/word_reel.py caption-check --date $D
    for u in $(python3 -c "import json; m=json.load(open('/tmp/media.json')); print(m['video_url'], m['cover_url'])"); do echo "$u $(curl -s -o /dev/null -w '%{http_code} %{content_type} %{size_download}' $u)"; done
    python3 -c "import sys; sys.path.insert(0,'tools'); import verses, json; d=json.load(open('word/schedule.json'))['days']; led=verses.from_repo(); print('ledger holds', sum(1 for k,v in d.items() if led.rest([v['ref']], k) == 0), 'of', len(d), 'approved days')"
    python3 tools/check_fresh.py --weeks 8 --from $D | tail -4

Then load the PostHog tools with ToolSearch and run this one query through the PostHog connector's SQL tool (HogQL), exactly as written, reporting only the two numbers:

    SELECT properties.platform AS platform, count(DISTINCT distinct_id) AS readers
    FROM events
    WHERE event = 'today_verse_cards_shown'
      AND properties.environment = 'production'
      AND timestamp > now() - INTERVAL 30 DAY
    GROUP BY platform

Do not run `switch` with those numbers: this run writes nothing.

Reply in one short paragraph: the Python version, the commit, the Chicago date and hour, the first approved date, what switch, status, media and caption-check printed, both URLs' HTTP code, content type and size, the ledger line, the freshness verdict, the iPhone and Android reader counts from PostHog (or why the query could not run), and anything that would stop the live routine from posting.
