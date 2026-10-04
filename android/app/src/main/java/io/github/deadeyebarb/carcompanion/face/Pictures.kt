package io.github.deadeyebarb.carcompanion.face

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import java.net.URLEncoder
import java.util.concurrent.ConcurrentHashMap

/**
 * The board's place pictures (images/) and clips (clips/), loaded over HTTP
 * from its page when a scene shows one. [version] goes up when one arrives or
 * they are all forgotten, so the display draws again.
 */
class Pictures(private val http: OkHttpClient, private val scope: CoroutineScope) : Panel.Pictures {
    @Volatile var base: String? = null  // e.g. "http://10.0.0.1:7000"
    private val sheets = ConcurrentHashMap<String, Panel.Sheet>()
    private val loading = ConcurrentHashMap.newKeySet<String>()
    private val failedAt = ConcurrentHashMap<String, Long>()  // not there: ask again after RETRY_MS
    private val _version = MutableStateFlow(0)
    val version: StateFlow<Int> = _version

    override fun image(name: String) = get("images", name)
    override fun clip(file: String) = get("clips", file)

    /** Pictures or clips were added or replaced on the board. */
    fun forget() {
        sheets.clear()
        failedAt.clear()
        _version.value++
    }

    private fun get(folder: String, name: String): Panel.Sheet? {
        val key = "$folder/$name"
        sheets[key]?.let { return it }
        val base = base ?: return null
        if (System.currentTimeMillis() - (failedAt[key] ?: 0) < RETRY_MS) return null
        if (loading.add(key)) scope.launch(Dispatchers.IO) {
            try {
                val url = "$base/$folder/${URLEncoder.encode(name, "UTF-8").replace("+", "%20")}?v=${System.currentTimeMillis()}"
                http.newCall(Request.Builder().url(url).build()).execute().use { response ->
                    val bitmap = response.body.byteStream().use { BitmapFactory.decodeStream(it) }
                    if (response.isSuccessful && bitmap != null) {
                        sheets[key] = if (folder == "images") sheet(Bitmap.createScaledBitmap(bitmap, 128, 128, true))
                        else sheet(bitmap)
                        _version.value++
                    } else failedAt[key] = System.currentTimeMillis()
                }
            } catch (_: Exception) {
                failedAt[key] = System.currentTimeMillis()  // not there (yet), or no connection
            } finally {
                loading.remove(key)
            }
        }
        return null
    }

    private companion object {
        const val RETRY_MS = 10_000L
    }

    private fun sheet(bitmap: Bitmap): Panel.Sheet {
        val pixels = IntArray(bitmap.width * bitmap.height)
        bitmap.getPixels(pixels, 0, bitmap.width, 0, 0, bitmap.width, bitmap.height)
        return Panel.Sheet(bitmap.width, bitmap.height, pixels)
    }
}
