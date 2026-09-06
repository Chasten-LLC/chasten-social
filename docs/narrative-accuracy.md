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
3. **Respect what the text actually says.** Exodus 14:21 says the wind blew *all
   that night*, so the crossing is at night and not at dawn. Jonah 1:17 says a
   *great fish*, so captions and notes say great fish even when the footage shows
   a whale.
4. **No people, ever.** The reel places the viewer at the setting; it does not
   act the story out. The creature, the element, the place. This is Ric's
   direction, and it is also what the models are good at.
5. **Do not depict Jesus identifiably.** The fourth figure in the furnace stays an
   anonymous silhouette rather than a rendered Christ.
6. **Review every new narrative set before it runs.** Thematic sets are safe to add
   freely. Narrative ones assert something visual and need a read first.

## Labelling

No Reel depicts a person, so the earlier advice to label narrative Reels no longer
applies. Meta's reach penalty targets accounts built on a synthetic person, which
this is not. Whether to label at all stays Ric's call.

## 7. Guard against anachronism

The first furnace render produced four silhouettes in fur lined parkas. The
silhouette rule worked, the period did not. Any scene containing figures must
state the era and the dress explicitly, and "modern clothing, jacket, coat,
hoodie, jeans, contemporary dress, modern buildings" is now in the negative
prompt for every narrative scene.

Anachronism is the characteristic failure of biblical scene generation. It does
not look like a stylistic choice, it looks like a mistake, and on scripture
content that costs more than a plain background would have.

## 8. The setting, not the scene

Ric, 2026-09-06: "I don't ever want you depicting actual scenes. Approach it as
something relative. Daniel and the lion: footage of a lion, growling, where you
can see the beast that it is, and then the scripture is read with the growling in
the background, so it supplements the scripture versus acting it out. The fiery
furnace: a furnace full of flames, no people, but you hear the crackling. Jonah:
a whale swimming past with an underwater recording. Peter on the water: rough
water and a storm, nobody in it. Cinematic, so the audio and video supplement the
story and make the scripture captivating, like being at the setting, not
watching it play out."

So a narrative beat names a creature, an element or a place, never an event with
people in it. This replaced two earlier rules in one day. The first banned people
while still trying to depict the story's scene, and got men in parkas in a
burning corridor. The second let distant silhouettes in, and got a landslide for
Jericho and three horsemen charging a camera. Both were trying to make the
models act. They cannot, and they were never asked to again.

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

Subject fidelity is the weak criterion, and it does not work. Three rewrites of
that one rule produced three different failure modes on the same six images: "does
it show the scene at all" passed an olive leaf for a scene whose subject is a dove
carrying one; checking the description noun by noun failed a hillside at night for
a missing pillow stone; asking for the main subject went back to passing the dove
beat. The model also asserted that a mountain landslide "clearly shows a large wall
collapsing". This is not a wording problem.

So the rule is set to the version that produces no false positives. Everything it
now misses, it misses by letting an image through, never by killing a good one.
That is the cheap direction to be wrong in: a false positive deletes a viable story
and pays to regenerate it, while a false negative costs one person one minute.

That minute is `tools/reels/contact_sheet.py`, which lays all three beats of every
set on a single page. Subject fidelity is a human gate, and calling it anything
else would be pretending.
