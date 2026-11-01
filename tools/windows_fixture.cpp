// Local, generated-tone fixture. Never ship this executable in the app bundle.
#include <windows.h>
#include <shobjidl.h>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Media.h>
#include <winrt/Windows.Media.Core.h>
#include <winrt/Windows.Media.Playback.h>
#include <chrono>
#include <iostream>
#include <thread>

using namespace winrt::Windows::Media;
using namespace winrt::Windows::Media::Core;
using namespace winrt::Windows::Media::Playback;
int wmain(int argc, wchar_t** argv) {
  if (argc != 2) return 1;
  winrt::init_apartment(winrt::apartment_type::multi_threaded);
  SetCurrentProcessExplicitAppUserModelID(L"Afterglow.TestFixture");
  MediaPlayer player;
  player.CommandManager().IsEnabled(false);
  player.Source(MediaSource::CreateFromUri(winrt::Windows::Foundation::Uri(argv[1])));
  player.IsLoopingEnabled(true); player.Volume(.15);
  auto controls = player.SystemMediaTransportControls();
  controls.IsEnabled(true); controls.IsPlayEnabled(true); controls.IsPauseEnabled(true);
  controls.IsNextEnabled(true); controls.IsPreviousEnabled(true);
  int track = 1;
  auto publish = [&] {
    auto updater = controls.DisplayUpdater(); updater.Type(MediaPlaybackType::Music);
    updater.MusicProperties().Title(L"Afterglow test " + std::to_wstring(track));
    updater.MusicProperties().Artist(L"Local verification fixture");
    updater.MusicProperties().AlbumTitle(L"Afterglow tests"); updater.Update();
  };
  controls.ButtonPressed([&](auto&&, auto&& e) {
    switch (e.Button()) {
      case SystemMediaTransportControlsButton::Play: player.Play(); break;
      case SystemMediaTransportControlsButton::Pause: player.Pause(); break;
      case SystemMediaTransportControlsButton::Next: ++track; player.PlaybackSession().Position(std::chrono::seconds(0)); publish(); break;
      case SystemMediaTransportControlsButton::Previous: --track; player.PlaybackSession().Position(std::chrono::seconds(0)); publish(); break;
      default: break;
    }
  });
  publish(); player.Play();
  std::cout << "Afterglow fixture running for 10 minutes\n";
  for (int i = 0; i < 6000; ++i) {
    auto session = player.PlaybackSession();
    controls.PlaybackStatus(session.PlaybackState() == MediaPlaybackState::Playing ? MediaPlaybackStatus::Playing : MediaPlaybackStatus::Paused);
    SystemMediaTransportControlsTimelineProperties timeline;
    timeline.StartTime(std::chrono::seconds(0)); timeline.EndTime(std::chrono::seconds(32));
    timeline.MinSeekTime(std::chrono::seconds(0)); timeline.MaxSeekTime(std::chrono::seconds(32));
    timeline.Position(session.Position()); controls.UpdateTimelineProperties(timeline);
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
  }
  player.Close();
}
