package com.afterglow.afterglow_companion

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.media.projection.MediaProjectionManager
import android.net.Uri
import android.os.Build
import android.provider.Settings
import android.view.WindowManager
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private lateinit var snapshot: MediaSnapshot
    private var pendingCapture: MethodChannel.Result? = null
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        snapshot = MediaSnapshot(this)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "afterglow/native").setMethodCallHandler { call, result ->
            try {
                when (call.method) {
                    "snapshot" -> result.success(snapshot.snapshot(call.argument<String>("preferred") ?: ""))
                    "permissions" -> { startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)); result.success(true) }
                    "command" -> { snapshot.command(call.argument<String>("player") ?: "", call.argument<String>("action") ?: ""); result.success(true) }
                    "capture" -> {
                        if (call.arguments == false) { stopService(Intent(this, PlaybackCapture::class.java)); result.success(true) }
                        else if (pendingCapture != null) result.error("pending", "A capture request is already open.", null)
                        else { pendingCapture = result; requestCapture() }
                    }
                    "overlay" -> {
                        if (call.arguments == false) { stopService(Intent(this, GlowOverlay::class.java)); result.success(true) }
                        else if (!Settings.canDrawOverlays(this)) {
                            startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")))
                            result.error("permission", "Enable “Appear on top” for Afterglow, return here, then tap Show over other apps again.", null)
                        } else { startForegroundService(Intent(this, GlowOverlay::class.java)); result.success(true) }
                    }
                    "present" -> {
                        @Suppress("UNCHECKED_CAST") val data = call.arguments as? Map<String, Any?>
                        GlowOverlay.scene = (data ?: emptyMap()) + ("stamp" to android.os.SystemClock.elapsedRealtime())
                        result.success(true)
                    }
                    "fullscreen" -> {
                        if (call.arguments == true) window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                        else window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                        result.success(true)
                    }
                    "debugFixture" -> {
                        if (applicationInfo.flags and android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE == 0) result.notImplemented()
                        else {
                            val cls = Class.forName("$packageName.PlaybackFixture")
                            val action = call.arguments as? String ?: "start"
                            cls.getMethod("control", Activity::class.java, String::class.java).invoke(null, this, action)
                            result.success(true)
                        }
                    }
                    "debugStats" -> result.success(mapOf("peak" to PlaybackCapture.peak))
                    else -> result.notImplemented()
                }
            } catch (e: Exception) { result.error("native", e.message ?: "Native operation failed", null) }
        }
    }
    private fun requestCapture() {
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            val permissions = mutableListOf(Manifest.permission.RECORD_AUDIO)
            if (Build.VERSION.SDK_INT >= 33) permissions.add(Manifest.permission.POST_NOTIFICATIONS)
            requestPermissions(permissions.toTypedArray(), 91)
        } else launchCaptureConsent()
    }
    private fun launchCaptureConsent() {
        val manager = getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        startActivityForResult(manager.createScreenCaptureIntent(), 92)
    }
    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 91) {
            if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) launchCaptureConsent()
            else { pendingCapture?.error("permission", "Playback audio permission was declined.", null); pendingCapture = null }
        }
    }
    @Suppress("DEPRECATION")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == 92) {
            if (resultCode == RESULT_OK && data != null) {
                startForegroundService(Intent(this, PlaybackCapture::class.java).putExtra("data", data))
                pendingCapture?.success(true)
            } else pendingCapture?.error("consent", "Playback capture was cancelled.", null)
            pendingCapture = null
        }
    }
    override fun onDestroy() {
        pendingCapture?.error("closed", "Activity closed during capture request.", null); pendingCapture = null
        if (isFinishing) {
            stopService(Intent(this, PlaybackCapture::class.java))
            stopService(Intent(this, GlowOverlay::class.java))
        }
        super.onDestroy()
    }
}
