package com.afterglow.afterglow_companion

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.media.MediaMetadata
import android.media.session.MediaController
import android.media.session.MediaSessionManager
import android.media.session.PlaybackState
import android.os.SystemClock
import android.provider.Settings
import android.service.notification.NotificationListenerService
import java.io.ByteArrayOutputStream

// Notification bodies are deliberately never read, retained or forwarded.
class MediaAccess : NotificationListenerService()

fun mediaPermission(context: Context): Boolean {
    val enabled = Settings.Secure.getString(context.contentResolver, "enabled_notification_listeners") ?: ""
    return enabled.split(':').mapNotNull { ComponentName.unflattenFromString(it) }
        .any { it == ComponentName(context, MediaAccess::class.java) }
}

fun sessions(context: Context): List<MediaController> = try {
    if (mediaPermission(context)) (context.getSystemService(Context.MEDIA_SESSION_SERVICE) as MediaSessionManager)
        .getActiveSessions(ComponentName(context, MediaAccess::class.java)) else emptyList()
} catch (_: SecurityException) { emptyList() }

class MediaSnapshot(private val context: Context) {
    private var artKey = ""
    private var artBytes: ByteArray? = null
    fun snapshot(preferred: String): Map<String, Any?> {
        val controllers = sessions(context)
        val current = if (preferred.isNotEmpty()) controllers.firstOrNull { it.packageName == preferred }
            else controllers.firstOrNull { it.playbackState?.state == PlaybackState.STATE_PLAYING } ?: controllers.firstOrNull()
        val players = controllers.distinctBy { it.packageName }.map {
            val name = try { context.packageManager.getApplicationLabel(context.packageManager.getApplicationInfo(it.packageName, 0)).toString() } catch (_: Exception) { it.packageName }
            mapOf("id" to it.packageName, "name" to name)
        }
        var track: Map<String, Any?>? = null
        if (current != null) {
            val meta = current.metadata
            val state = current.playbackState
            val playing = state?.state == PlaybackState.STATE_PLAYING
            val title = meta?.getString(MediaMetadata.METADATA_KEY_TITLE) ?: meta?.getString(MediaMetadata.METADATA_KEY_DISPLAY_TITLE) ?: "Unknown track"
            val artist = meta?.getString(MediaMetadata.METADATA_KEY_ARTIST) ?: ""
            val nextKey = "${current.packageName}\n$title\n$artist"
            if (nextKey != artKey) {
                artKey = nextKey
                artBytes = try {
                    val bitmap = meta?.getBitmap(MediaMetadata.METADATA_KEY_ALBUM_ART) ?: meta?.getBitmap(MediaMetadata.METADATA_KEY_ART) ?: meta?.getBitmap(MediaMetadata.METADATA_KEY_DISPLAY_ICON)
                    bitmap?.let {
                        val scaled = Bitmap.createScaledBitmap(it, 256, 256, true)
                        val output = ByteArrayOutputStream()
                        scaled.compress(Bitmap.CompressFormat.JPEG, 85, output)
                        if (scaled !== it) scaled.recycle()
                        output.toByteArray()
                    }
                } catch (_: Exception) { null }
            }
            var position = (state?.position ?: 0).coerceAtLeast(0) / 1000.0
            val speed = state?.playbackSpeed?.toDouble() ?: 1.0
            if (playing && state != null && state.lastPositionUpdateTime > 0) {
                position += (SystemClock.elapsedRealtime() - state.lastPositionUpdateTime).coerceAtLeast(0) / 1000.0 * speed
            }
            val actions = state?.actions ?: 0
            val canToggle = actions and PlaybackState.ACTION_PLAY_PAUSE != 0L || actions and (if (playing) PlaybackState.ACTION_PAUSE else PlaybackState.ACTION_PLAY) != 0L
            track = mapOf("player" to current.packageName, "title" to title, "artist" to artist,
                "album" to (meta?.getString(MediaMetadata.METADATA_KEY_ALBUM) ?: ""),
                "duration" to ((meta?.getLong(MediaMetadata.METADATA_KEY_DURATION) ?: 0) / 1000.0),
                "position" to position, "speed" to speed, "playing" to playing,
                "trackUrl" to (meta?.getString(MediaMetadata.METADATA_KEY_MEDIA_URI) ?: ""),
                "canToggle" to canToggle, "canNext" to (actions and PlaybackState.ACTION_SKIP_TO_NEXT != 0L),
                "canPrevious" to (actions and PlaybackState.ACTION_SKIP_TO_PREVIOUS != 0L), "artwork" to artBytes)
        }
        return mapOf("permission" to mediaPermission(context), "players" to players, "track" to track,
            "capturing" to PlaybackCapture.running, "level" to PlaybackCapture.level,
            "audioStatus" to PlaybackCapture.status, "overlay" to GlowOverlay.running,
            "status" to if (!mediaPermission(context)) "Connect music apps to follow their media controls."
                else if (current == null) "Start music in Spotify or another player with Android media controls."
                else "Connected to ${current.packageName}")
    }
    fun command(player: String, action: String) {
        val current = sessions(context).firstOrNull { it.packageName == player } ?: return
        val state = current.playbackState ?: return
        val flags = state.actions
        when (action) {
            "playPause" -> if (state.state == PlaybackState.STATE_PLAYING) {
                if (flags and (PlaybackState.ACTION_PAUSE or PlaybackState.ACTION_PLAY_PAUSE) != 0L) current.transportControls.pause()
            } else if (flags and (PlaybackState.ACTION_PLAY or PlaybackState.ACTION_PLAY_PAUSE) != 0L) current.transportControls.play()
            "next" -> if (flags and PlaybackState.ACTION_SKIP_TO_NEXT != 0L) current.transportControls.skipToNext()
            "previous" -> if (flags and PlaybackState.ACTION_SKIP_TO_PREVIOUS != 0L) current.transportControls.skipToPrevious()
        }
    }
}

fun serviceNotification(context: Context, text: String, service: Class<*>, id: Int): android.app.Notification {
    val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
    manager.createNotificationChannel(NotificationChannel("afterglow", "Afterglow visual services", NotificationManager.IMPORTANCE_LOW))
    val open = PendingIntent.getActivity(context, id, Intent(context, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    val stop = PendingIntent.getService(context, id, Intent(context, service).setAction("stop"), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    return android.app.Notification.Builder(context, "afterglow").setSmallIcon(R.drawable.ic_afterglow)
        .setContentTitle("Afterglow").setContentText(text).setContentIntent(open).setOngoing(true)
        .addAction(android.app.Notification.Action.Builder(null, "Stop", stop).build()).build()
}
