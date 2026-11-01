# Afterglow 0.2.0 verification

Verified on 2026-11-01. Repository renamed from `afterglow-linux` to `afterglow`.

| Check | Evidence / result |
|---|---|
| Flutter analysis | No issues found |
| Dart tests | 16 tests passed: bounded LRC / TTML, exact versus estimated timing, gaps, offsets, provider failure / fallback, pause and responsive layouts |
| Layout coverage | 375×812, 812×375, 768×1024, 1280×720 and 1440×900; large text and reduced motion; all five lyric treatments and fullscreen return |
| Windows native build | Release x64 `Afterglow.exe`, built on Windows 11 with Visual Studio 2026 and C++20 |
| Windows native integration | `flutter test integration_test/device_test.dart -d windows`: passed. Actual generated-audio Windows media session; pause/resume, previous/next, import, fullscreen, overlay and nonzero WASAPI output-loopback reaction; capture stopped afterward |
| Windows UI | Native window inspected with controls, preview, style choices and accessibility names. Further computer-use testing stopped when Escape was pressed |
| Android native build | Signed universal release APK, 0.2.0 (version code 2), min API 29 / target API 36; APK signature verified with `apksigner` |
| Android release contents | Manifest checked: capture and overlay services present; no debuggable flag or debug playback-fixture service |
| USB phone | Samsung SM-A156E / Galaxy A15, Android 16, connected through authorized ADB. Debug app installed and rendered; demo, style switching, pause, import, fullscreen and return reached the fixture phase without assertion failures |
| Remaining phone checks | Notification permission, actual external media controls, playback-capture level and native overlay test were interrupted. Physical-phone testing was deferred at the user's request; these are **not claimed as passed** |
| Linux regression | 37 Python tests passed in Ubuntu CI; MPRIS discovery, capabilities, pause, changes, disconnect/reconnect passed |
| Linux desktop regression | GTK demo clock, pause, offset, click-through input shape, desktop/fullscreen, controls recovery and worker cleanup passed under Xvfb + picom |
| Spotify extension | Existing extension sandbox self-check passed |

Linux CI evidence: [platform checks](https://github.com/UmarAlMukhtar/afterglow/actions/runs/41272722172).
This is a virtual X11 check, not a new test of the user's physical Linux partition.

## Distribution limits

- Windows is a portable x64 ZIP and requires the Microsoft Visual C++ runtime.
  The executable is not Authenticode signed. Keep the included DLLs and data folder.
- Android is a signed sideload APK. Release signing material is private and is
  excluded from Git and release assets. No Play Store listing is configured.
- Android players may prohibit playback capture; no microphone fallback exists.
  The system overlay uses a simpler native lyric stack than the Flutter stage.
- Linux remains the Python / GTK X11 app and is distributed as runnable source
  with documented system-package prerequisites.
- Windows/Android fisheye is an independent Flutter cylindrical text treatment,
  not a port of the existing Linux OpenGL mesh renderer. The optional Spicetify
  receiver remains Linux-specific. iOS and macOS are outside this release.
