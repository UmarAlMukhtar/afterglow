import 'dart:async';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'model.dart';

class LyricStage extends StatefulWidget {
  final AfterglowModel model;
  final bool preview;
  const LyricStage({super.key, required this.model, this.preview = false});
  @override
  State<LyricStage> createState() => _LyricStageState();
}

class _LyricStageState extends State<LyricStage>
    with SingleTickerProviderStateMixin {
  late Ticker ticker;
  final frame = ValueNotifier<int>(0);
  double last = 0, lastOverlay = 0, smoothLevel = 0;
  final motion = LyricMotion();
  @override
  void initState() {
    super.initState();
    ticker = createTicker((elapsed) {
      final now = elapsed.inMicroseconds / 1e6;
      if (now - last < 1 / 30) return;
      last = now;
      final m = widget.model;
      final target = m.demo
          ? m.playing
                ? .22 + .36 * math.sin(m.position * 3.8).abs()
                : .06
          : m.level;
      smoothLevel +=
          (target - smoothLevel) * (target > smoothLevel ? .28 : .08);
      frame.value++;
      if (now - lastOverlay > .1) {
        lastOverlay = now;
        unawaited(m.presentOverlay());
      }
    })..start();
  }

  @override
  void dispose() {
    ticker.dispose();
    frame.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => RepaintBoundary(
    child: Stack(
      children: [
        Positioned.fill(
          child: CustomPaint(
            painter: ScenePainter(
              widget.model,
              frame,
              () => smoothLevel,
              MediaQuery.disableAnimationsOf(context),
              motion,
            ),
            isComplex: true,
            willChange: widget.model.playing,
          ),
        ),
        if (widget.preview)
          Positioned(
            left: 16,
            right: 16,
            bottom: 16,
            child: Row(
              children: [
                const Icon(Icons.circle, size: 6, color: accent),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    widget.model.demo
                        ? 'DEMO PREVIEW'
                        : widget.model.hasTrack
                        ? 'LIVE PREVIEW'
                        : 'YOUR LYRIC STAGE',
                    style: const TextStyle(
                      fontSize: 10,
                      letterSpacing: 1.7,
                      color: muted,
                    ),
                  ),
                ),
                if (widget.model.hasTrack)
                  Text(
                    '${timeLabel(widget.model.position)} / ${timeLabel(widget.model.duration)}',
                    style: const TextStyle(fontSize: 11, color: muted),
                  ),
              ],
            ),
          ),
      ],
    ),
  );
}

class ScenePainter extends CustomPainter {
  final AfterglowModel m;
  final double Function() level;
  final bool systemReduced;
  final LyricMotion motion;
  ScenePainter(
    this.m,
    Listenable frame,
    this.level,
    this.systemReduced,
    this.motion,
  ) : super(repaint: frame);
  static final Map<String, IconData> symbols = {
    'love': Icons.favorite,
    'heart': Icons.favorite,
    'light': Icons.auto_awesome,
    'glow': Icons.auto_awesome,
    'sound': Icons.music_note,
    'music': Icons.music_note,
    'room': Icons.home_outlined,
    'home': Icons.home_outlined,
    'sun': Icons.wb_sunny_outlined,
    'night': Icons.nightlight_round,
    'moon': Icons.nightlight_round,
    'time': Icons.schedule,
    'words': Icons.chat_bubble_outline,
    'rise': Icons.north_east,
    'fall': Icons.south_east,
    'you': Icons.person_outline,
    'dream': Icons.auto_awesome,
  };
  void text(
    Canvas c,
    String value,
    Offset at,
    double fontSize,
    Color color, {
    FontWeight weight = FontWeight.w800,
    double maxWidth = double.infinity,
  }) {
    final p = TextPainter(
      text: TextSpan(
        text: value,
        style: TextStyle(
          color: color,
          fontSize: fontSize,
          fontWeight: weight,
          height: 1.05,
          letterSpacing: -fontSize * .035,
        ),
      ),
      textDirection: TextDirection.ltr,
      textAlign: TextAlign.center,
    )..layout(maxWidth: maxWidth);
    p.paint(c, at - Offset(p.width / 2, p.height / 2));
  }

  @override
  void paint(Canvas canvas, Size s) {
    if (s.isEmpty) return;
    canvas.clipRect(Offset.zero & s);
    canvas.drawColor(Colors.black, BlendMode.src);
    if (m.light) {
      final strength = m.intensity * (.13 + level() * .85);
      final w = (m.width * s.shortestSide / 400).clamp(
        7.0,
        s.shortestSide * .25,
      );
      for (var side = 0; side < 4; side++) {
        final colors = [m.primary, m.secondary, m.primary, m.secondary];
        final bounds = switch (side) {
          0 => Rect.fromLTWH(0, 0, w * 3, s.height),
          1 => Rect.fromLTWH(s.width - w * 3, 0, w * 3, s.height),
          2 => Rect.fromLTWH(0, 0, s.width, w * 3),
          _ => Rect.fromLTWH(0, s.height - w * 3, s.width, w * 3),
        };
        final from = [
          Alignment.centerLeft,
          Alignment.centerRight,
          Alignment.topCenter,
          Alignment.bottomCenter,
        ][side];
        final to = [
          Alignment.centerRight,
          Alignment.centerLeft,
          Alignment.bottomCenter,
          Alignment.topCenter,
        ][side];
        canvas.drawRect(
          bounds,
          Paint()
            ..shader = LinearGradient(
              begin: from,
              end: to,
              colors: [
                colors[side].withValues(alpha: strength),
                colors[side].withValues(alpha: strength * .12),
                colors[side].withValues(alpha: 0),
              ],
              stops: const [0, .4, 1],
            ).createShader(bounds),
        );
      }
    }
    if (!m.showLyrics) return;
    final pos = m.visualPosition, doc = m.lyrics;
    if (doc.quality == 'unsynced' && doc.lines.isNotEmpty) {
      text(
        canvas,
        doc.lines.first.text,
        s.center(Offset.zero),
        20 * m.size,
        muted,
        weight: FontWeight.w500,
        maxWidth: s.width * .8,
      );
      return;
    }
    final index = doc.wordAt(pos);
    if (index < 0 || doc.words.isEmpty) {
      if (!m.hasTrack || m.demo || m.busy || doc.lines.isEmpty) {
        text(
          canvas,
          m.busy
              ? 'Finding the words…'
              : doc.quality == 'instrumental'
              ? 'Just the music.'
              : m.hasTrack
              ? 'Let the music glow.'
              : 'A little light.\nA little closer.',
          Offset(s.width / 2, s.height * .47),
          math.min(34.0, s.width * .085),
          foreground,
          weight: FontWeight.w600,
          maxWidth: s.width * .76,
        );
      }
      return;
    }
    final reduced = m.reduceMotion || systemReduced;
    final current = doc.words[index];
    final active = pos >= current.start && pos < current.end;
    if (m.style == 'lines') {
      final lineIndex = doc.lines.indexWhere(
        (l) => l.start <= pos && pos < l.end,
      );
      if (lineIndex >= 0) {
        for (var d = -1; d <= 1; d++) {
          final n = lineIndex + d;
          if (n < 0 || n >= doc.lines.length) continue;
          text(
            canvas,
            doc.lines[n].text,
            Offset(s.width / 2, s.height / 2 + d * s.height * .2),
            (d == 0 ? 30.0 : 21.0) * m.size,
            d == 0 ? foreground : muted.withValues(alpha: .5),
            maxWidth: s.width * .82,
          );
        }
      }
      return;
    }
    final lens = m.style.startsWith('fisheye');
    final visual = m.style == 'visual' || m.style == 'fisheye_visual';
    final progress =
        ((pos - current.start) / math.max(.001, current.end - current.start))
            .clamp(0.0, 1.0);
    final phase = reduced || !m.playing ? 0.0 : m.seconds;
    final focus = motion.sample(index, progress, m.seconds, reduced);
    for (var n = math.max(0, index - 2); n <= index; n++) {
      final d = n - index;
      final word = doc.words[n].text;
      final selected = d == 0 && active;
      final y = s.height * .64 + (n - focus) * s.height * .245;
      final x =
          s.width * .5 +
          math.sin(phase * .38 + n * .73) * s.width * (reduced ? 0 : .022);
      final font =
          math.min(s.width * .25, s.height * .22) * m.size * (1 + d * .11);
      final p = TextPainter(
        text: TextSpan(
          text: word,
          style: TextStyle(
            fontSize: font,
            fontWeight: FontWeight.w900,
            letterSpacing: -font * .045,
            height: 1,
            color: selected
                ? foreground
                : lyricPink.withValues(alpha: d == 0 ? .75 : .6 + d * .14),
          ),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      final fit = math.min(1.0, s.width * .76 / math.max(1, p.width));
      canvas.save();
      canvas.translate(x, y);
      canvas.rotate(reduced ? 0 : math.sin(phase * .22 + n * .9) * .012);
      canvas.scale(fit, fit);
      if (lens) {
        _lensWord(
          canvas,
          p,
          Rect.fromLTWH(
            -p.width / 2 - 14,
            -p.height / 2 - 5,
            p.width + 28,
            p.height + 10,
          ),
          selected,
        );
      } else {
        canvas.transform(
          (Matrix4.identity()
                ..setEntry(3, 1, -.00055)
                ..rotateY(-.12))
              .storage,
        );
        if (selected) {
          canvas.drawRRect(
            RRect.fromRectAndRadius(
              Rect.fromLTWH(
                -p.width / 2 - 12,
                -p.height / 2 - 4,
                p.width + 24,
                p.height + 8,
              ),
              const Radius.circular(3),
            ),
            Paint()..color = lyricHighlight,
          );
        }
        p.paint(canvas, Offset(-p.width / 2, -p.height / 2));
      }
      if (visual) {
        final symbol =
            symbols[word.toLowerCase().replaceAll(RegExp(r'[^a-z]'), '')];
        if (symbol != null) {
          final icon = TextPainter(
            text: TextSpan(
              text: String.fromCharCode(symbol.codePoint),
              style: TextStyle(
                fontFamily: symbol.fontFamily,
                package: symbol.fontPackage,
                color: selected ? foreground : lyricPink,
                fontSize: font * .32,
              ),
            ),
            textDirection: TextDirection.ltr,
          )..layout();
          icon.paint(canvas, Offset(p.width / 2 + 25, -icon.height / 2));
        }
      }
      canvas.restore();
    }
  }

  void _lensWord(Canvas c, TextPainter text, Rect rect, bool selected) {
    // Slice a shaped word through a cylindrical lens: the center bulges while
    // outer glyphs taper independently. Flutter retains multilingual shaping.
    const slices = 32;
    for (var i = 0; i < slices; i++) {
      final x0 = rect.left + rect.width * i / slices;
      final x1 = rect.left + rect.width * (i + 1) / slices;
      final normalized = ((x0 + x1) / 2) / (rect.width / 2);
      final curve = 1.12 - .3 * normalized * normalized;
      c.save();
      c.clipRect(Rect.fromLTRB(x0, rect.top * 1.3, x1 + .5, rect.bottom * 1.3));
      c.scale(1, curve);
      if (selected) {
        c.drawRRect(
          RRect.fromRectAndRadius(rect, const Radius.circular(3)),
          Paint()..color = lyricHighlight,
        );
      }
      text.paint(c, Offset(-text.width / 2, -text.height / 2));
      c.restore();
    }
  }

  @override
  bool shouldRepaint(covariant ScenePainter old) => true;
}

class LyricMotion {
  double? focus;
  double velocity = 0, last = 0;
  double sample(int index, double progress, double now, bool reduced) {
    final target = index + (reduced ? 0.0 : progress * .16);
    if (focus == null || reduced || (focus! - target).abs() > 4) {
      focus = target;
      velocity = 0;
      last = now;
      return target;
    }
    final dt = (now - last).clamp(0.0, .05) / 2;
    last = now;
    for (var i = 0; i < 2; i++) {
      velocity += ((target - focus!) * 55 - velocity * 13.5) * dt;
      focus = focus! + velocity * dt;
    }
    return focus!;
  }
}
