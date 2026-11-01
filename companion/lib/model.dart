import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;
import 'dart:ui' as ui;
import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'lyrics.dart';

const accent = Color(0xFFA9E5C2);
const warm = Color(0xFFEBAE84);
const foreground = Color(0xFFF3F5EE);
const muted = Color(0xFFA9B7AE);
const surface = Color(0xFF131B17);
const border = Color(0xFF35473D);
const lyricPink = Color(0xFFC7839D);
const lyricHighlight = Color(0xFFB6486C);
const styles = {
  'ship': 'Ship',
  'fisheye': 'Fisheye',
  'fisheye_visual': 'Fisheye Visual',
  'visual': 'Visual',
  'lines': 'Lines',
};
const native = MethodChannel('afterglow/native');

class AfterglowModel extends ChangeNotifier {
  final bool isAndroid;
  AfterglowModel({bool? android}) : isAndroid = android ?? Platform.isAndroid;
  final client = http.Client();
  final clock = Stopwatch()..start();
  Timer? timer;
  SharedPreferences? prefs;
  Map<String, Object?> track = {};
  List<Map<String, Object?>> players = [];
  Lyrics lyrics = Lyrics([], 'missing', '');
  Uint8List? artwork;
  Color primary = accent, secondary = warm;
  String style = 'fisheye_visual',
      preferred = '',
      status = 'Start music in your player, or try the demo.';
  String audioStatus = 'Audio capture is off', error = '', key = '';
  bool demo = false,
      demoPlaying = true,
      reduceMotion = false,
      light = true,
      showLyrics = true;
  bool busy = false,
      permission = false,
      capturing = false,
      overlay = false,
      full = false,
      disposed = false;
  double intensity = .65, width = 36, size = 1, offset = 0, level = 0;
  double basePosition = 0, baseStamp = 0, speed = 1;
  int generation = 0;
  bool polling = false;
  Directory? dataDir;
  bool get playing => demo ? demoPlaying : track['playing'] == true;
  bool get hasTrack => demo || track.isNotEmpty;
  String get title => demo
      ? 'Let the room glow'
      : track['title'] as String? ?? 'Nothing playing yet';
  String get artist => demo
      ? 'Afterglow · original demo'
      : track['artist'] as String? ?? 'Your music, a little more alive.';
  double get duration =>
      demo ? 32 : (track['duration'] as num?)?.toDouble() ?? 0;
  double get seconds => clock.elapsedMicroseconds / 1e6;
  double get position {
    var value =
        basePosition +
        (playing ? math.max(0.0, seconds - baseStamp) * speed : 0);
    if (demo) return value % 32;
    return duration > 0 ? value.clamp(0.0, duration) : math.max(0, value);
  }

  double get visualPosition => math.max(0.0, position + offset);
  bool can(String action) => demo || track[action] == true;
  Future<Object?> call(String method, [Object? args]) async {
    try {
      return await native.invokeMethod<Object?>(method, args);
    } on PlatformException catch (e) {
      error = e.message ?? e.code;
    } on MissingPluginException {
      error = 'Native integration is unavailable in this build.';
    }
    return null;
  }

  Future<void> init({bool startDemo = false}) async {
    prefs = await SharedPreferences.getInstance();
    dataDir = await getApplicationSupportDirectory();
    style = prefs!.getString('style') ?? style;
    if (!styles.containsKey(style)) style = 'fisheye_visual';
    reduceMotion = prefs!.getBool('reduceMotion') ?? false;
    light = prefs!.getBool('light') ?? true;
    showLyrics = prefs!.getBool('showLyrics') ?? true;
    intensity = _pref('intensity', intensity, 0, 1);
    width = _pref('width', width, 8, 100);
    size = _pref('size', size, .5, 2);
    offset = _pref('offset', offset, -10, 10);
    native.setMethodCallHandler((event) async {
      if (event.method == 'exitStage') {
        full = false;
        overlay = false;
        notifyListeners();
      }
    });
    if (startDemo) setDemo(true);
    await poll();
    if (!disposed) {
      timer = Timer.periodic(const Duration(milliseconds: 400), (_) => poll());
    }
    if (!disposed) notifyListeners();
  }

  double _pref(String name, double fallback, double min, double max) {
    final v = prefs!.getDouble(name) ?? fallback;
    return v.isFinite ? v.clamp(min, max) : fallback;
  }

  Future<void> save() async {
    await prefs?.setString('style', style);
    await prefs?.setBool('reduceMotion', reduceMotion);
    await prefs?.setBool('light', light);
    await prefs?.setBool('showLyrics', showLyrics);
    for (final entry in {
      'intensity': intensity,
      'width': width,
      'size': size,
      'offset': offset,
    }.entries) {
      await prefs?.setDouble(entry.key, entry.value);
    }
  }

  void change(VoidCallback update) {
    update();
    unawaited(save());
    notifyListeners();
  }

  void setDemo(bool enabled) {
    generation++;
    demo = enabled;
    key = '';
    basePosition = 0;
    baseStamp = seconds;
    speed = 1;
    demoPlaying = true;
    artwork = null;
    primary = accent;
    secondary = warm;
    lyrics = enabled ? parseLrc(demoLrc, 32) : Lyrics([], 'missing', '');
    busy = false;
    status = enabled
        ? 'Original fixture lyrics · simulated audio · no song is played'
        : 'Following your selected player';
    notifyListeners();
    if (!enabled) unawaited(poll());
  }

  Future<void> poll() async {
    if (polling || disposed) return;
    polling = true;
    try {
      final raw = await call('snapshot', {'preferred': preferred});
      if (disposed || raw is! Map) return;
      final data = Map<String, Object?>.from(raw);
      permission = data['permission'] == true;
      capturing = data['capturing'] == true;
      overlay = data['overlay'] == true;
      level = ((data['level'] as num?)?.toDouble() ?? 0).clamp(0, 1);
      audioStatus = data['audioStatus'] as String? ?? audioStatus;
      players = (data['players'] as List? ?? [])
          .map((p) => Map<String, Object?>.from(p as Map))
          .toList();
      if (!demo) {
        final current = data['track'];
        track = current is Map ? Map<String, Object?>.from(current) : {};
        basePosition = (track['position'] as num?)?.toDouble() ?? 0;
        speed = (track['speed'] as num?)?.toDouble() ?? 1;
        baseStamp = seconds;
        final nextKey = track.isEmpty
            ? ''
            : jsonEncode([
                track['player'],
                track['title'],
                track['artist'],
                track['album'],
                track['duration'],
              ]);
        if (nextKey != key) {
          key = nextKey;
          generation++;
          artwork = track['artwork'] is Uint8List
              ? track['artwork'] as Uint8List
              : null;
          primary = accent;
          secondary = warm;
          lyrics = Lyrics([], 'missing', '');
          busy = false;
          if (track.isNotEmpty) unawaited(loadLyrics());
          if (artwork != null) unawaited(palette(artwork!, generation));
        }
        status =
            data['status'] as String? ??
            (track.isEmpty
                ? 'Start music in a player with system media controls.'
                : 'Connected to ${track['player']}');
      }
      if (isAndroid && overlay) await presentOverlay();
      notifyListeners();
    } finally {
      polling = false;
    }
  }

  Future<void> palette(Uint8List bytes, int request) async {
    ui.Codec? codec;
    ui.Image? image;
    try {
      codec = await ui.instantiateImageCodec(
        bytes,
        targetWidth: 24,
        targetHeight: 24,
      );
      image = (await codec.getNextFrame()).image;
      final data = await image.toByteData();
      if (data == null || request != generation || disposed) return;
      final colors = <Color>[];
      for (var i = 0; i + 3 < data.lengthInBytes; i += 4) {
        final c = Color.fromARGB(
          255,
          data.getUint8(i),
          data.getUint8(i + 1),
          data.getUint8(i + 2),
        );
        final h = HSLColor.fromColor(c);
        if (h.saturation > .25 && h.lightness > .15 && h.lightness < .85) {
          colors.add(c);
        }
      }
      if (colors.isNotEmpty) {
        primary = HSLColor.fromColor(
          colors[colors.length ~/ 3],
        ).withLightness(.68).toColor();
        secondary = HSLColor.fromColor(
          colors[colors.length * 2 ~/ 3],
        ).withLightness(.62).toColor();
        notifyListeners();
      }
    } catch (_) {
      /* Corrupt/unsupported art keeps fallback colors. */
    } finally {
      image?.dispose();
      codec?.dispose();
    }
  }

  String get storageKey => sha256.convert(utf8.encode(key)).toString();
  Future<void> loadLyrics({bool retry = false}) async {
    final request = ++generation;
    final identity = key, filename = storageKey;
    final snapshot = Map<String, Object?>.from(track);
    busy = true;
    error = '';
    notifyListeners();
    try {
      Lyrics? document;
      if (dataDir != null) {
        for (final kind in ['import', if (!retry) 'cache']) {
          final file = File('${dataDir!.path}/$kind/$filename.json');
          if (await file.exists() &&
              await file.length() <= maxLyricsBytes * 2) {
            try {
              final data =
                  jsonDecode(await file.readAsString()) as Map<String, dynamic>;
              if (data['key'] == identity) {
                document = data['format'] == 'ttml'
                    ? parseTtml(data['text'] as String)
                    : parseLrc(
                        data['text'] as String,
                        (snapshot['duration'] as num?)?.toDouble() ?? 0,
                      );
                document = Lyrics(
                  document.lines,
                  document.quality,
                  kind == 'import' ? 'Imported file' : 'Local cache',
                );
                break;
              }
            } catch (_) {
              /* Cache damage should not prevent a fresh lookup. */
            }
          }
        }
      }
      if (document == null) {
        document = await LyricLookup(client).resolve(snapshot);
        if (document.lines.isNotEmpty &&
            dataDir != null &&
            request == generation &&
            !disposed) {
          // Serialize as enhanced LRC, preserving source quality on reload.
          final lrc = document.lines
              .map(
                (l) => document!.quality == 'word'
                    ? '[${stamp(l.start)}]${l.words.map((w) => '<${stamp(w.start)}>${w.text} ').join()}<${stamp(l.end)}>'
                    : '[${stamp(l.start)}]${l.text}',
              )
              .join('\n');
          if (document.quality != 'unsynced') {
            await writeDocument('cache', filename, identity, lrc, 'lrc');
          }
        }
      }
      if (request != generation || disposed || demo) return;
      lyrics = document;
    } catch (e) {
      if (request == generation && !disposed) {
        error = 'Lyrics unavailable. Retry or import LRC / TTML.';
      }
    } finally {
      if (request == generation && !disposed) {
        busy = false;
        notifyListeners();
      }
    }
  }

  Future<void> writeDocument(
    String kind,
    String filename,
    String identity,
    String text,
    String format,
  ) async {
    final dir = Directory('${dataDir!.path}/$kind');
    await dir.create(recursive: true);
    final target = File('${dir.path}/$filename.json');
    final temp = File('${target.path}.tmp');
    await temp.writeAsString(
      jsonEncode({'key': identity, 'text': text, 'format': format}),
      flush: true,
    );
    if (await target.exists()) await target.delete();
    await temp.rename(target.path);
    if (kind == 'cache') {
      final files = await dir
          .list()
          .where((f) => f.path.endsWith('.json'))
          .toList();
      if (files.length > 500) {
        final dated = await Future.wait(
          files.map((f) async => (f, (await f.stat()).modified)),
        );
        dated.sort((a, b) => a.$2.compareTo(b.$2));
        for (final item in dated.take(files.length - 500)) {
          await item.$1.delete();
        }
      }
    }
  }

  Future<void> importLyrics(String text, String name) async {
    final parsed = name.toLowerCase().endsWith('.ttml')
        ? parseTtml(text)
        : parseLrc(text, duration);
    if (parsed.lines.isEmpty) {
      throw const FormatException('This file contains no lyrics.');
    }
    generation++;
    lyrics = parsed;
    busy = false;
    error = '';
    if (!demo && track.isNotEmpty && dataDir != null) {
      await writeDocument(
        'import',
        storageKey,
        key,
        text,
        name.toLowerCase().endsWith('.ttml') ? 'ttml' : 'lrc',
      );
    }
    notifyListeners();
  }

  Future<void> command(String action) async {
    if (demo) {
      if (action == 'playPause') {
        basePosition = position;
        baseStamp = seconds;
        demoPlaying = !demoPlaying;
      } else {
        basePosition = 0;
        baseStamp = seconds;
      }
      notifyListeners();
      return;
    }
    if (!can(
      action == 'playPause'
          ? 'canToggle'
          : action == 'next'
          ? 'canNext'
          : 'canPrevious',
    )) {
      return;
    }
    await call('command', {'action': action, 'player': track['player']});
    await poll();
  }

  Future<void> select(String id) async {
    preferred = id;
    await poll();
  }

  Future<void> capture(bool enabled) async {
    await call('capture', enabled);
    await poll();
  }

  Future<void> stage(bool enabled) async {
    {
      final result = await call('fullscreen', enabled);
      if (result == null && error.isNotEmpty) {
        notifyListeners();
        return;
      }
    }
    full = enabled;
    notifyListeners();
  }

  Future<void> showOverlay(bool enabled) async {
    final result = await call('overlay', enabled);
    if (result == true) {
      overlay = enabled;
      if (!isAndroid) full = enabled;
    }
    if (enabled && result == true) await presentOverlay();
    notifyListeners();
  }

  Future<void> presentOverlay() async {
    if (!isAndroid || !overlay) return;
    final i = lyrics.wordAt(visualPosition);
    final words = i < 0
        ? <LyricWord>[]
        : lyrics.words.sublist(math.max(0, i - 2), i + 1);
    await call('present', {
      'words': words.map((w) => w.text).toList(),
      'active': i >= 0 && visualPosition < lyrics.words[i].end,
      'primary': primary.toARGB32(),
      'secondary': secondary.toARGB32(),
      'intensity': intensity,
      'width': width,
      'size': size,
      'light': light,
      'lyrics': showLyrics,
      'reduced': reduceMotion,
      'timeline': lyrics.words.map((w) => [w.text, w.start, w.end]).toList(),
      'position': visualPosition,
      'playing': playing,
      'speed': speed,
      'demo': demo,
      'demoLevel': demo
          ? demoPlaying
                ? .35 + .3 * math.sin(seconds * 4).abs()
                : .08
          : -1.0,
    });
  }

  @override
  void dispose() {
    disposed = true;
    generation++;
    timer?.cancel();
    client.close();
    native.setMethodCallHandler(null);
    super.dispose();
  }
}

String stamp(double s) =>
    '${(s ~/ 60).toString().padLeft(2, '0')}:${(s % 60).toStringAsFixed(3).padLeft(6, '0')}';
String timeLabel(double s) =>
    '${s ~/ 60}:${(s.toInt() % 60).toString().padLeft(2, '0')}';
