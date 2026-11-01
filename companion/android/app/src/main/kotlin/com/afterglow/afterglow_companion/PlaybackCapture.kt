package com.afterglow.afterglow_companion

import android.app.Activity
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioPlaybackCaptureConfiguration
import android.media.AudioRecord
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import kotlin.math.sqrt

class PlaybackCapture : Service() {
    companion object {
        @Volatile var running = false
        @Volatile var level = 0.0
        @Volatile var peak = 0.0
        @Volatile var status = "Audio capture is off"
    }
    private var projection: MediaProjection? = null
    private var recorder: AudioRecord? = null
    private var worker: Thread? = null
    private val callback = object : MediaProjection.Callback() {
        override fun onStop() { status = "Capture permission ended. Enable audio reaction to reconnect."; stopSelf() }
    }
    override fun onBind(intent: Intent?): IBinder? = null
    @Suppress("DEPRECATION")
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == "stop") { stopSelf(); return START_NOT_STICKY }
        if (running) return START_NOT_STICKY
        val data = intent?.getParcelableExtra<Intent>("data")
        if (data == null) { stopSelf(); return START_NOT_STICKY }
        startForeground(101, serviceNotification(this, "Analyzing eligible playback audio · nothing is saved", PlaybackCapture::class.java, 101), ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION)
        try {
            val manager = getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
            projection = manager.getMediaProjection(Activity.RESULT_OK, data)
            projection!!.registerCallback(callback, Handler(Looper.getMainLooper()))
            val config = AudioPlaybackCaptureConfiguration.Builder(projection!!)
                .addMatchingUsage(AudioAttributes.USAGE_MEDIA).addMatchingUsage(AudioAttributes.USAGE_GAME).addMatchingUsage(AudioAttributes.USAGE_UNKNOWN).build()
            val format = AudioFormat.Builder().setEncoding(AudioFormat.ENCODING_PCM_16BIT).setSampleRate(44100).setChannelMask(AudioFormat.CHANNEL_IN_STEREO).build()
            val min = AudioRecord.getMinBufferSize(44100, AudioFormat.CHANNEL_IN_STEREO, AudioFormat.ENCODING_PCM_16BIT)
            val audio = AudioRecord.Builder().setAudioFormat(format).setBufferSizeInBytes(min.coerceAtLeast(16384))
                .setAudioPlaybackCaptureConfig(config).build()
            // No setAudioSource() call: this records the playback mix, never the mic.
            recorder = audio
            audio.startRecording()
            running = true; peak = 0.0
            status = "Playback capture active · silence may mean the player blocks capture"
            worker = Thread({
                val samples = ShortArray(4096)
                try {
                    while (running) {
                        val count = audio.read(samples, 0, samples.size)
                        if (count < 0) throw IllegalStateException("Playback capture interrupted")
                        if (count == 0) continue
                        var energy = 0.0
                        for (i in 0 until count) { val v = samples[i] / 32768.0; energy += v * v }
                        level = (sqrt(energy / count) * 5).coerceIn(0.0, 1.0)
                        peak = maxOf(peak, level)
                    }
                } catch (_: Exception) {
                    if (running) { status = "Playback capture interrupted. Re-enable to reconnect."; Handler(Looper.getMainLooper()).post { stopSelf() } }
                } finally { audio.release() }
            }, "afterglow-playback").also { it.start() }
        } catch (_: Exception) {
            status = "Playback capture could not start. Check system consent and audio permission."; stopSelf()
        }
        return START_NOT_STICKY
    }
    override fun onDestroy() {
        running = false; level = 0.0
        try { recorder?.stop() } catch (_: Exception) { }
        if (worker == null) recorder?.release()
        recorder = null
        projection?.unregisterCallback(callback)
        projection?.stop(); projection = null
        if (status.startsWith("Playback capture active")) status = "Audio capture is off"
        super.onDestroy()
    }
}
