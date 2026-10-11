# Audio library

Instrumental beds for Reels, and the Sunday dove's sound.

## The Sunday dove (made for Chasten, 2026-10-08)

- `dove-harp.mp3`: ElevenLabs music (`music_v2_5`, instrumental), harp arpeggios and celesta
  over strings and organ. The first note is at 0.19 s.
- `dove-wings.mp3`: ElevenLabs sound effect, a dove's steady wingbeats (looped under the flight).
- `dove-landing.mp3`: ElevenLabs sound effect, a soft flutter as the dove lands.

`tools/formats/dove_sound.py` mixes them under every Sunday dove. All three were generated on
Chasten's paid ElevenLabs plan: Eleven Music's terms allow commercial online use with no
attribution, and ElevenLabs states that with a paid account its sound effects may be used
royalty-free "in commercial projects, including YouTube videos, social media content, and
even advertising" (elevenlabs.io/sound-effects, read 2026-10-08). Boosting is covered.

Audio does reach Instagram inside the video slides of a carousel: each slide keeps its own
sound (checked 2026-10-11, Instagram serves an audio track for every slide of
https://www.instagram.com/p/DeQAk7rideZ/). Image slides cannot carry audio.

## Why not image carousels

Instagram's in-app "Add music" picks from Instagram's own licensed catalogue. There
is no upload path for your own audio file on a feed post, and the Graph API exposes
no music parameter for images or carousels at all. An MP3 can only reach Instagram
by being mixed into a video, which means a Reel.

So for the daily carousel, the audio suggestion in the morning email stays the right
mechanism: it names a song to search for inside Instagram's library. These files are
groundwork for the day the Reel format gets built.

## Licensing

Every track here follows Pixabay's naming pattern `artist-title-id.mp3`, so it is
presumed to come from https://pixabay.com/music/ under the Pixabay Content License:
commercial use allowed, no attribution required, no fee.

**That provenance is inferred from the filename, not verified.** Before any of these
is published, confirm each one really came from Pixabay. If a track came from
somewhere else, its licence is probably different.

Two traps worth remembering when adding more:

1. A public domain hymn is not a public domain recording. "Be Thou My Vision" is
   public domain as a composition, but any particular recording of it is separately
   copyrighted. Use a Pixabay track, a public domain recording from
   https://musopen.org, or one you commission.
2. Instagram fingerprints audio. Even correctly licensed royalty free music is
   occasionally false flagged and muted, more so for heavily used tracks. If a Reel
   ever publishes silent, that is the likely cause.

## Coverage

`tracks.json` maps each file to the theme keys used by `settings.audio.byTheme`, so
one lookup serves both the email suggestion and a future Reel.

Gaps worth filling:

- **`love, grace, mercy, forgiveness, gospel, salvation` has no track.** It is one of
  the most common themes in the verse sets, so this is the first one to add.
- `prayer, faith, presence` only has an 8 second piece, which has to loop to cover a
  15 second Reel. A longer alternative would be better.
- Two files are flagged `fit: off-brand` and left unassigned: `old skool piano` and
  `dark street groove`. Neither suits a reverent verse post. They are kept rather than
  deleted in case they are wanted elsewhere, but nothing will select them.

## Adding a track

Drop the MP3 in this folder, then add an entry to `tracks.json` with its `file`,
`artist`, `title`, `seconds`, `themes` (matching `settings.audio.byTheme` keys),
`fit`, `source` and `license`. Prefer pieces of at least 20 seconds so a Reel does
not need to loop.
