# Afterglow 0.2.0 — Linux, Windows and Android

Afterglow now includes a shared Flutter companion for Windows and Android,
alongside the original native GTK Linux edition. The repository is now named
`afterglow`.

## Downloads

- **Windows x64:** extract `afterglow-0.2.0-windows-x64.zip` and run `Afterglow.exe`.
  Keep every DLL and the `data` folder. Requires Windows 10 1809+ / Windows 11
  and the Microsoft Visual C++ 2015–2022 x64 runtime.
- **Android 10+:** sideload `afterglow-0.2.0-android.apk`. This is a signed release
  APK supporting ARM64, ARMv7 and x64, not a Play Store listing.
- **Linux X11:** extract `afterglow-0.2.0-linux.tar.gz`, install the README's GTK /
  PulseAudio dependencies and run `./afterglow-linux`. This is a runnable source
  distribution, not an AppImage or RPM.
- Check downloads against `SHA256SUMS.txt`.

## Added

- Windows system media sessions, transport controls, WASAPI output audio
  analysis, album colors, fullscreen and click-through desktop glow.
- Android media-session access, consent-based playback-audio analysis,
  fullscreen and an optional native overlay with a persistent Stop action.
- LRC / enhanced LRC and TTML import, AMLL / LRCLIB lookup, per-song imports,
  a bounded local cache, timing offset and saved preferences.
- Ship, Fisheye, Fisheye Visual, Visual and Lines treatments in the Flutter stage,
  original demo lyrics, simulated demo reaction and reduced motion.
- Platform CI and reproducible release packaging.

## Testing and limits

Windows native end-to-end checks passed on the development PC, including actual
output audio. All 16 Dart tests and 37 Linux regression tests passed; Linux MPRIS
and virtual desktop checks passed too. Android was installed and its demo UI
exercised on a USB-connected Galaxy A15. Full phone media/capture/overlay checks
were deferred at the user's request and remain unverified on that hardware.
See [the verification record](https://github.com/UmarAlMukhtar/afterglow/blob/main/docs/verification-0.2.0.md).

Android players can block playback capture. The native Android overlay is a
simpler word stack; full treatments are inside the app. Windows color-key overlay
edges and Flutter fisheye differ from the Linux OpenGL implementation. The optional
Spicetify lyric receiver remains Linux-specific. iOS and macOS are not included.

No microphone source, audio/video recording file, audio upload, account login or
telemetry is used. Online lyric lookup sends song metadata to the documented
providers. Android notification access is an optional broad OS permission used
only for active media sessions. Windows binaries are not Authenticode signed.
