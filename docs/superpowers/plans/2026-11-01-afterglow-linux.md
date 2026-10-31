# Afterglow Linux Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Deliver and locally demonstrate an open-source X11 music companion with synced lyrics and output-audio-reactive edge lighting.

**Architecture:** A small Python package connects to MPRIS and the output monitor in bounded background workers. GTK renders a shared playback/lyrics/audio state into a control window, transparent overlay and fullscreen stage. Pure timing/parsing code remains independently testable.

**Tech Stack:** System Python 3, GTK3/PyGObject, Cairo, Pango, dbus-python, `parec`, `pactl`, Python standard library, unittest; no pip dependency installation.

**Spec:** [Approved release spec](../specs/2026-11-01-afterglow-linux-design.md) and [locked DESIGN.md](../../../DESIGN.md).

## Global Constraints

- First-class target: the user's Fedora/bspwm/X11/PipeWire session.
- Audio stays in memory and is neither recorded to disk nor uploaded.
- Never fall back to the microphone.
- Standard LRC is line-timed; label estimated word timing explicitly.
- No Spotify developer app, OAuth backend, password storage or provider-specific streaming API.
- No proprietary assets, bundled copyrighted song lyrics, unrequested autostart or compositor edits.
- Network/audio work stays off the GTK main loop; subprocesses close on exit.
- Target 30fps while active; respect Reduce Motion and pause.
- Publish source, original fixtures and documentation, excluding user caches/settings.

## Review Focus

- A slow lookup for an old track must not overwrite the current song (Task 2).
- A browser can omit duration, artist, seek support or position; show usable honest states (Task 3).
- Bluetooth/output changes must reconnect to an output monitor, never an input (Task 4).
- Long/RTL lyrics and malformed lyric files must remain bounded and readable (Tasks 1 and 5).
- Closing any visual surface must leave a route back to controls; quitting must remove overlays and workers (Tasks 5 and 6).

## File structure and interfaces

- `afterglow/__init__.py`, `afterglow/__main__.py`: package version and launch entry.
- `afterglow/lyrics.py`: lyric models, bounded LRC/TTML parsing, timeline lookup.
- `afterglow/storage.py`: XDG paths, preferences, bounded HTTPS fetches, caches, lyric resolver and artwork palette.
- `afterglow/media.py`: playback snapshot model, active-player choice and MPRIS worker.
- `afterglow/audio.py`: output-monitor reader and smoothed energy model.
- `afterglow/visuals.py`: Cairo/Pango stage and click-through/fullscreen surfaces.
- `afterglow/app.py`: GTK controls, state coordination, demo and lifecycle.
- `tests/test_lyrics.py`, `tests/test_storage.py`, `tests/test_media.py`, `tests/test_audio.py`: focused unittest checks.
- `tests/mpris_fixture.py`: private-session fake player used for integration verification.
- `README.md`, `LICENSE`, `.gitignore`, `afterglow.desktop`: running, licensing and optional launcher.

### Task 1: Lyric documents and trustworthy timing

**Files:** Create package metadata/entry stub, `lyrics.py`, `tests/test_lyrics.py`.

**Interfaces:** Produce immutable `Word(text, start, end)`, `Line(text, start, end, words)` and `LyricDocument(lines, quality, source)` dataclasses; `parse_lrc(text: str, duration: float = 0) -> LyricDocument`; `parse_ttml(text: str) -> LyricDocument`; `locate(document: LyricDocument, position: float) -> tuple[int, int, float]`. Quality values: `word`, `estimated`, `unsynced`, `instrumental`, `missing`.

- [x] Write tests asserting: `[00:01.00]Hello world` starts at 1 second and is `estimated`; enhanced LRC `<00:01.00>Hello <00:02.00>world` retains exact starts and is `word`; a gap has no falsely active word; plain lyrics are `unsynced`; empty input is `missing`.
- [x] Add TTML tests for word spans, syllables, whitespace and malformed/entity-containing XML; add LRC tests for offsets, duplicate timestamps, nonfinite values, long input and Unicode/RTL text.
- [x] Run `python3 -m unittest discover -s tests -p test_lyrics.py -v`; confirm failure before implementation.
- [x] Implement the models/parsers and binary-search timeline, with bounded input/event counts, safe timestamp ordering and explicit errors on oversized/unsafe documents.
- [x] Run the same command; require all tests to pass.
- [x] Commit the lyric core and its tests.

### Task 2: Persistent settings and asynchronous content resolution

**Files:** Create `storage.py`, `tests/test_storage.py`, `.gitignore`.

**Interfaces:** Consume Task 1. Produce `load_settings() -> dict`, `save_settings(settings: dict) -> None`, `fetch_bytes(url: str, limit: int) -> bytes`, `resolve_lyrics(track: dict, override: str | None = None) -> LyricDocument`, `load_artwork(url: str) -> tuple[object | None, tuple[str, str]]`; a small `LatestRequest` generation guard with `next() -> int` and `is_current(generation: int) -> bool` prevents stale UI commits.

- [x] Write tests asserting temporary XDG directories work, settings round-trip atomically, invalid settings preserve the original file, and unsafe/oversized responses fail without partial cache writes.
- [x] Add mocked lyric-provider tests: imported override wins; cache hit avoids network; valid Spotify-ID TTML wins over LRCLIB; provider miss falls through; missing and instrumental results differ; a newer request makes the old generation stale.
- [x] Run `python3 -m unittest discover -s tests -p test_storage.py -v`; confirm failure before implementation.
- [x] Implement fixed lyric endpoints, bounded HTTPS retrieval, timeouts, metadata normalization, bounded caches and artwork downsampling/palette extraction outside GTK callbacks. Validate saved settings types/ranges. Persist no secrets or audio.
- [x] Run the same command; require all tests to pass.
- [x] Commit persistence/resolution and tests.

### Task 3: Music-source discovery and transport

**Files:** Create `media.py`, `tests/test_media.py`, `tests/mpris_fixture.py`.

**Interfaces:** Produce `Playback` dataclass containing player bus name/identity, title/artist/album, duration/position/sample monotonic timestamp, playing status, track/artwork URLs and capability flags; `Playback.at(now: float) -> float`; `choose_player(players: list[Playback], preferred: str, previous: str) -> Playback | None`; `MediaWorker(on_update)` with `start()`, `select(bus_name: str)`, `command(action: str)`, `stop()`.

- [x] Write tests for stable active-player selection, explicit selection, disconnect, pause/seek extrapolation and incomplete browser metadata. Assert disabled transport capabilities are never sent to the player.
- [x] Run `python3 -m unittest discover -s tests -p test_media.py -v`; confirm failure before implementation.
- [x] Implement bounded MPRIS D-Bus polling and a command queue in one worker, identifying the intended bus name on commands and handling timeouts/player disappearance. Dispatch immutable snapshots to the GTK coordinator.
- [x] Implement a configurable fake MPRIS player on a private `dbus-run-session`, with track change, seek, capability and disconnect hooks. Its fixture uses original lyric/track data.
- [x] Run media tests and a private-bus discovery/control/reconnect smoke check; require observed snapshots and supported commands to match expectations.
- [x] Commit media integration and fixtures.

### Task 4: Output-audio reaction and routing recovery

**Files:** Create `audio.py`, `tests/test_audio.py`.

**Interfaces:** Produce `Envelope.update(pcm: bytes, rate: int) -> tuple[float, float]` for smoothed total/bass energy; `output_monitor() -> str`; `AudioWorker(on_update)` with `start()` and `stop()`. Callback supplies normalized energy and readable capture status; it never supplies/stores PCM outside the worker.

- [x] Write generated-PCM tests for silence, tone/pulse response, bounded peaks and release decay. Mock `pactl` responses to assert only a verified default sink monitor is selected and a missing monitor is reported as unavailable.
- [x] Add subprocess/routing tests proving sink changes or capture termination close the old reader and trigger bounded retry; `stop()` must stop the reader and worker.
- [x] Run `python3 -m unittest discover -s tests -p test_audio.py -v`; confirm failure before implementation.
- [x] Implement standard-library RMS/low-pass energy and attack/release smoothing; start `parec` with explicit monitor and PCM format, follow default sink changes, and use timeout/select-based reads and bounded reconnect backoff.
- [x] Run audio tests and an actual output-monitor capture probe; record source name and capture status without recording audio to disk or changing system routing.
- [x] Commit capture and tests.

### Task 5: Native controls and both visual surfaces

**Files:** Create `visuals.py`, `app.py`; finish `__main__.py`; add `afterglow.desktop` and original in-code demo fixtures.

**Interfaces:** Consume Tasks 1–4. Produce `Stage(Gtk.DrawingArea)` drawing the current playback/document/energy/settings state; `VisualWindow` for transparent desktop or dark fullscreen; `AfterglowApp(Gtk.Application)` owning workers, UI, async generations, demo and shutdown. Run via `python3 -m afterglow` with optional `--demo`.

- [x] Add a GTK/Xvfb smoke check asserting the demo advances, pause freezes its clock, offset changes lyric position, and shutdown leaves no workers/overlay windows.
- [x] Run it before implementation and record the expected missing-app failure.
- [x] Implement the locked DESIGN.md colors/type/spacing, readable Pango lyrics, smooth edge glow, word-stack/line views, monitor selection and X11 click-through overlay. Cap redraw rate and reduce idle work; maintain a usable control window on visual-window close.
- [x] Add all approved controls: provider launch shortcuts, source selector, supported transport actions, desktop/fullscreen/off, separate effects, style, intensity/width/size/offset, palette, Reduce Motion, monitor, lyric import, demo and quit. Show honest connection/capture/timing states.
- [x] Run the smoke check and the complete unittest suite. Inspect rendered 1920×1200 demo screenshots and smaller control-window layout, including long/RTL lyrics. Confirm keyboard navigation and Escape behavior.
- [x] Commit UI and integration.

### Task 6: Local trial, review and open-source publication

**Files:** Create `README.md`, MIT `LICENSE`; finish optional launcher and `.gitignore`; update plan checkboxes as work finishes.

- [ ] Write Fedora runtime-package instructions, source-run command, provider connection steps, privacy/data locations, architecture, tests, screenshots, troubleshooting and tested compatibility limits. Make launcher installation optional, with paths resolved from the actual checkout.
- [ ] Run `python3 -m unittest discover -s tests -v`, Python compilation and `git diff --check`; require passing output. Complete private-bus end-to-end checks.
- [ ] Launch the app on the user's desktop. Verify overlay input passes through, fullscreen/Escape works, monitor geometry is correct, audio comes from the output monitor and quitting cleans up. Test live track metadata/lyrics/controls when a real source is available; clearly report any unavailable provider/Bluetooth checks.
- [ ] Review the full implementation against the approved spec, resolve actionable failures, and rerun only affected checks. A fresh review may be used if authorized by the selected execution workflow.
- [ ] Check staged/tracked paths for credentials, caches and non-original fixtures. Commit the release source/docs, then create the requested public `UmarAlMukhtar/afterglow-linux` repository (use an available equivalent name if taken) and push the reviewed source.
- [ ] Leave the local demo open for the user to try, and deliver the repository URL, run command, observed checks and remaining limitations.

## Approved follow-up implementation

- [x] Four reference lyric styles, actual GPU lens, original symbol mapping and native style captures.
- [x] Optional authenticated Spotify lyric bridge; user-installed Spotify copy and official Spicetify release applied with user approval.
- [x] True black, inertial rise and independent sideways motion; Reduce Motion remains off.
- [x] Both reviews addressed with failing regressions followed by passing checks.
