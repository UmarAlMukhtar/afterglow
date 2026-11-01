package com.afterglow.afterglow_companion

import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.*
import android.os.Build
import android.os.IBinder
import android.provider.Settings
import android.view.View
import android.view.WindowManager

class GlowOverlay : Service() {
    companion object {
        @Volatile var running = false
        @Volatile var scene: Map<String, Any?> = emptyMap()
    }
    private var view: GlowView? = null
    override fun onBind(intent: Intent?): IBinder? = null
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == "stop" || !Settings.canDrawOverlays(this)) { stopSelf(); return START_NOT_STICKY }
        if (running) return START_NOT_STICKY
        val notification = serviceNotification(this, "Click-through light and lyrics · tap to return", GlowOverlay::class.java, 102)
        if (Build.VERSION.SDK_INT >= 34) startForeground(102, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        else startForeground(102, notification)
        try {
            val window = getSystemService(WINDOW_SERVICE) as WindowManager
            view = GlowView(this)
            window.addView(view, WindowManager.LayoutParams(WindowManager.LayoutParams.MATCH_PARENT, WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                PixelFormat.TRANSLUCENT).apply { alpha = .75f })
            running = true
        } catch (_: Exception) { stopSelf() }
        return START_NOT_STICKY
    }
    override fun onDestroy() {
        running = false
        view?.let { try { (getSystemService(WINDOW_SERVICE) as WindowManager).removeView(it) } catch (_: Exception) { } }
        view = null; scene = emptyMap(); super.onDestroy()
    }
    private class GlowView(context: Context) : View(context) {
        private val brush = Paint(Paint.ANTI_ALIAS_FLAG)
        private var smooth = 0f
        override fun onDraw(canvas: Canvas) {
            val data = scene
            val w = width.toFloat(); val h = height.toFloat()
            val demo = (data["demoLevel"] as? Number)?.toFloat() ?: -1f
            val target = if (demo >= 0) demo else PlaybackCapture.level.toFloat()
            smooth += (target - smooth) * .15f
            if (data["light"] != false) {
                val primary = (data["primary"] as? Number)?.toInt() ?: 0xffa9e5c2.toInt()
                val secondary = (data["secondary"] as? Number)?.toInt() ?: 0xffebae84.toInt()
                val intensity = ((data["intensity"] as? Number)?.toFloat() ?: .65f) * (.15f + smooth * .85f)
                val size = ((data["width"] as? Number)?.toFloat() ?: 36f) * resources.displayMetrics.density * 2
                for (side in 0..3) {
                    val color = if (side % 2 == 0) primary else secondary
                    val solid = (color and 0x00ffffff) or ((intensity * 255).toInt().coerceIn(0,255) shl 24)
                    val coords = when(side) { 0 -> floatArrayOf(0f,0f,size,0f); 1 -> floatArrayOf(w,0f,w-size,0f); 2 -> floatArrayOf(0f,0f,0f,size); else -> floatArrayOf(0f,h,0f,h-size) }
                    brush.shader = LinearGradient(coords[0],coords[1],coords[2],coords[3], solid, color and 0x00ffffff, Shader.TileMode.CLAMP)
                    when(side) { 0 -> canvas.drawRect(0f,0f,size,h,brush); 1 -> canvas.drawRect(w-size,0f,w,h,brush); 2 -> canvas.drawRect(0f,0f,w,size,brush); else -> canvas.drawRect(0f,h-size,w,h,brush) }
                }
            }
            brush.shader = null
            if (data["lyrics"] != false) {
                val elapsed = (android.os.SystemClock.elapsedRealtime() - ((data["stamp"] as? Number)?.toLong() ?: android.os.SystemClock.elapsedRealtime())).coerceAtLeast(0) / 1000.0
                var position = ((data["position"] as? Number)?.toDouble() ?: 0.0) + if (data["playing"] == true) elapsed * ((data["speed"] as? Number)?.toDouble() ?: 1.0) else 0.0
                if (data["demo"] == true) position %= 32.0
                val timeline = (data["timeline"] as? List<*>)?.mapNotNull { it as? List<*> } ?: emptyList()
                val at = timeline.indexOfLast { ((it.getOrNull(1) as? Number)?.toDouble() ?: Double.MAX_VALUE) <= position }
                val rows = if (at >= 0) timeline.subList(maxOf(0, at-2), at+1) else emptyList()
                val words = rows.map { it[0] as? String ?: "" }
                val active = at >= 0 && position < ((timeline[at].getOrNull(2) as? Number)?.toDouble() ?: 0.0)
                brush.typeface = Typeface.create("sans-serif", Typeface.BOLD)
                for ((i, text) in words.withIndex()) {
                    val current = i == words.lastIndex && active
                    brush.textSize = minOf(w * .18f, h * .12f) * ((data["size"] as? Number)?.toFloat() ?: 1f)
                    val measured = brush.measureText(text)
                    if (measured > w * .7f) brush.textSize *= w * .7f / measured
                    val textWidth = brush.measureText(text)
                    val y = h * .64f + (i - words.lastIndex) * brush.textSize * 1.2f
                    if (current) { brush.color = 0xffb6486c.toInt(); canvas.drawRoundRect((w-textWidth)/2-12,y+brush.fontMetrics.top-4,(w+textWidth)/2+12,y+brush.fontMetrics.bottom+4,4f,4f,brush) }
                    brush.color = if (current) Color.WHITE else 0xffc7839d.toInt()
                    canvas.drawText(text,(w-textWidth)/2,y,brush)
                }
            }
            if (running) postInvalidateDelayed(33)
        }
    }
}
