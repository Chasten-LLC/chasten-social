# Accuracy rules for narrative Reels

A narrative Reel makes visual claims the verse does not. Every scene must be
checkable against the passage it illustrates, because this is a Bible app and a
wrong detail is the kind of thing an attentive reader notices immediately.

## Rules

1. **Verse text comes from the BSB data in chasten-web.** Never paraphrased, never
   from memory, never from a different translation. If a public API cannot serve
   BSB, take it from the app's own files.
2. **Do not mix accounts.** The scene illustrates the verse on screen and nothing
   else. Folded linen belongs to John 20, so it cannot appear beside Matthew 28.
3. **Respect what the text actually says.** Daniel 3:25 says the four were
   *walking* in the fire, so they are not standing. Exodus 14:21 says the wind blew
   *all that night*, so the crossing is at night and not at dawn.
4. **No faces, ever.** Silhouettes, distance, or backs. This is partly reverence and
   partly that faces are the one thing image models reliably fail at. Figures
   themselves are welcome; a legible face is not.
5. **Do not depict Jesus identifiably.** The fourth figure in the furnace stays an
   anonymous silhouette rather than a rendered Christ.
6. **Review every new narrative set before it runs.** Thematic sets are safe to add
   freely. Narrative ones assert something visual and need a read first.

## Labelling

Narrative Reels depict people and should carry Instagram's AI label. Scenery-only
Reels contain no people and do not. The metadata field `narrative` says which is
which, and the email states it.

## 7. Guard against anachronism

The first furnace render produced four silhouettes in fur lined parkas. The
silhouette rule worked, the period did not. Any scene containing figures must
state the era and the dress explicitly, and "modern clothing, jacket, coat,
hoodie, jeans, contemporary dress, modern buildings" is now in the negative
prompt for every narrative scene.

Anachronism is the characteristic failure of biblical scene generation. It does
not look like a stylistic choice, it looks like a mistake, and on scripture
content that costs more than a plain background would have.

## 8. People belong in these scenes, faces do not

This rule used to read "nothing living on screen", and it was wrong. It came from
one bad render, the men in parkas in the furnace, and generalised a costume
failure into a ban on human presence.

The ban then rejected all twenty three narrative sets, including a dust road
running to a walled city with two robed silhouettes on it, which was the best
image of the sweep. Ordering the model to remove people it insists on drawing
also made the images worse, not emptier.

So the prompt now directs instead of forbidding: any people are small, far away,
seen from behind or in silhouette, faces never visible. Distance carries the
reverence the ban was reaching for, and it is something the model will actually
do.

Scenery Reels stay empty. That is a different format with a different look, not a
safety rule.

## 9. Look at the still before paying to animate

A still costs about four cents and a clip about a dollar sixty five. The furnace
failure animated three bad stills before anyone looked at them, wasting roughly
five dollars to produce something unusable. Generate the stills, look at them,
and only animate what passes.

## 10. The build audits itself

Every still is checked by a vision model before anything is animated. It fails an
image for one of five specific defects: a legible human face, visible anatomical
distortion, anything modern, a named subject that is missing from the frame, or a
key object at an absurd scale.

A failed beat is regenerated with a stronger instruction, up to four rolls, each
pushing the figures further away. If the beat still fails, the set is dropped and
the build moves to the next story.

Two lessons are worth keeping. A rubric with a catch-all clause, in this case
"looks like a mistake", will eventually justify rejecting anything, so every
criterion names a defect. And the judge matters as much as the rubric: on six
stills with a verdict set by looking at them, gpt-4o-mini scored two out of five
and called a face legible on backs of heads, while gpt-4.1-mini scored four.

Subject fidelity is the weak criterion. The first version asked whether the image
showed the requested scene "at all", which passed an olive leaf on driftwood for a
scene whose subject was a dove carrying it, and a landslide in a ravine for the
walls of Jericho. It now names the test: the specific things the scene calls for
must be present and recognisable.

Even so, this is the criterion a model is worst at, so every narrative set gets a
human read before it goes live. `tools/reels/contact_sheet.py` lays all three
beats of every set on one page for exactly that.
