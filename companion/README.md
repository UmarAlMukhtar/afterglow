# Afterglow for Windows and Android

Shared Flutter UI, lyric parsers and providers, with small native adapters.
Flutter 3.44.9 / Dart 3.12.2, Android SDK 36, Android 10+ (API 29), and a
Windows C++20 toolchain with Windows SDK 10.0.26100 or later were used here.

```sh
flutter pub get
flutter analyze
flutter test
flutter run -d windows
flutter run -d <android-device-id>
flutter build windows --release
flutter build apk --release
```

Windows needs Visual Studio's Desktop development with C++ workload and a
Windows 10/11 SDK. The portable release includes all build output files;
`Afterglow.exe` alone is not a standalone bundle. The VC++ runtime is a
prerequisite. The application requires neither elevation nor autostart.

Android release builds require `android/key.properties` (gitignored):

```properties
storeFile=/absolute/path/to/private/afterglow-release.jks
storePassword=YOUR_PRIVATE_PASSWORD
keyAlias=afterglow
keyPassword=YOUR_PRIVATE_PASSWORD
```

Use your own release key, and keep that key and its password backed up privately.
Future updates must use the same key. The build refuses to sign a release using
the debug key. Local signing material is never included in commits or release
assets. Debug builds work without `key.properties`. The published APK is signed
with the project's local release key; no Play Store provisioning is configured.

## Implementation

- `lib/lyrics.dart`: bounded enhanced LRC / TTML parsing, genuine versus estimated
  timing, AMLL by exposed Spotify ID, and LRCLIB by metadata.
- `lib/model.dart`: monotonic playback timeline, stale-request protection,
  per-song imports, a 500-document cache, saved preferences, artwork colors and
  the native channel. OS capture permissions are never saved as consent.
- `lib/stage.dart`: 30 fps shaped word wall, inertial movement, reduced motion,
  a cylindrical lens, symbol variants, and audio-reactive edge gradients.
- `windows/runner/native_bridge.*`: background GSMTC media polling and command
  capability checks, WASAPI output-loopback RMS, output-device reconnect, and
  window modes. `Ctrl+Alt+G` restores click-through desktop mode; conflicts
  refuse activation so the user always has a recovery shortcut.
- Android `MediaAccess`: notification-listener identity for active media sessions;
  no notification callback reads message text.
- Android `PlaybackCapture`: user-consented MediaProjection foreground service
  and AudioPlaybackCaptureConfiguration. No mic source, video surface, recording
  file or upload. Players can block playback capture. Its notification can stop it.
- Android `GlowOverlay`: native click-through overlay with a simpler word stack,
  foreground notification and Stop action. It interpolates the lyric timeline
  independently when the app is behind another window. Opacity is capped below
  Android's untrusted-touch obscuration threshold. Full lyric styles remain in
  the Flutter stage.

Notification access and Appear on top are optional system permissions and can be
revoked in Settings. Capture must be explicitly restarted after consent ends.
Services do not start on boot and stop on a normal app exit. None of these modes
is a secure lock screen. The fullscreen stage keeps the Android screen awake
while it is open.

The Windows adapter receives the title / artist / timeline exposed by each
player. Windows GSMTC does not supply the Spotify track ID in this adapter, so
metadata-based LRCLIB / imports are used there. Windows/Android do not host the
optional Python Spicetify lyric receiver. Service account login and subscriptions
stay entirely in the user's music app.

## Native end-to-end tests

Unit / widget tests cover parser boundaries, gaps, estimated timing, provider
fallback, pause, layouts at 375 / 768 / 1280 / 1440 widths and landscape,
large text, reduced motion, all five styles and fullscreen return.

```sh
flutter test integration_test/device_test.dart -d <android-device-id>
flutter test integration_test/device_test.dart -d windows
```

The device test uses actual native media sessions and generated local audio.
Android's fixture is under `android/app/src/debug/` and is excluded from release
builds. Enable media access, accept audio capture and enable Appear on top in the
system UI when the test requests them. Do not run this test during a call or
while using another player: it intentionally exercises transport and local audio.

On Windows, first build `../tools/windows_fixture.cpp` with
`../tools/build_windows_fixture.ps1 -OutputDirectory <scratch-folder>`, then run
the resulting executable with the generated WAV's `file:///` URI. It registers
its own controlled Windows media session for the test. No streaming account or
third-party recording is used. The fixture exits after ten minutes and is never
included in release assets.

After building both release targets, run `tools/package_release.ps1` from the
repository root, supplying an output folder. It creates a portable Windows ZIP,
signed Android APK, runnable Linux source archive and SHA-256 checksums from the
current commit. The GitHub CI separately checks Linux and builds both new targets.

Native API references: [Windows media sessions](https://learn.microsoft.com/en-us/uwp/api/windows.media.control.globalsystemmediatransportcontrolssessionmanager),
[WASAPI loopback](https://learn.microsoft.com/en-us/windows/win32/coreaudio/loopback-recording),
[Android playback capture](https://developer.android.com/media/platform/av-capture),
[Flutter platform channels](https://docs.flutter.dev/platform-integration/platform-channels).
