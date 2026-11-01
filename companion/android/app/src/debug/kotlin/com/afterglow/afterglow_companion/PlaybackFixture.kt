package com.afterglow.afterglow_companion

import android.app.Activity
import android.media.AudioAttributes
import android.media.MediaMetadata
import android.media.MediaPlayer
import android.media.session.MediaSession
import android.media.session.PlaybackState
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import java.io.File
import java.io.FileOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.sin

// Compiled only in debug builds. The tone is generated locally; no music or
// account is needed to exercise actual media sessions and playback capture.
class PlaybackFixture {
    companion object {
        private var player: MediaPlayer? = null
        private var session: MediaSession? = null
        private var track = 1
        private val handler = Handler(Looper.getMainLooper())
        private fun publish() {
            val audio = player ?: return
            session?.setMetadata(MediaMetadata.Builder().putString(MediaMetadata.METADATA_KEY_TITLE, "Afterglow test $track")
                .putString(MediaMetadata.METADATA_KEY_ARTIST, "Local verification fixture").putString(MediaMetadata.METADATA_KEY_ALBUM, "Afterglow tests")
                .putLong(MediaMetadata.METADATA_KEY_DURATION, 32000).build())
            session?.setPlaybackState(PlaybackState.Builder().setActions(PlaybackState.ACTION_PLAY or PlaybackState.ACTION_PAUSE or PlaybackState.ACTION_PLAY_PAUSE or PlaybackState.ACTION_SKIP_TO_NEXT or PlaybackState.ACTION_SKIP_TO_PREVIOUS or PlaybackState.ACTION_SEEK_TO)
                .setState(if (audio.isPlaying) PlaybackState.STATE_PLAYING else PlaybackState.STATE_PAUSED, audio.currentPosition.toLong(), 1f, SystemClock.elapsedRealtime()).build())
        }
        @JvmStatic fun control(activity: Activity, action: String) {
            if (action == "stop") { player?.release(); player = null; session?.release(); session = null; return }
            if (player != null) return
            val file = File(activity.cacheDir, "afterglow-test.wav")
            val rate = 44100; val length = rate * 32; val bytes = length * 2
            FileOutputStream(file).use { out ->
                val header = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
                header.put("RIFF".toByteArray()).putInt(36+bytes).put("WAVEfmt ".toByteArray()).putInt(16).putShort(1).putShort(1)
                    .putInt(rate).putInt(rate*2).putShort(2).putShort(16).put("data".toByteArray()).putInt(bytes)
                out.write(header.array())
                val block = ByteBuffer.allocate(bytes).order(ByteOrder.LITTLE_ENDIAN)
                for (i in 0 until length) block.putShort((sin(i * 2 * Math.PI * 220 / rate) * 3000 * (.5 + .5 * sin(i * 2 * Math.PI * 2 / rate))).toInt().toShort())
                out.write(block.array())
            }
            player = MediaPlayer().apply {
                setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).setAllowedCapturePolicy(AudioAttributes.ALLOW_CAPTURE_BY_ALL).build())
                setDataSource(file.path); isLooping = true; prepare(); setVolume(.15f, .15f); start()
            }
            session = MediaSession(activity, "Afterglow verification").apply {
                setCallback(object : MediaSession.Callback() {
                    override fun onPlay() { player?.start(); publish() }
                    override fun onPause() { player?.pause(); publish() }
                    override fun onSkipToNext() { track++; player?.seekTo(0); publish() }
                    override fun onSkipToPrevious() { track--; player?.seekTo(0); publish() }
                    override fun onSeekTo(pos: Long) { player?.seekTo(pos.toInt()); handler.postDelayed({ publish() }, 100) }
                }, handler)
                isActive = true
            }
            publish()
        }
    }
}
