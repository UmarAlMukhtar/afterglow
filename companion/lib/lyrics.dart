import 'dart:convert';
import 'dart:math' as math;
import 'package:http/http.dart' as http;
import 'package:xml/xml.dart';

const maxLyricsBytes = 2 * 1024 * 1024;
const demoLrc =
    '''[00:00.00]<00:00.00>Let <00:01.00>the <00:01.50>room <00:02.50>glow<00:04.00>
[00:04.00]<00:04.00>Follow <00:05.20>every <00:06.40>little <00:07.30>sound<00:09.00>
[00:09.00]<00:09.00>Colors <00:10.50>rise <00:11.60>and <00:12.20>fall<00:14.00>
[00:14.00]<00:14.00>Let <00:15.00>the <00:15.50>words <00:16.70>surround<00:19.00>
[00:19.00]<00:19.00>A <00:19.60>little <00:20.50>light <00:22.00>for <00:22.70>you<00:25.00>
[00:25.00]<00:25.00>Stay <00:26.40>here <00:27.70>in <00:28.30>the <00:29.00>music<00:32.00>''';

class LyricWord {
  final String text;
  final double start, end;
  const LyricWord(this.text, this.start, this.end);
}

class LyricLine {
  final String text;
  final double start, end;
  final List<LyricWord> words;
  const LyricLine(this.text, this.start, this.end, this.words);
}

class Lyrics {
  final List<LyricLine> lines;
  final String quality, source;
  late final words = lines.expand((l) => l.words).toList()
    ..sort((a, b) => a.start.compareTo(b.start));
  Lyrics(this.lines, this.quality, this.source);
  String get label => switch (quality) {
    'word' => 'Word-synced',
    'estimated' => 'Estimated word timing',
    'unsynced' => 'Unsynced lyrics',
    'instrumental' => 'Instrumental',
    _ => 'No lyrics found',
  };
  int wordAt(double position) {
    var lo = 0, hi = words.length;
    while (lo < hi) {
      final mid = (lo + hi) ~/ 2;
      if (words[mid].start <= position) {
        lo = mid + 1;
      } else {
        hi = mid;
      }
    }
    return lo - 1;
  }
}

List<LyricWord> estimatedWords(String text, double start, double end) {
  final tokens = text
      .trim()
      .split(RegExp(r'\s+'))
      .where((s) => s.isNotEmpty)
      .toList();
  final total = tokens.fold<int>(0, (s, w) => s + w.length);
  var cursor = start;
  return tokens.map((w) {
    final stop = cursor + (end - start) * w.length / math.max(1, total);
    final result = LyricWord(w, cursor, stop);
    cursor = stop;
    return result;
  }).toList();
}

final _lineTag = RegExp(r'\[(\d{1,3}):(\d{2}(?:\.\d+)?)\]');
final _wordTag = RegExp(r'<(\d{1,3}):(\d{2}(?:\.\d+)?)>');
double _stamp(RegExpMatch m) => int.parse(m[1]!) * 60 + double.parse(m[2]!);
void _check(String text) {
  if (utf8.encode(text).length > maxLyricsBytes ||
      '\n'.allMatches(text).length > 20000) {
    throw const FormatException('Lyrics file is too large (maximum 2 MB).');
  }
}

Lyrics parseLrc(String text, [double duration = 0]) {
  _check(text);
  final offset =
      (int.tryParse(
            RegExp(
                  r'\[offset:([+-]?\d+)\]',
                  caseSensitive: false,
                ).firstMatch(text)?[1] ??
                '',
          ) ??
          0) /
      1000;
  final entries = <double, String>{};
  var expanded = 0;
  for (final raw in const LineSplitter().convert(text)) {
    final tags = _lineTag.allMatches(raw).toList();
    if (tags.isEmpty) continue;
    final body = raw.substring(tags.last.end).trim();
    if (body.replaceAll(_wordTag, '').trim().isEmpty) continue;
    for (final tag in tags) {
      final start = math.max(0.0, _stamp(tag) + offset);
      if (!entries.containsKey(start)) {
        expanded += body.length;
        if (expanded > maxLyricsBytes * 4 || entries.length >= 20000) {
          throw const FormatException('Too many lyric events.');
        }
        entries[start] = body;
      }
    }
  }
  if (entries.isEmpty) {
    final plain = text
        .split('\n')
        .where(
          (l) => !RegExp(
            r'^\[[a-z]+:.*\]$',
            caseSensitive: false,
          ).hasMatch(l.trim()),
        )
        .join('\n')
        .trim();
    return Lyrics(
      plain.isEmpty ? [] : [LyricLine(plain, 0, 0, [])],
      plain.isEmpty ? 'missing' : 'unsynced',
      'Imported LRC',
    );
  }
  final starts = entries.keys.toList()..sort();
  final lines = <LyricLine>[];
  var exact = true;
  for (var i = 0; i < starts.length; i++) {
    final start = starts[i], body = entries[start]!;
    final tags = _wordTag.allMatches(body).toList();
    final boundary = i + 1 < starts.length
        ? starts[i + 1]
        : duration > start
        ? duration
        : tags.isNotEmpty
        ? math.max(start + 5, _stamp(tags.last) + offset + 3)
        : start + 5;
    var end = tags.isEmpty ? math.min(boundary, start + 7) : boundary;
    final words = <LyricWord>[];
    for (var j = 0; j < tags.length; j++) {
      final token = body
          .substring(
            tags[j].end,
            j + 1 < tags.length ? tags[j + 1].start : body.length,
          )
          .trim();
      final a = math.max(start, _stamp(tags[j]) + offset);
      final b = math.min(
        end,
        j + 1 < tags.length ? _stamp(tags[j + 1]) + offset : end,
      );
      if (token.isNotEmpty && b > a) words.add(LyricWord(token, a, b));
    }
    final clean = body.replaceAll(_wordTag, '').trim();
    exact &= words.isNotEmpty;
    if (words.isNotEmpty) end = math.min(end, words.last.end);
    lines.add(
      LyricLine(
        clean,
        start,
        end,
        words.isEmpty ? estimatedWords(clean, start, end) : words,
      ),
    );
  }
  if (lines.fold<int>(0, (n, l) => n + l.words.length) > 50000) {
    throw const FormatException('Too many lyric words.');
  }
  return Lyrics(lines, exact ? 'word' : 'estimated', 'LRC');
}

double xmlTime(String? value) {
  if (value == null) throw const FormatException('Missing TTML time.');
  double result;
  if (value.endsWith('ms')) {
    result = double.parse(value.substring(0, value.length - 2)) / 1000;
  } else if (value.endsWith('s')) {
    result = double.parse(value.substring(0, value.length - 1));
  } else {
    result = value.split(':').fold(0.0, (n, p) => n * 60 + double.parse(p));
  }
  if (!result.isFinite || result < 0) {
    throw const FormatException('Invalid TTML time.');
  }
  return result;
}

Lyrics parseTtml(String text) {
  _check(text);
  if (RegExp(r'<!\s*(DOCTYPE|ENTITY)', caseSensitive: false).hasMatch(text)) {
    throw const FormatException('XML declarations are not allowed.');
  }
  final doc = XmlDocument.parse(text);
  final lines = <LyricLine>[];
  var exact = true;
  for (final p in doc.descendants.whereType<XmlElement>().where(
    (e) => e.name.local == 'p' && e.getAttribute('begin') != null,
  )) {
    final start = xmlTime(p.getAttribute('begin')),
        end = xmlTime(p.getAttribute('end'));
    if (end <= start) continue;
    final words = <LyricWord>[];
    for (final span in p.childElements) {
      if (span.getAttribute('begin') == null ||
          span.getAttribute('end') == null) {
        continue;
      }
      final a = math.max(start, xmlTime(span.getAttribute('begin'))),
          b = math.min(end, xmlTime(span.getAttribute('end')));
      final token = span.innerText;
      if (b <= a || token.trim().isEmpty) continue;
      // TTML frequently splits a word into syllable spans, separated by no whitespace.
      final previous = span.previousSibling;
      final separated =
          token.startsWith(RegExp(r'\s')) ||
          previous is XmlText &&
              previous.value.trim().isEmpty &&
              previous.value.isNotEmpty;
      if (words.isNotEmpty && !separated) {
        final old = words.removeLast();
        words.add(LyricWord(old.text + token.trim(), old.start, b));
      } else {
        words.add(LyricWord(token.trim(), a, b));
      }
    }
    final text = p.innerText.trim();
    if (text.isEmpty) continue;
    exact &= words.isNotEmpty;
    lines.add(
      LyricLine(
        text,
        start,
        end,
        words.isEmpty ? estimatedWords(text, start, end) : words,
      ),
    );
    if (lines.length > 20000) {
      throw const FormatException('Too many lyric lines.');
    }
  }
  lines.sort((a, b) => a.start.compareTo(b.start));
  return Lyrics(
    lines,
    lines.isEmpty
        ? 'missing'
        : exact
        ? 'word'
        : 'estimated',
    'AMLL TTML',
  );
}

class LyricLookup {
  final http.Client client;
  LyricLookup(this.client);
  Future<String> get(Uri uri) => _get(uri).timeout(const Duration(seconds: 16));
  Future<String> _get(Uri uri) async {
    if (uri.scheme != 'https' || uri.userInfo.isNotEmpty) {
      throw const FormatException(
        'Only HTTPS providers without credentials are supported.',
      );
    }
    final response = await client
        .send(
          http.Request('GET', uri)
            ..followRedirects = false
            ..headers['User-Agent'] =
                'Afterglow/0.2 (open-source music companion)',
        )
        .timeout(const Duration(seconds: 8));
    if (response.statusCode != 200) {
      await response.stream.drain<void>();
      throw http.ClientException('Provider returned ${response.statusCode}');
    }
    final bytes = <int>[];
    await for (final chunk in response.stream.timeout(
      const Duration(seconds: 8),
    )) {
      bytes.addAll(chunk);
      if (bytes.length > maxLyricsBytes) {
        throw const FormatException('Provider response too large.');
      }
    }
    return utf8.decode(bytes);
  }

  Future<Lyrics> resolve(Map<String, Object?> track) async {
    final url = track['trackUrl'] as String? ?? '';
    final id = RegExp(
      r'(?:spotify:track:|open\.spotify\.com/track/)([A-Za-z0-9]{22})\b',
    ).firstMatch(url)?[1];
    if (id != null) {
      try {
        final doc = parseTtml(
          await get(
            Uri.https(
              'raw.githubusercontent.com',
              '/amll-dev/amll-ttml-db/main/spotify-lyrics/$id.ttml',
            ),
          ),
        );
        if (doc.lines.isNotEmpty) return doc;
      } catch (_) {
        /* Fall through to metadata lookup. */
      }
    }
    final query = {
      'track_name': '${track['title'] ?? ''}',
      'artist_name': '${track['artist'] ?? ''}',
    };
    if ('${track['album'] ?? ''}'.isNotEmpty) {
      query['album_name'] = '${track['album']}';
    }
    final duration = (track['duration'] as num?)?.toDouble() ?? 0;
    if (duration > 0) query['duration'] = duration.round().toString();
    final data =
        jsonDecode(await get(Uri.https('lrclib.net', '/api/get', query)))
            as Map<String, dynamic>;
    if (data['instrumental'] == true) {
      return Lyrics([], 'instrumental', 'LRCLIB');
    }
    final synced = data['syncedLyrics'] as String? ?? '';
    final result = parseLrc(
      synced.isNotEmpty ? synced : data['plainLyrics'] as String? ?? '',
      duration,
    );
    return Lyrics(result.lines, result.quality, 'LRCLIB');
  }
}
