#pragma once
#include <flutter/method_channel.h>
#include <flutter/standard_method_codec.h>
#include <windows.h>
#include <atomic>
#include <memory>
#include <mutex>
#include <string>
#include <thread>

class NativeBridge {
 public:
  NativeBridge(flutter::BinaryMessenger* messenger, HWND window);
  ~NativeBridge();
  bool HandleMessage(UINT message, WPARAM wparam);
 private:
  void MediaLoop();
  void AudioLoop();
  void Stage(bool fullscreen, bool overlay);
  HWND window_;
  std::unique_ptr<flutter::MethodChannel<flutter::EncodableValue>> channel_;
  std::atomic<bool> stopped_{false}, capture_{false};
  std::thread media_thread_, audio_thread_;
  std::mutex mutex_;
  flutter::EncodableMap track_;
  flutter::EncodableList players_;
  std::string preferred_, action_, action_player_, media_status_, audio_status_ = "Audio capture is off";
  double sample_time_ = 0, level_ = 0;
  bool audio_running_ = false, fullscreen_ = false, overlay_ = false;
  LONG_PTR saved_style_ = 0, saved_ex_style_ = 0;
  WINDOWPLACEMENT placement_{sizeof(WINDOWPLACEMENT)};
};
