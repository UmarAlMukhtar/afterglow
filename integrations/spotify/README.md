# Optional Spotify lyrics bridge

This extension runs **inside Spotify Desktop through Spicetify**. It asks Spotify's
own client for the current song's lyric data, then sends only track ID, duration,
lyric text and lyric timestamps to Afterglow on `127.0.0.1:43827`.

The Spotify request uses Spicetify's Cosmos wrapper against a fixed Spotify URL.
The local request uses ordinary `fetch` with `credentials: omit`. Spotify cookies,
access tokens and account headers are never sent to Afterglow. A separate random
local connection token protects the loopback receiver.

This uses an **undocumented Spotify lyrics endpoint**, as Spicetify's own Lyrics
Plus provider does. Spotify updates, account restrictions or unavailable lyrics
can break it. It is optional, not an official Spotify integration. Line-synced
Spotify lyrics still require estimated word timing; this does not magically make
them true per-word lyrics.

## Setup

1. Install and configure [Spicetify](https://spicetify.app/docs/getting-started/).
   Follow its platform instructions for your Spotify package. A system-wide Flatpak
   may have read-only application files. This project does not automatically change
   their permissions, replace your Spotify installation, or patch the client.
2. Prepare the private extension from the Afterglow checkout:

   ```bash
   python3 tools/prepare_spotify_bridge.py
   ```

   This prints the prepared file's location, normally
   `~/.config/afterglow-linux/afterglow-bridge.local.js`.
3. Run `spicetify -c` to find its config file. Copy the prepared JS file into the
   `Extensions` directory beside that config file, preserving its private mode.
4. Enable and apply the extension:

   ```bash
   spicetify config extensions afterglow-bridge.local.js
   spicetify apply
   ```

5. In Afterglow, enable **Use Spotify lyric bridge**. Restart Spotify if needed,
   play a song, or press its **Send lyrics to Afterglow** top-bar button.

Imported LRC and true word-timed sources retain priority over line-only bridge
lyrics. If the bridge is unavailable, external lyric lookups remain in place.

## Local connection data

The local token lives in Afterglow's private XDG config directory. The prepared JS
file embeds that local token so it can authenticate. **Do not publish that prepared
file**; the public template contains only a placeholder. The receiver binds only
loopback, enforces origin/authentication and body-size checks, and is disabled by
default. Switch it off to stop listening. Received lyric documents stay in memory.

Removing the extension from Spicetify configuration and applying again removes the
client-side bridge. The preparer itself only writes the private extension file.
