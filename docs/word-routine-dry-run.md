You are checking Chasten's daily word reel routine inside this cloud sandbox. This is a DRY RUN. Never publish anything, never push, never commit, never call Composio, Instagram, Slack, Gmail, PushNotification or any notification tool, and never use the Artifact tool. Never write em dashes. Never look for or print any key or token. Counts from PostHog only: never look up or print a person, an id or any other property.

The live routine's prompt is docs/word-routine-prompt.md. This run follows its steps on the branch named below, up to the point of posting, for the date given below, and reports what each step printed. The session starts in /home/user, which is not a repository: always use the paths below.

    R=/home/user/chasten-social; A=/home/user/chasten-bible-app; W=$R/.wordrun; D=__DATE__
    cd $R && git fetch -q origin __BRANCH__ && git checkout -q --detach FETCH_HEAD && git log --oneline -1
    python3 -c "from datetime import datetime; from zoneinfo import ZoneInfo; n=datetime.now(ZoneInfo('America/Chicago')); print(n.date(), n.hour)"
    python3 tools/word_reel.py status --date $D
    python3 tools/word_reel.py switch
    time (python3 -m venv /tmp/wv && /tmp/wv/bin/python -m pip install --quiet pillow numpy fonttools playwright) 2>&1 | tail -3; PY=/tmp/wv/bin/python; $PY -c "import PIL, playwright, fontTools; print('tools ok', PIL.__version__)"
    cd $A && git fetch -q origin release/next && git checkout -q --detach origin/release/next && git log --oneline -1; cd $R
    which google-chrome && google-chrome --version
    rm -rf $W && time $PY tools/word_render.py today --app $A --date $D --out $W
    ls -la $W
    mkdir -p word/$D && cp $W/reel.mp4 $W/cover.jpg $W/caption.txt $W/reel.json word/$D/
    python3 tools/word_reel.py media --date $D | head -c 400; echo
    $PY tools/word_render.py calendar --app $A --from $D --to 2027-02-28 --write
    python3 -c "import sys; sys.path.insert(0,'tools'); import verses, json; c=json.load(open('word/calendar.json')); led=verses.from_repo(); print('ledger holds', sum(1 for k,v in c.items() if led.rest([v], k) == 0), 'of', len(c), 'calendar days')"
    $PY tools/check_fresh.py --weeks 8 --from $D | tail -4
    git status --short | head

Give the render up to ten minutes. If a command fails, keep going with the next one.

Then Read $W/cover.jpg once and say whether every word on it is whole and readable, with nothing overlapping or cut off, and whether the Hebrew or Greek word drew as real letters.

Then load the PostHog tools with ToolSearch and run this one query through the PostHog connector's SQL tool (HogQL), exactly as written, reporting only the two numbers:

    SELECT properties.platform AS platform, count(DISTINCT distinct_id) AS readers
    FROM events
    WHERE event = 'today_verse_cards_shown'
      AND properties.environment = 'production'
      AND timestamp > now() - INTERVAL 30 DAY
    GROUP BY platform

Do not run `switch` with those numbers: this run writes nothing that leaves the sandbox.

Reply in one short paragraph: the commit, the Chicago date and hour, what status and switch printed, how long the setup took and the Pillow version, the app commit, the Chrome version, the render's last line and how long it took, the files and their sizes, what media printed, the calendar and ledger lines, the freshness verdict, what you saw on the cover, the iPhone and Android reader counts from PostHog (or why the query could not run), and every error message verbatim.
