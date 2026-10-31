const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

(async () => {
  let spotifyUrl, sent;
  const context = {
    console, AbortSignal,
    Spicetify: {
      Player: { data: { item: { uri: 'spotify:track:0123456789012345678901', metadata: { duration: '10000' } } }, addEventListener() {} },
      CosmosAsync: { async get(url) {
        spotifyUrl = url;
        return { sessionSecret: 'MUST_NOT_LEAVE_SPOTIFY', lyrics: { syncType: 'LINE_SYNCED', extra: 'not needed', lines: [{ startTimeMs: '1000', words: 'Original fixture', unused: 'not needed' }] } };
      } }
    },
    async fetch(url, options) { sent = { url, options }; return { ok: true }; }
  };
  await vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../integrations/spotify/afterglow-bridge.js'), 'utf8'), context);
  assert.equal(new URL(spotifyUrl).hostname, 'spclient.wg.spotify.com');
  assert.equal(sent.url, 'http://127.0.0.1:43827/v1/lyrics');
  assert.equal(sent.options.credentials, 'omit');
  assert.equal(sent.options.headers.Authorization, 'Bearer __AFTERGLOW_LOCAL_TOKEN__');
  assert.equal(sent.options.body.includes('MUST_NOT_LEAVE_SPOTIFY'), false);
  assert.equal(sent.options.body.includes('not needed'), false);
  assert.equal(JSON.parse(sent.options.body).lyrics.lines[0].words, 'Original fixture');
  console.log('Spotify extension confines session requests to Spotify and sends only lyric data to loopback: PASS');
})().catch(error => { console.error(error); process.exitCode = 1; });
