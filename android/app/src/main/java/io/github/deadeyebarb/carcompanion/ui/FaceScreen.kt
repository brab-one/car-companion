package io.github.deadeyebarb.carcompanion.ui

import android.graphics.Bitmap
import androidx.compose.foundation.Image
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AssistChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.FilterQuality
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.deadeyebarb.carcompanion.Companion
import io.github.deadeyebarb.carcompanion.arr
import io.github.deadeyebarb.carcompanion.bool
import io.github.deadeyebarb.carcompanion.face.Panel
import io.github.deadeyebarb.carcompanion.num
import io.github.deadeyebarb.carcompanion.obj
import io.github.deadeyebarb.carcompanion.str
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlin.math.roundToInt

/** His face as on the board's display, what he is doing, and the car. */
@Composable
fun FaceScreen(companion: Companion, modifier: Modifier = Modifier) {
    val scene by companion.scene.collectAsStateWithLifecycle()
    val status by companion.status.collectAsStateWithLifecycle()
    val car by companion.car.collectAsStateWithLifecycle()
    val config by companion.config.collectAsStateWithLifecycle()

    Column(
        modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        ConnectionLine(companion)
        Spacer(Modifier.height(12.dp))
        Displays(companion, scene)
        Spacer(Modifier.height(12.dp))
        status?.let { Text(statusText(it), style = MaterialTheme.typography.bodyMedium) }
        car?.let {
            Spacer(Modifier.height(8.dp))
            Text(carText(it), style = MaterialTheme.typography.bodyMedium)
            if (it.bool("android_auto") == true) {
                Text("Android Auto connected", color = Cyan, style = MaterialTheme.typography.bodyMedium)
            }
        }
        val animations = config["animations"]?.obj("animations")?.keys.orEmpty()
        if (animations.isNotEmpty()) {
            Spacer(Modifier.height(16.dp))
            Text("Play an animation", style = MaterialTheme.typography.labelLarge)
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                for (name in animations) AssistChip(onClick = { companion.play(name) }, label = { Text(name) })
            }
        }
    }
}

@Composable
fun ConnectionLine(companion: Companion) {
    val connection by companion.connection.collectAsStateWithLifecycle()
    val text = when (connection.link) {
        Companion.Link.CONNECTED -> "Connected to the board (${connection.address})"
        Companion.Link.CONNECTING -> "Looking for the board at ${connection.address}" +
            (connection.problem?.let { " · $it" } ?: "")
    }
    Text(text, style = MaterialTheme.typography.labelMedium,
        color = if (connection.link == Companion.Link.CONNECTED) Cyan else MaterialTheme.colorScheme.onSurface)
}

/** The scene on 128 × 128 pixels per display, drawn by Panel and shown crisp, without smoothing. */
@Composable
private fun Displays(companion: Companion, scene: JsonObject?) {
    val pictures by companion.pictures.version.collectAsStateWithLifecycle()
    val count = remember { intArrayOf(1) }  // displays of the last scene: pictures and clips keep it
    val bitmaps = remember(scene, pictures) {
        if (scene == null) emptyList()
        else {
            count[0] = Panel.displays(scene, count[0])
            (0 until count[0]).map { i ->
                Bitmap.createBitmap(Panel.render(scene, i, companion.pictures), Panel.SIZE, Panel.SIZE, Bitmap.Config.ARGB_8888)
                    .asImageBitmap()
            }
        }
    }
    if (bitmaps.isEmpty()) {
        Text("Waiting for his face ...", style = MaterialTheme.typography.bodyMedium)
        return
    }
    Row(Modifier.fillMaxWidth().widthIn(max = 520.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        for (bitmap in bitmaps) {
            Image(bitmap, contentDescription = "his face", filterQuality = FilterQuality.None,
                modifier = Modifier.weight(1f).aspectRatio(1f))
        }
    }
}

private fun statusText(s: JsonObject): String {
    val parts = mutableListOf(if (s.bool("asleep") == true) "Asleep" else "Mood: ${s.str("mood") ?: "?"}")
    s.str("animation")?.let { parts += "playing $it" }
    s.str("place")?.let { parts += "in $it" }
    val assistant = s.str("assistant")
    if (assistant != null && assistant != "idle") parts += "$assistant ..."
    val rules = s.arr("rules")?.mapNotNull { (it as? JsonPrimitive)?.content }.orEmpty()
    if (rules.isNotEmpty()) parts += "rules: ${rules.joinToString(", ")}"
    return parts.joinToString(" · ")
}

private fun carText(c: JsonObject): String {
    val parts = mutableListOf<String>()
    if (c.bool("ignition") == false) parts += "Ignition off"
    c.num("speed_kmh")?.let { parts += "${it.roundToInt()} km/h" }
    c.num("rpm")?.let { parts += "${it.roundToInt()} rpm" }
    c.num("oil_c")?.let { parts += "oil ${it.roundToInt()} °C" }
    c.num("coolant_c")?.let { parts += "coolant ${it.roundToInt()} °C" }
    return parts.joinToString(" · ")
}
