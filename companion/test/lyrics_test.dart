import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:afterglow_companion/lyrics.dart';

void main() {
  test('enhanced LRC keeps word boundaries and does not highlight gaps', () {
    final doc = parseLrc(
      '[00:00]<00:00>Hello <00:01>world<00:02>\n[00:10]Again',
      20,
    );
    expect(doc.quality, 'estimated');
    expect(doc.words[0].text, 'Hello');
    expect(doc.words[1].end, 2);
    expect(doc.words[doc.wordAt(5)].end < 5, true);
    expect(doc.wordAt(-1), -1);
  });
  test('demo has genuine per-word fixture times', () {
    final doc = parseLrc(demoLrc, 32);
    expect(doc.quality, 'word');
    expect(doc.words[doc.wordAt(2.6)].text, 'glow');
    expect(doc.words.last.end, 32);
  });
  test('offset applies to all timestamps and repeated lines expand', () {
    final doc = parseLrc('[offset:500]\n[00:01][00:05]Hello world', 10);
    expect(doc.lines.map((l) => l.start), [1.5, 5.5]);
    expect(doc.quality, 'estimated');
  });
  test('line-only lyric gaps are capped conservatively', () {
    final doc = parseLrc('[00:00]Hello\n[01:00]Again', 65);
    expect(doc.lines.first.end, 7);
  });
  test('plain lyrics remain unsynced and metadata is removed', () {
    final doc = parseLrc('[ar:Fixture]\nA plain lyric');
    expect(doc.quality, 'unsynced');
    expect(doc.lines.single.text, 'A plain lyric');
    expect(doc.words, isEmpty);
  });
  test('TTML handles namespace, syllables, explicit spaces and timings', () {
    final doc = parseTtml(
      '<tt xmlns="http://www.w3.org/ns/ttml"><body><p begin="0s" end="3s"><span begin="0s" end="0.5s">Hel</span><span begin="0.5s" end="1s">lo</span> <span begin="1s" end="3s">world</span></p></body></tt>',
    );
    expect(doc.quality, 'word');
    expect(doc.words.map((w) => w.text), ['Hello', 'world']);
    expect(doc.words.first.end, 1);
  });
  test('invalid and oversized documents fail before rendering', () {
    expect(() => parseLrc('a' * (maxLyricsBytes + 1)), throwsFormatException);
    expect(() => parseTtml('<!DOCTYPE x><tt/>'), throwsFormatException);
    expect(() => xmlTime('NaNs'), throwsFormatException);
    expect(() => xmlTime('-2s'), throwsFormatException);
  });
  test(
    'provider query is HTTPS and line timing is labeled estimated',
    () async {
      final lookup = LyricLookup(
        MockClient((request) async {
          expect(request.url.scheme, 'https');
          expect(request.url.queryParameters['track_name'], 'Fixture');
          expect(request.url.queryParameters['duration'], '32');
          return http.Response(
            jsonEncode({'syncedLyrics': '[00:00]Hello world'}),
            200,
          );
        }),
      );
      final doc = await lookup.resolve({
        'title': 'Fixture',
        'artist': 'Afterglow',
        'duration': 32,
      });
      expect(doc.source, 'LRCLIB');
      expect(doc.quality, 'estimated');
    },
  );
  test('AMLL failure falls back and provider outages surface', () async {
    var requests = 0;
    final lookup = LyricLookup(
      MockClient((request) async {
        requests++;
        return request.url.host == 'raw.githubusercontent.com'
            ? http.Response('', 404)
            : http.Response('{"instrumental":true}', 200);
      }),
    );
    expect(
      (await lookup.resolve({
        'trackUrl': 'spotify:track:1234567890123456789012',
      })).quality,
      'instrumental',
    );
    expect(requests, 2);
    await expectLater(
      LyricLookup(
        MockClient((_) async => http.Response('', 503)),
      ).resolve({'title': 'Fixture'}),
      throwsA(isA<http.ClientException>()),
    );
  });
}
