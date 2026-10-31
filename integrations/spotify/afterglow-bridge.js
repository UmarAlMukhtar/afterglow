// Prepared locally with tools/prepare_spotify_bridge.py; never contains a Spotify token.
(async function afterglowBridge() {
  const localToken = "__AFTERGLOW_LOCAL_TOKEN__";
  const destination = "http://127.0.0.1:43827/v1/lyrics";
  for (let n = 0; !globalThis.Spicetify?.Player?.data || !Spicetify.CosmosAsync; n++) {
    if (n > 60) return;
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  let generation = 0;
  let cachedBody = null, cachedTrack = '';
  async function deliver(body) {
    const sent = await fetch(destination, {
      method: "POST", credentials: "omit", signal: AbortSignal.timeout(4000),
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${localToken}` }, body
    });
    if (!sent.ok) throw new Error("Local bridge rejected lyrics");
  }
  async function sendLyrics() {
    const request = ++generation;
    const uri = Spicetify.Player.data?.item?.uri || "";
    if (uri !== cachedTrack) { cachedBody = null; cachedTrack = uri; }
    const match = /^spotify:track:([A-Za-z0-9]{22})$/.exec(uri);
    if (!match) return;
    const trackId = match[1];
    try {
      // Cosmos attaches the session only to this fixed Spotify URL.
      const response = await Spicetify.CosmosAsync.get(
        `https://spclient.wg.spotify.com/color-lyrics/v2/track/${trackId}?format=json&vocalRemoval=false&market=from_token`
      );
      if (request !== generation || !response?.lyrics) return;
      const body = JSON.stringify({
        track_id: trackId,
        duration_ms: Number(Spicetify.Player.data?.item?.metadata?.duration || 0),
        lyrics: {
          syncType: response.lyrics.syncType,
          lines: (response.lyrics.lines || []).map(line => ({ startTimeMs: line.startTimeMs, words: line.words }))
        }
      });
      if (body.length > 2 * 1024 * 1024) return;
      cachedBody = body;
      // Use ordinary fetch for localhost: no Spotify cookies or headers are forwarded.
      await deliver(body);
    } catch {
      console.info("Afterglow: lyrics unavailable, or the local bridge is disabled. External sources remain available.");
    }
  }
  Spicetify.Player.addEventListener("songchange", sendLyrics);
  if (Spicetify.Topbar?.Button) new Spicetify.Topbar.Button("Send lyrics to Afterglow", "lyrics", sendLyrics);
  setInterval(async () => {
    if (cachedBody && Spicetify.Player.data?.item?.uri === cachedTrack) {
      try { await deliver(cachedBody); } catch { /* Afterglow may be closed. */ }
    }
  }, 8000);
  await sendLyrics();
})();
