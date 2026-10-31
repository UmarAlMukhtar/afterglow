# Afterglow Linux — first release design

Status: approved by the user on 2026-11-01.
Date: 2026-11-01

## Agreed intent

The user wants to enjoy music on their own Linux machine with both Verci-style
animated lyrics and Lumn-style audio-reactive screen-edge lighting. They asked
for an existing open-source alternative first, and a new open-source repository
when no close combined alternative was found. They selected both effects and
approved the proposed native Linux companion design in chat.

Success means the app runs on the user's Fedora 44 / bspwm / X11 desktop,
responds to system-output audio, follows a compatible music player, and can be
tried immediately. The initial deliverable is an MIT-licensed public GitHub
repository with source, installation/run instructions, focused tests and an
honest compatibility section. No proprietary assets or implementations are copied.

## Research and chosen approach

- [Lyra](https://github.com/eisewilliam/project-lyra) offers Linux MPRIS lyrics and
  karaoke surfaces, but does not advertise the requested reactive edge lighting.
  Its player-support document describes Linux integration as not yet run on Linux.
- [Cadence](https://github.com/MowkE/cadence) offers a Linux lyric/visualizer overlay.
  Its README also describes repeated Google sign-in prompts and invite-gated
  features. It does not document the requested combined screen-edge experience.
- [Vela](https://github.com/sayginsaman/Vela) combines both effects, but targets macOS.
- [GLava](https://github.com/jarcode-foss/glava) supplies X11 audio visualization,
  but requires a separate lyrics experience.

The search did not establish that no other implementation exists. These are the
closest inspected alternatives. A small independent native app avoids adopting
an unrelated application's social system or relying on macOS-specific code.

Use Python 3, GTK3/PyGObject, Pango, Cairo and the session D-Bus. These libraries,
an X11 compositor (picom), and PulseAudio-compatible tools are already installed
on the target machine. No new Python package dependency is required for v1.

The visual contract is [DESIGN.md](../../../DESIGN.md).

## Music providers and login

Afterglow is a companion to existing players, not a streaming client. Provider
buttons open the official Spotify, YouTube Music, Apple Music or SoundCloud
web player using the system browser. The user signs in there. Afterglow discovers
players through [MPRIS](https://specifications.freedesktop.org/mpris/latest/),
reads track metadata/position and sends supported transport commands.

Spotify Desktop, browser players and local MPRIS players are intended sources.
Compatibility depends on the player's metadata, position reporting and capabilities;
the UI must show the actual detected player and unsupported controls. Provider
buttons are launch shortcuts, not claims of dedicated service integrations.

Auto mode prefers a playing player and avoids needless switching. A player selector
allows an explicit choice. Preserve selection while it exists, handle closing or
restarting players, and resynchronize on pause, seek and track change. Do not act
on another player after a stale command. Respect MPRIS capability flags.

No Spotify developer app, Premium requirement imposed by Afterglow, OAuth backend,
password storage, paid lyrics key or provider-specific streaming API is part of v1.
Service subscription and playback restrictions still belong to the chosen player.

## Lyrics and timing

Priority: a user-imported LRC/enhanced LRC override, cached lyrics, true word-timed
TTML from the community AMLL database when a Spotify track ID matches, then
LRCLIB lookup using title/artist/album/duration. Use fixed, documented HTTPS
endpoints and identify the application in its requests.

TTML and enhanced LRC retain supplied word timestamps. Standard LRC is line-timed:
estimate individual word durations conservatively from word lengths within the
line's interval and label the result "Estimated word timing". Plain text is
explicitly unsynced, with line display; do not invent a synchronized position.

AMLL word-level lookup is limited to identifiable Spotify IDs in v1. Other sources
can still use true timing through enhanced LRC import, or use the LRCLIB fallback.
Coverage is never guaranteed. Missing lyrics retain track information and light,
and offer retry/import instead of an endless loading spinner.

A manual offset handles lyric-file errors and Bluetooth/output latency. Track
position extrapolates from a monotonic timestamp only while playing, with regular
correction from MPRIS. Async responses from an old track cannot replace current
lyrics/artwork. Cache by stable track identity and relevant metadata; imported
overrides take precedence. Keep caches bounded and separate from source code.

## Audio and colors

Read PCM from the current output sink's monitor through `parec`, specifying the
monitor explicitly. Never fall back to the microphone. Audio stays in memory and
is neither recorded to disk nor uploaded.

Compute smoothed amplitude and low-frequency energy using standard-library DSP
sufficient for a responsive glow. Describe this as audio-reactive lighting rather
than claiming sample-perfect beat transcription. Cap brightness/intensity and
smooth peaks. Reconnect with bounded backoff if the stream stops and follow output
changes, including Bluetooth routing. Show unavailable/reconnecting state when
capture fails; the rest of the app remains usable.

Extract a small two-color palette from downsampled album artwork. Download/decode
off the GTK thread, enforce time and byte limits, accept only supported image
inputs, and fall back to the default mint/amber palette when unavailable. Permit
a manual palette override. Album artwork is requested from the player-provided
location; local file artwork remains local.

## Windows and user controls

- A normal GTK control window owns the lifecycle and stays keyboard-accessible.
- A transparent always-above, click-through X11 surface draws the edge glow and
  optional lyric overlay without taking mouse input from underlying applications.
- A fullscreen stage draws the same visual state on a dark background. Escape
  leaves fullscreen. Quitting closes every overlay and capture subprocess.
- Controls: player selection; official service launch buttons; previous/play-pause/
  next; desktop/fullscreen/off; separate light and lyric toggles; word/line style;
  intensity, glow width, lyric size, timing offset, palette and Reduce Motion;
  monitor selection; LRC import; demo; quit.
- Store user preferences atomically in the normal XDG config directory; handle
  invalid files by safe defaults without overwriting a recoverable corrupt file.

Do not change bspwm or picom configuration, install global shortcuts or autostart
on the user's behalf. Supply an optional desktop launcher and clear manual run
instructions. First-run UI explains that music plays in its existing player.

## Error handling, privacy and bounds

Keep network and audio work off the GTK main loop. Limit worker/subprocess counts,
cancel/ignore stale work and close resources on exit. Use subprocess argument lists,
never shell commands constructed from song metadata. Bound network responses,
request durations, imported file size and parsed event counts. Reject XML document
types/entities; handle malformed and out-of-order lyric timestamps safely.

Lyrics requests share track metadata with the selected lyric service; artwork
requests contact the artwork host. Explain this plainly in README and settings.
No analytics, telemetry, cloud account, audio upload or credential storage. No
automatic update executor. Preserve third-party attribution and do not bundle
copyrighted songs or their lyrics as demo content.

## Demonstration and verification

Demo uses short original fixture lyrics and a deterministic playback clock/audio
envelope. It visibly identifies itself as a demo. Its purpose is to verify visuals,
timing, controls and cleanup without needing an account or real song data.

Focused automated checks cover LRC/TTML parsing and malformed input, truthful
timing quality, timeline boundaries and seek/pause, palette/audio smoothing,
settings persistence and invalid configuration. Use a mock MPRIS service to verify
metadata, capabilities, commands, track changes and disconnect/reconnect without
altering the user's real playback.

On the actual desktop, verify launching, desktop input transparency, fullscreen
and Escape, monitor geometry, capture from output rather than microphone, output
routing recovery, pause behavior and process cleanup. Render and inspect screenshots
using demo lyrics. When a real music player is available, verify metadata, lyric
lookup, controls and visible audio reaction, explicitly distinguishing tested
behavior from upstream/service assumptions. Do not claim provider logins or
Bluetooth timing were verified without actually checking them.

## Release boundaries

First-class target: the user's Fedora/bspwm/X11/PipeWire session. Document Fedora
runtime packages and source launch. Other X11 desktops are best effort until
tested. Wayland layer-shell support, secure lock-screen integration, embedded
streaming/search/library management, remote Spotify Connect devices, automatic
speech alignment, social features and multi-monitor simultaneous rendering are
outside this release. They do not block the requested local experience.

Publish only source, original fixtures and documentation. Exclude local settings,
cached lyrics/artwork, credentials, temporary captures and test-environment data.

## User-approved follow-up scope — 2026-11-01

The user replaced the approximate word stack with a request to recreate Verci's
lyric presentation and selected all four named styles. Follow the revision in
DESIGN.md: oversized perspective type, filled active-word highlights, word symbols,
and a real OpenGL convex mesh for the two fisheye variants. This supersedes the
original small word-stack visual treatment. Other v1 platform boundaries remain.

The user also authorized adding a user-installed Spotify copy with Spicetify and
the prepared optional lyric bridge, because the existing system Flatpak is
read-only. Keep that system copy in place; a Spotify restart is authorized.
The bridge runs inside the user's Spotify session and calls its undocumented lyric
endpoint. It sends only lyric fields, track ID and duration to an authenticated
loopback receiver; no Spotify credential is exported. A private local connection
token is stored in XDG config. This is optional and disabled by default for other
users. Clearly describe private-endpoint availability and the distinction between
Spotify line timing and actual word timing. Received bridge lyrics stay in memory;
imported lyrics and genuine word-timed sources retain priority.
