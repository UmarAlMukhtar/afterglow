#include "native_bridge.h"
#include <audioclient.h>
#include <mmdeviceapi.h>
#include <ksmedia.h>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Foundation.Collections.h>
#include <winrt/Windows.Media.Control.h>
#include <winrt/Windows.Storage.Streams.h>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstring>

using V = flutter::EncodableValue;
using M = flutter::EncodableMap;
using L = flutter::EncodableList;
using namespace winrt::Windows::Media::Control;
namespace {
double Now() { return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count(); }
std::string String(const M& m, const char* key) {
  auto it = m.find(V(key));
  if (it != m.end()) if (auto v = std::get_if<std::string>(&it->second)) return *v;
  return {};
}
void SleepUntil(std::atomic<bool>& stopped, int count) {
  for (int i = 0; i < count && !stopped; ++i) std::this_thread::sleep_for(std::chrono::milliseconds(20));
}
}

NativeBridge::NativeBridge(flutter::BinaryMessenger* messenger, HWND window) : window_(window) {
  channel_ = std::make_unique<flutter::MethodChannel<V>>(messenger, "afterglow/native", &flutter::StandardMethodCodec::GetInstance());
  channel_->SetMethodCallHandler([this](const flutter::MethodCall<V>& call, std::unique_ptr<flutter::MethodResult<V>> result) {
    const auto& method = call.method_name();
    auto args = call.arguments();
    if (method == "snapshot") {
      std::lock_guard<std::mutex> lock(mutex_);
      if (args) if (const auto* map = std::get_if<M>(args)) preferred_ = String(*map, "preferred");
      M track = track_;
      if (!track.empty() && std::get<bool>(track.at(V("playing")))) {
        auto p = std::get<double>(track.at(V("position")));
        auto rate = std::get<double>(track.at(V("speed")));
        track[V("position")] = V(p + std::max(0.0, Now() - sample_time_) * rate);
      }
      result->Success(V(M{{V("permission"), V(true)}, {V("players"), V(players_)}, {V("track"), V(track)},
        {V("capturing"), V(capture_.load())}, {V("overlay"), V(overlay_)}, {V("level"), V(level_)},
        {V("audioStatus"), V(audio_status_)}, {V("status"), V(media_status_)}}));
    } else if (method == "command") {
      if (args) if (const auto* map = std::get_if<M>(args)) {
        std::lock_guard<std::mutex> lock(mutex_);
        action_ = String(*map, "action"); action_player_ = String(*map, "player");
      }
      result->Success(V(true));
    } else if (method == "capture") {
      capture_ = args && std::holds_alternative<bool>(*args) && std::get<bool>(*args);
      result->Success(V(true));
    } else if (method == "fullscreen" || method == "overlay") {
      const bool enabled = args && std::holds_alternative<bool>(*args) && std::get<bool>(*args);
      if (method == "overlay" && enabled && !overlay_ && !RegisterHotKey(window_, 42, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 'G')) {
        result->Error("hotkey", "Ctrl + Alt + G is in use. Close the other hotkey owner or use fullscreen."); return;
      }
      Stage(enabled, method == "overlay" && enabled);
      result->Success(V(true));
    } else { result->NotImplemented(); }
  });
  media_thread_ = std::thread([this] { MediaLoop(); });
  audio_thread_ = std::thread([this] { AudioLoop(); });
}
NativeBridge::~NativeBridge() {
  channel_->SetMethodCallHandler(nullptr);
  stopped_ = true; capture_ = false;
  UnregisterHotKey(window_, 42);
  if (media_thread_.joinable()) media_thread_.join();
  if (audio_thread_.joinable()) audio_thread_.join();
}

void NativeBridge::MediaLoop() {
  winrt::init_apartment(winrt::apartment_type::multi_threaded);
  GlobalSystemMediaTransportControlsSessionManager manager{nullptr};
  std::string artwork_key;
  std::vector<uint8_t> artwork;
  while (!stopped_) {
    try {
      if (!manager) manager = GlobalSystemMediaTransportControlsSessionManager::RequestAsync().get();
      const auto sessions = manager.GetSessions();
      std::string preferred, action, action_player;
      { std::lock_guard<std::mutex> lock(mutex_); preferred = preferred_; action.swap(action_); action_player.swap(action_player_); }
      GlobalSystemMediaTransportControlsSession selected{nullptr};
      L players;
      for (const auto& session : sessions) {
        const auto id = winrt::to_string(session.SourceAppUserModelId());
        players.emplace_back(M{{V("id"), V(id)}, {V("name"), V(id)}});
        if (!preferred.empty()) { if (id == preferred) selected = session; }
        else if (!selected || (session.GetPlaybackInfo().PlaybackStatus() == GlobalSystemMediaTransportControlsSessionPlaybackStatus::Playing && selected.GetPlaybackInfo().PlaybackStatus() != GlobalSystemMediaTransportControlsSessionPlaybackStatus::Playing)) selected = session;
      }
      if (selected && !action.empty() && winrt::to_string(selected.SourceAppUserModelId()) == action_player) {
        const auto controls = selected.GetPlaybackInfo().Controls();
        if (action == "playPause" && controls.IsPlayPauseToggleEnabled()) selected.TryTogglePlayPauseAsync().get();
        else if (action == "next" && controls.IsNextEnabled()) selected.TrySkipNextAsync().get();
        else if (action == "previous" && controls.IsPreviousEnabled()) selected.TrySkipPreviousAsync().get();
      }
      M track;
      if (selected) {
        const auto props = selected.TryGetMediaPropertiesAsync().get();
        const auto playback = selected.GetPlaybackInfo();
        const auto timeline = selected.GetTimelineProperties();
        const auto controls = playback.Controls();
        const auto id = winrt::to_string(selected.SourceAppUserModelId());
        const auto title = winrt::to_string(props.Title());
        const auto artist = winrt::to_string(props.Artist());
        const auto playing = playback.PlaybackStatus() == GlobalSystemMediaTransportControlsSessionPlaybackStatus::Playing;
        double position = std::chrono::duration<double>(timeline.Position()).count();
        const auto rate = playback.PlaybackRate();
        const double speed = rate ? rate.Value() : 1.0;
        const double age = std::chrono::duration<double>(winrt::clock::now() - timeline.LastUpdatedTime()).count();
        if (playing && age >= 0 && age < 86400) position += age * speed;
        const auto art_key = id + "\n" + title + "\n" + artist;
        if (art_key != artwork_key) {
          artwork_key = art_key; artwork.clear();
          try {
            if (auto thumbnail = props.Thumbnail()) {
              const auto stream = thumbnail.OpenReadAsync().get();
              if (stream.Size() <= 2 * 1024 * 1024) {
                const auto count = static_cast<uint32_t>(stream.Size());
                const auto reader = winrt::Windows::Storage::Streams::DataReader(stream);
                reader.LoadAsync(count).get();
                artwork.resize(count); reader.ReadBytes(artwork);
              }
              stream.Close();
            }
          } catch (...) { artwork.clear(); }
        }
        track = {{V("player"), V(id)}, {V("title"), V(title)}, {V("artist"), V(artist)}, {V("album"), V(winrt::to_string(props.AlbumTitle()))},
          {V("position"), V(std::max(0.0, position))}, {V("duration"), V(std::max(0.0, std::chrono::duration<double>(timeline.EndTime() - timeline.StartTime()).count()))},
          {V("playing"), V(playing)}, {V("speed"), V(speed)}, {V("canToggle"), V(controls.IsPlayPauseToggleEnabled())},
          {V("canNext"), V(controls.IsNextEnabled())}, {V("canPrevious"), V(controls.IsPreviousEnabled())}, {V("artwork"), V(artwork)}};
      }
      { std::lock_guard<std::mutex> lock(mutex_); track_ = std::move(track); players_ = std::move(players); sample_time_ = Now();
        media_status_ = selected ? "Connected through Windows media controls" : "Start music in a player that publishes Windows media controls."; }
    } catch (const winrt::hresult_error&) {
      std::lock_guard<std::mutex> lock(mutex_); track_.clear(); players_.clear();
      media_status_ = "Windows media controls unavailable; retrying."; manager = nullptr;
    } catch (...) {
      std::lock_guard<std::mutex> lock(mutex_); track_.clear(); media_status_ = "Player disconnected; retrying.";
    }
    SleepUntil(stopped_, 20);
  }
  winrt::uninit_apartment();
}

void NativeBridge::AudioLoop() {
  winrt::init_apartment(winrt::apartment_type::multi_threaded);
  while (!stopped_) {
    if (!capture_) {
      { std::lock_guard<std::mutex> lock(mutex_); level_ = 0; audio_running_ = false; audio_status_ = "Audio capture is off"; }
      SleepUntil(stopped_, 5); continue;
    }
    try {
      winrt::com_ptr<IMMDeviceEnumerator> enumerator;
      winrt::check_hresult(CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL, IID_PPV_ARGS(enumerator.put())));
      winrt::com_ptr<IMMDevice> device;
      winrt::check_hresult(enumerator->GetDefaultAudioEndpoint(eRender, eMultimedia, device.put()));
      LPWSTR raw_id = nullptr; winrt::check_hresult(device->GetId(&raw_id));
      const std::wstring device_id(raw_id); CoTaskMemFree(raw_id);
      winrt::com_ptr<IAudioClient> audio;
      winrt::check_hresult(device->Activate(__uuidof(IAudioClient), CLSCTX_ALL, nullptr, audio.put_void()));
      WAVEFORMATEX* format = nullptr;
      winrt::check_hresult(audio->GetMixFormat(&format));
      const auto format_guard = std::unique_ptr<WAVEFORMATEX, decltype(&CoTaskMemFree)>(format, &CoTaskMemFree);
      bool floating = format->wFormatTag == WAVE_FORMAT_IEEE_FLOAT;
      if (format->wFormatTag == WAVE_FORMAT_EXTENSIBLE && format->cbSize >= 22) floating = reinterpret_cast<WAVEFORMATEXTENSIBLE*>(format)->SubFormat == KSDATAFORMAT_SUBTYPE_IEEE_FLOAT;
      if (!(floating && format->wBitsPerSample == 32) && format->wBitsPerSample != 16 && format->wBitsPerSample != 24 && format->wBitsPerSample != 32) throw std::runtime_error("Unsupported audio format");
      winrt::check_hresult(audio->Initialize(AUDCLNT_SHAREMODE_SHARED, AUDCLNT_STREAMFLAGS_LOOPBACK, 1000000, 0, format, nullptr));
      winrt::com_ptr<IAudioCaptureClient> capture;
      winrt::check_hresult(audio->GetService(IID_PPV_ARGS(capture.put())));
      winrt::check_hresult(audio->Start());
      { std::lock_guard<std::mutex> lock(mutex_); audio_running_ = true; audio_status_ = "WASAPI output loopback · in memory only"; }
      double checked = Now();
      while (capture_ && !stopped_) {
        UINT32 packet = 0; winrt::check_hresult(capture->GetNextPacketSize(&packet));
        double energy = 0; uint64_t count = 0;
        while (packet > 0) {
          BYTE* data = nullptr; UINT32 frames = 0; DWORD flags = 0;
          winrt::check_hresult(capture->GetBuffer(&data, &frames, &flags, nullptr, nullptr));
          const auto samples = frames * format->nChannels;
          if (!(flags & AUDCLNT_BUFFERFLAGS_SILENT)) {
            for (UINT32 i = 0; i < samples; ++i) {
              double value = 0;
              if (floating) value = reinterpret_cast<float*>(data)[i];
              else if (format->wBitsPerSample == 16) value = reinterpret_cast<int16_t*>(data)[i] / 32768.0;
              else if (format->wBitsPerSample == 32) value = reinterpret_cast<int32_t*>(data)[i] / 2147483648.0;
              else { const auto* b = data + i * 3; int32_t v = b[0] | (b[1] << 8) | (b[2] << 16); if (v & 0x800000) v |= static_cast<int32_t>(0xff000000); value = v / 8388608.0; }
              if (std::isfinite(value)) energy += value * value;
            }
          }
          count += samples;
          winrt::check_hresult(capture->ReleaseBuffer(frames));
          winrt::check_hresult(capture->GetNextPacketSize(&packet));
        }
        { std::lock_guard<std::mutex> lock(mutex_); level_ = count ? std::clamp(std::sqrt(energy / static_cast<double>(count)) * 5.0, 0.0, 1.0) : level_ * .9; }
        if (Now() - checked > 2) {
          checked = Now(); winrt::com_ptr<IMMDevice> current;
          winrt::check_hresult(enumerator->GetDefaultAudioEndpoint(eRender, eMultimedia, current.put()));
          LPWSTR new_id = nullptr; winrt::check_hresult(current->GetId(&new_id));
          const bool changed = device_id != new_id; CoTaskMemFree(new_id);
          if (changed) break;
        }
        SleepUntil(stopped_, 2);
      }
      audio->Stop();
    } catch (...) {
      { std::lock_guard<std::mutex> lock(mutex_); level_ = 0; audio_running_ = false; audio_status_ = "Output audio unavailable; retrying the default output device."; }
      SleepUntil(stopped_, 50);
    }
  }
  winrt::uninit_apartment();
}

void NativeBridge::Stage(bool fullscreen, bool overlay) {
  if (!fullscreen_ && fullscreen) {
    GetWindowPlacement(window_, &placement_);
    saved_style_ = GetWindowLongPtr(window_, GWL_STYLE);
    saved_ex_style_ = GetWindowLongPtr(window_, GWL_EXSTYLE);
  }
  if (fullscreen) {
    MONITORINFO monitor{sizeof(MONITORINFO)};
    GetMonitorInfo(MonitorFromWindow(window_, MONITOR_DEFAULTTONEAREST), &monitor);
    SetWindowLongPtr(window_, GWL_STYLE, saved_style_ & ~WS_OVERLAPPEDWINDOW);
    SetWindowLongPtr(window_, GWL_EXSTYLE, overlay ? saved_ex_style_ | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE : saved_ex_style_);
    if (overlay) SetLayeredWindowAttributes(window_, RGB(0, 0, 0), 255, LWA_COLORKEY);
    SetWindowPos(window_, overlay ? HWND_TOPMOST : HWND_TOP, monitor.rcMonitor.left, monitor.rcMonitor.top,
      monitor.rcMonitor.right - monitor.rcMonitor.left, monitor.rcMonitor.bottom - monitor.rcMonitor.top,
      SWP_FRAMECHANGED | (overlay ? SWP_NOACTIVATE : 0));
  } else if (fullscreen_) {
    SetWindowLongPtr(window_, GWL_STYLE, saved_style_);
    SetWindowLongPtr(window_, GWL_EXSTYLE, saved_ex_style_);
    SetWindowPos(window_, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_FRAMECHANGED);
    SetWindowPlacement(window_, &placement_); SetForegroundWindow(window_);
  }
  if (!overlay) UnregisterHotKey(window_, 42);
  fullscreen_ = fullscreen; overlay_ = overlay;
}
bool NativeBridge::HandleMessage(UINT message, WPARAM wparam) {
  if (message == WM_HOTKEY && wparam == 42) {
    Stage(false, false); channel_->InvokeMethod("exitStage", nullptr); return true;
  }
  return false;
}
