# Design Spec — Afterglow Linux

Status: locked; the user approved this written specification on 2026-11-01.

## Purpose and references

A personal Linux music companion combining animated lyrics inspired by
[Verci](https://www.verci.xyz/) with music-reactive screen-edge light inspired
by [Lumn](https://www.trylumn.xyz/). The primary action is to start music in an
existing player, then enable Afterglow's light and lyrics.

Design DNA: a quiet dark canvas; one strong lyric focus; album-derived light;
generous spacing; smooth motion. Build original assets and code. References
guide the experience, rather than supplying proprietary code or branding.

## Colors

| Token | Value | Usage |
|---|---|---|
| bg-primary | #101413 | Main window and fullscreen stage |
| bg-surface | #1B2421 | Controls and settings |
| text-primary | #F3F5EE | Current lyric and headings |
| text-secondary | #A9B7AE | Nearby lyrics and secondary text |
| accent | #A9E5C2 | Default highlight and focus |
| accent-warm | #EBAE84 | Default secondary light |
| border | #35473D | Subtle separators and control borders |
| error | #F2A29A | Actionable error text |

Album colors replace the light accents when artwork is available. Text retains
readable contrast. Color never acts as the only status indicator.

## Typography

Use the installed system sans-serif family, resolved through Pango. No font download.

- Display: bold / 64px at a 1920px stage, scaled and fitted to available space.
- Heading: bold / 24px.
- Body: regular / 15px.
- Caption: regular / 12px.
- Line heights: 1.15 for focused lyrics, 1.4 for body text.
- Render multilingual lyrics through Pango shaping, including long and RTL text.

## Spacing

Base unit: 4px. Scale: 4, 8, 12, 16, 24, 32, 48, 64px.

## Radius

Small: 6px. Medium: 12px. Large: 18px. Fullscreen lighting follows the display
rectangle; no camera-notch imitation.

## Elevation

Use flat controls and restrained borders. Soft bloom belongs to the screen-edge
lighting, not every control. Desktop overlays use real transparency.

## Icons

Use existing symbolic GTK icons with visible text or accessible names. No icon font.

## Layout

- Main window: one column, approximately 520px wide; responsive minimum 380px.
- Order: connection/source, track information, playback controls, visual modes,
  appearance/timing controls, status.
- Stage: centered lyric stack with current word emphasized and adjacent words
  receding through scale and opacity. A line mode is also available.
- Desktop mode: separate click-through lighting and lyric surfaces; controls stay
  in the main window. Overlay geometry follows the selected monitor.
- Fullscreen mode: dark background, lyrics and light, unobtrusive track context;
  Escape returns to the main controls.
- One monitor selected at a time in the first release; all attached monitors are
  selectable. Reposition safely when a display disappears.

## Motion

Target 30fps while active. Smooth attack/release for audio-reactive brightness and
thickness; 160–240ms lyric transitions. Reduce Motion removes spatial lyric
transitions and fast light travel. Pause substantially reduces redraws. Sliders
control light intensity and lyric size; light and lyrics can be switched separately.

## Banned

- Strobing, hard flashes, unbounded brightness changes.
- Fake login forms, bundled provider secrets, credential collection.
- Claims that every provider or every song is supported.
- Presenting estimated word times as genuine per-word timings.
- Presenting fullscreen as a secure lock screen.
- Unrequested autostart, compositor edits, system-wide installation or telemetry.

Once the user confirms the written spec, this design is locked for the first
release. Any material design change requires another review.
