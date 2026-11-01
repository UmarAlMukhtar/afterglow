import 'dart:async';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'model.dart';
import 'stage.dart';

class AfterglowApp extends StatefulWidget {
  final bool startDemo;
  final AfterglowModel? model;
  const AfterglowApp({super.key, this.startDemo = false, this.model});
  @override
  State<AfterglowApp> createState() => _AfterglowAppState();
}

class _AfterglowAppState extends State<AfterglowApp> {
  late final model = widget.model ?? AfterglowModel();
  @override
  void initState() {
    super.initState();
    if (widget.model == null) {
      unawaited(model.init(startDemo: widget.startDemo));
    }
  }

  @override
  void dispose() {
    if (widget.model == null) model.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Afterglow',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      brightness: Brightness.dark,
      scaffoldBackgroundColor: Colors.black,
      colorScheme: const ColorScheme.dark(
        primary: accent,
        secondary: warm,
        surface: surface,
        onSurface: foreground,
        onPrimary: Colors.black,
        outline: border,
      ),
      textTheme: ThemeData.dark().textTheme.apply(
        bodyColor: foreground,
        displayColor: foreground,
      ),
      useMaterial3: true,
      sliderTheme: const SliderThemeData(
        trackHeight: 3,
        showValueIndicator: ShowValueIndicator.onDrag,
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size(48, 48),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          minimumSize: const Size(48, 48),
          side: const BorderSide(color: border),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
          ),
        ),
      ),
    ),
    home: ListenableBuilder(
      listenable: model,
      builder: (context, _) => Home(model: model),
    ),
  );
}

class Home extends StatelessWidget {
  final AfterglowModel model;
  const Home({super.key, required this.model});
  Future<void> import(BuildContext context) async {
    try {
      final file = await openFile(
        acceptedTypeGroups: [
          const XTypeGroup(
            label: 'Lyrics',
            extensions: ['lrc', 'ttml', 'txt'],
            mimeTypes: [
              'text/*',
              'application/ttml+xml',
              'application/octet-stream',
            ],
          ),
        ],
      );
      if (file == null) return;
      if (await file.length() > 2 * 1024 * 1024) {
        throw const FormatException('Lyrics file must be smaller than 2 MB.');
      }
      await model.importLyrics(await file.readAsString(), file.name);
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Could not import lyrics: $e')));
      }
    }
  }

  Future<void> permissions(BuildContext context) async {
    final accepted = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Follow your music'),
        content: const Text(
          'Android uses notification access to let Afterglow read active media sessions and control playback. This permission can expose other notifications too. Afterglow only reads media sessions; it does not store or upload notifications.\n\nEnable Afterglow on the next screen, then return here.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Open settings'),
          ),
        ],
      ),
    );
    if (accepted == true) await model.call('permissions');
  }

  Future<void> capture(BuildContext context) async {
    if (model.capturing) {
      await model.capture(false);
      return;
    }
    if (model.isAndroid) {
      final accepted = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('React to playback audio'),
          content: const Text(
            'Afterglow analyzes playback volume in memory. No audio is saved or uploaded, and no microphone source is opened.\n\nAndroid calls its required permission “Record audio” and also asks for capture consent. Some players block playback capture; lyrics still work.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Continue'),
            ),
          ],
        ),
      );
      if (accepted != true) return;
    }
    await model.capture(true);
  }

  @override
  Widget build(BuildContext context) {
    if (model.full) {
      return PopScope(
        canPop: false,
        onPopInvokedWithResult: (didPop, _) {
          if (!didPop) unawaited(model.stage(false));
        },
        child: Shortcuts(
          shortcuts: const {
            SingleActivator(LogicalKeyboardKey.escape): DismissIntent(),
            SingleActivator(LogicalKeyboardKey.space): ActivateIntent(),
          },
          child: Actions(
            actions: {
              DismissIntent: CallbackAction<DismissIntent>(
                onInvoke: (_) {
                  unawaited(model.stage(false));
                  return null;
                },
              ),
              ActivateIntent: CallbackAction<ActivateIntent>(
                onInvoke: (_) {
                  unawaited(model.command('playPause'));
                  return null;
                },
              ),
            },
            child: Focus(
              autofocus: true,
              child: Scaffold(
                body: Stack(
                  children: [
                    Positioned.fill(child: LyricStage(model: model)),
                    if (!model.overlay)
                      SafeArea(
                        child: Align(
                          alignment: Alignment.topRight,
                          child: Padding(
                            padding: const EdgeInsets.all(16),
                            child: IconButton.filledTonal(
                              tooltip: 'Return to controls (Escape)',
                              onPressed: () => model.stage(false),
                              icon: const Icon(Icons.close),
                            ),
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ),
        ),
      );
    }
    return Scaffold(
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final wide =
                constraints.maxWidth >= 940 && constraints.maxHeight >= 540;
            final controls = _controls(context);
            if (wide) {
              return Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Expanded(
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(32, 24, 16, 24),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          _brand(),
                          const SizedBox(height: 24),
                          Expanded(
                            child: ClipRRect(
                              borderRadius: BorderRadius.circular(16),
                              child: DecoratedBox(
                                decoration: BoxDecoration(
                                  border: Border.all(color: border),
                                  borderRadius: BorderRadius.circular(16),
                                ),
                                child: LyricStage(model: model, preview: true),
                              ),
                            ),
                          ),
                          const SizedBox(height: 16),
                          _caption(),
                        ],
                      ),
                    ),
                  ),
                  SizedBox(
                    width: 400,
                    child: SingleChildScrollView(
                      padding: const EdgeInsets.fromLTRB(24, 32, 32, 32),
                      child: controls,
                    ),
                  ),
                ],
              );
            }
            return SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(24, 24, 24, 32),
              child: Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 600),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      _brand(),
                      const SizedBox(height: 24),
                      ClipRRect(
                        borderRadius: BorderRadius.circular(14),
                        child: SizedBox(
                          height: constraints.maxHeight < 500 ? 180 : 260,
                          child: LyricStage(model: model, preview: true),
                        ),
                      ),
                      const SizedBox(height: 12),
                      _caption(),
                      const SizedBox(height: 28),
                      controls,
                    ],
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _brand() => Row(
    children: [
      const Icon(Icons.blur_on, size: 32, color: accent),
      const SizedBox(width: 12),
      const Expanded(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'afterglow',
              style: TextStyle(
                fontSize: 28,
                fontWeight: FontWeight.w700,
                letterSpacing: -1,
              ),
            ),
            Text(
              'Lyrics and light for your music.',
              style: TextStyle(color: muted, fontSize: 13),
            ),
          ],
        ),
      ),
      if (model.demo)
        const Chip(label: Text('DEMO'), visualDensity: VisualDensity.compact),
    ],
  );
  Widget _caption() => Row(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Icon(
        model.busy ? Icons.hourglass_top : Icons.lyrics_outlined,
        size: 16,
        color: muted,
      ),
      const SizedBox(width: 8),
      Expanded(
        child: Text(
          model.busy
              ? 'Looking for lyrics…'
              : '${model.lyrics.label}${model.lyrics.source.isNotEmpty ? ' · ${model.lyrics.source}' : ''}',
          style: const TextStyle(color: muted, fontSize: 12),
        ),
      ),
    ],
  );
  Widget _controls(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      if (model.isAndroid && !model.permission) ...[
        const Text(
          'Connect your player',
          style: TextStyle(fontSize: 20, fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 8),
        const Text(
          'Play music in Spotify or another app, then allow access to its media controls.',
          style: TextStyle(color: muted, height: 1.5),
        ),
        const SizedBox(height: 12),
        FilledButton.icon(
          onPressed: () => permissions(context),
          icon: const Icon(Icons.link),
          label: const Text('Connect music apps'),
        ),
        const SizedBox(height: 24),
      ],
      if (model.players.isNotEmpty && !model.demo) ...[
        DropdownButtonFormField<String>(
          initialValue:
              model.preferred.isEmpty ||
                  model.players.any((p) => p['id'] == model.preferred)
              ? model.preferred
              : '',
          isExpanded: true,
          decoration: const InputDecoration(
            labelText: 'Music source',
            border: OutlineInputBorder(),
          ),
          items: [
            const DropdownMenuItem(
              value: '',
              child: Text('Auto · playing source'),
            ),
            ...model.players.map(
              (p) => DropdownMenuItem(
                value: p['id'] as String,
                child: Text(
                  p['name'] as String? ?? p['id'] as String,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ),
          ],
          onChanged: (v) {
            if (v != null) unawaited(model.select(v));
          },
        ),
        const SizedBox(height: 20),
      ],
      Row(
        children: [
          Container(
            width: 56,
            height: 56,
            clipBehavior: Clip.antiAlias,
            decoration: BoxDecoration(
              color: surface,
              borderRadius: BorderRadius.circular(10),
            ),
            child: model.artwork == null
                ? const Icon(Icons.music_note, color: accent)
                : Image.memory(
                    model.artwork!,
                    fit: BoxFit.cover,
                    errorBuilder: (_, _, _) => const Icon(Icons.music_note),
                  ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  model.title,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 19,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  model.artist,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: muted, height: 1.3),
                ),
              ],
            ),
          ),
        ],
      ),
      const SizedBox(height: 16),
      Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          IconButton(
            tooltip: 'Previous track',
            onPressed: model.can('canPrevious')
                ? () => model.command('previous')
                : null,
            icon: const Icon(Icons.skip_previous_rounded),
            iconSize: 30,
          ),
          const SizedBox(width: 20),
          IconButton.filled(
            tooltip: model.playing ? 'Pause' : 'Play',
            onPressed: model.can('canToggle')
                ? () => model.command('playPause')
                : null,
            icon: Icon(
              model.playing ? Icons.pause_rounded : Icons.play_arrow_rounded,
            ),
            iconSize: 32,
            padding: const EdgeInsets.all(14),
          ),
          const SizedBox(width: 20),
          IconButton(
            tooltip: 'Next track',
            onPressed: model.can('canNext')
                ? () => model.command('next')
                : null,
            icon: const Icon(Icons.skip_next_rounded),
            iconSize: 30,
          ),
        ],
      ),
      const SizedBox(height: 16),
      FilledButton.icon(
        onPressed: () => model.stage(true),
        icon: const Icon(Icons.fullscreen),
        label: const Text('Enter fullscreen'),
      ),
      const SizedBox(height: 8),
      OutlinedButton.icon(
        onPressed: () => model.showOverlay(!model.overlay),
        icon: Icon(
          model.overlay
              ? Icons.visibility_off_outlined
              : Icons.desktop_windows_outlined,
        ),
        label: Text(
          model.overlay
              ? 'Hide overlay'
              : model.isAndroid
              ? 'Show over other apps'
              : 'Desktop glow',
        ),
      ),
      if (!model.isAndroid)
        const Padding(
          padding: EdgeInsets.only(top: 8),
          child: Text(
            'Desktop glow is click-through. Ctrl + Alt + G returns to controls. Uses the current monitor.',
            style: TextStyle(fontSize: 12, color: muted, height: 1.5),
          ),
        ),
      const SizedBox(height: 24),
      _section('LYRIC STYLE'),
      const SizedBox(height: 12),
      Wrap(
        spacing: 8,
        runSpacing: 8,
        children: styles.entries
            .map(
              (s) => ChoiceChip(
                label: Text(s.value),
                selected: model.style == s.key,
                onSelected: (_) => model.change(() => model.style = s.key),
              ),
            )
            .toList(),
      ),
      const SizedBox(height: 20),
      _toggle(
        'Edge light',
        'Colors follow the album artwork',
        model.light,
        (v) => model.change(() => model.light = v),
      ),
      _toggle(
        'Lyrics',
        'Recent words and the current highlight',
        model.showLyrics,
        (v) => model.change(() => model.showLyrics = v),
      ),
      _slider(
        'Light intensity',
        model.intensity,
        0,
        1,
        '${(model.intensity * 100).round()}%',
        (v) => model.change(() => model.intensity = v),
      ),
      _slider(
        'Light width',
        model.width,
        8,
        100,
        '${model.width.round()}',
        (v) => model.change(() => model.width = v),
      ),
      _slider(
        'Lyric size',
        model.size,
        .5,
        2,
        '${model.size.toStringAsFixed(1)}×',
        (v) => model.change(() => model.size = v),
      ),
      _slider(
        'Timing offset',
        model.offset,
        -10,
        10,
        '${model.offset >= 0 ? '+' : ''}${model.offset.toStringAsFixed(1)}s',
        (v) => model.change(() => model.offset = v),
      ),
      const Text(
        'Positive offset advances lyrics. Line-only sources use estimated word timing.',
        style: TextStyle(color: muted, fontSize: 12, height: 1.5),
      ),
      const SizedBox(height: 12),
      _toggle(
        'Reduce motion',
        'Keep words steady and remove drift',
        model.reduceMotion,
        (v) => model.change(() => model.reduceMotion = v),
      ),
      const Divider(height: 32),
      _section('CONNECTION'),
      const SizedBox(height: 12),
      _toggle(
        'Demo',
        'Original lyrics · simulated reaction · no audio',
        model.demo,
        model.setDemo,
      ),
      const SizedBox(height: 8),
      OutlinedButton.icon(
        onPressed: () => capture(context),
        icon: Icon(
          model.capturing ? Icons.stop_circle_outlined : Icons.graphic_eq,
        ),
        label: Text(
          model.capturing ? 'Stop audio capture' : 'Enable audio reaction',
        ),
      ),
      const SizedBox(height: 8),
      Text(
        model.audioStatus,
        style: const TextStyle(color: muted, fontSize: 12, height: 1.5),
      ),
      const SizedBox(height: 12),
      Wrap(
        spacing: 8,
        runSpacing: 8,
        children: [
          OutlinedButton.icon(
            onPressed: model.demo || model.track.isEmpty || model.busy
                ? null
                : () => model.loadLyrics(retry: true),
            icon: const Icon(Icons.refresh, size: 18),
            label: const Text('Retry lyrics'),
          ),
          OutlinedButton.icon(
            onPressed: model.hasTrack ? () => import(context) : null,
            icon: const Icon(Icons.file_open_outlined, size: 18),
            label: const Text('Import lyrics'),
          ),
        ],
      ),
      const SizedBox(height: 16),
      Text(
        model.status,
        style: const TextStyle(color: muted, fontSize: 12, height: 1.5),
      ),
      if (model.error.isNotEmpty)
        Padding(
          padding: const EdgeInsets.only(top: 12),
          child: Text(
            model.error,
            style: const TextStyle(color: Color(0xFFF2A29A), height: 1.5),
          ),
        ),
      const SizedBox(height: 24),
      const Text(
        'Afterglow follows your player. No service login, audio uploads or account required.',
        style: TextStyle(color: muted, fontSize: 12, height: 1.5),
      ),
    ],
  );
  Widget _section(String label) => Text(
    label,
    style: const TextStyle(
      fontSize: 11,
      fontWeight: FontWeight.w600,
      color: muted,
      letterSpacing: 1.8,
    ),
  );
  Widget _toggle(
    String title,
    String subtitle,
    bool value,
    ValueChanged<bool> changed,
  ) => SwitchListTile.adaptive(
    contentPadding: EdgeInsets.zero,
    title: Text(title),
    subtitle: Text(
      subtitle,
      style: const TextStyle(fontSize: 12, color: muted),
    ),
    value: value,
    onChanged: changed,
  );
  Widget _slider(
    String label,
    double value,
    double min,
    double max,
    String display,
    ValueChanged<double> changed,
  ) => Padding(
    padding: const EdgeInsets.only(top: 12),
    child: Column(
      children: [
        Row(
          children: [
            Expanded(child: Text(label, style: const TextStyle(fontSize: 13))),
            Text(display, style: const TextStyle(color: accent, fontSize: 13)),
          ],
        ),
        Slider(
          value: value,
          min: min,
          max: max,
          label: display,
          onChanged: changed,
        ),
      ],
    ),
  );
}
