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
   partly that faces are the one thing image models reliably fail at.
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

## 8. Nothing living on screen

Every image that has worked has been a landscape or a natural phenomenon with
nothing alive in it. Every failure has had figures: four men in a furnace read as
four men in a burning corridor, and the crayon attempts were worse.

This is not a prompting problem. It is what the model is good at. So narrative
scenes show the place and never the people. The verse already says what happened,
and a viewer supplies the rest more vividly than a render can.

If a story cannot be told by its setting alone, it is not a candidate. Walking on
water and the feeding of the five thousand both need a figure to mean anything,
so neither belongs in this library.

## 9. Look at the still before paying to animate

A still costs about four cents and a clip about a dollar sixty five. The furnace
failure animated three bad stills before anyone looked at them, wasting roughly
five dollars to produce something unusable. Generate the stills, look at them,
and only animate what passes.

## 10. The build audits itself

Every still is checked by a vision model before anything is animated. It fails an
image that does not show the requested subject, that contains any person, face or
animal, that shows anything modern, or that simply looks like a mistake.

A failed beat is regenerated once with a stronger instruction. If it fails again
the whole set is dropped and the build moves to the next story in the rotation.
Nothing reaches a clip without passing.

This exists because the furnace kept hallucinating people into a scene whose
prompt said "no people" three times. Prompting alone does not hold. The audit
costs a fraction of a cent and a clip costs about a dollar sixty five.
