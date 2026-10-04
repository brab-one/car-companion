package io.github.deadeyebarb.carcompanion.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExposedDropdownMenuAnchorType
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.deadeyebarb.carcompanion.Companion
import io.github.deadeyebarb.carcompanion.arr
import io.github.deadeyebarb.carcompanion.bool
import io.github.deadeyebarb.carcompanion.int
import io.github.deadeyebarb.carcompanion.num
import io.github.deadeyebarb.carcompanion.obj
import io.github.deadeyebarb.carcompanion.str
import io.github.deadeyebarb.carcompanion.toJson
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

private val CHANNELS = mapOf("2.4" to (1..13).toList(), "5" to listOf(36, 40, 44, 48))
private val DEFAULT_CHANNEL = mapOf("2.4" to 6, "5" to 36)

/**
 * Wireless Android Auto through the board, like Configure > Board on the board's
 * page: on and off, pairing, what the bridge does, and its settings
 * (android_auto in settings.json; PROTOCOL.md, `board`).
 */
@Composable
fun AndroidAutoScreen(companion: Companion, modifier: Modifier = Modifier) {
    val board by companion.board.collectAsStateWithLifecycle()
    val config by companion.config.collectAsStateWithLifecycle()
    val car by companion.car.collectAsStateWithLifecycle()
    val connection by companion.connection.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    var message by remember { mutableStateOf("") }

    // The board says what the bridge does every 2 s while this screen shows.
    LaunchedEffect(connection.link) {
        while (true) {
            companion.boardInfo()
            delay(2_000)
        }
    }

    val aa = config["settings"]?.obj("android_auto") ?: JsonObject(emptyMap())
    val enabled = aa.bool("enabled") ?: false
    val status = board?.obj("android_auto")

    Column(modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)) {
        ConnectionLine(companion)
        Text("Wireless Android Auto", style = MaterialTheme.typography.titleLarge)
        Text("For cars with Android Auto over a cable: your phone connects to the board, the board to the car.",
            style = MaterialTheme.typography.bodyMedium)
        Text(statusText(board, status), style = MaterialTheme.typography.bodyMedium, color = Cyan)
        if (car?.bool("android_auto") == true) Text("Your phone's Android Auto is connected.", color = Cyan)
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Button(onClick = {
                scope.launch {
                    val errors = companion.patchSettings(JsonObject(mapOf("android_auto" to toJson(mapOf("enabled" to !enabled)))))
                    message = when {
                        errors == null -> "No answer from the board."
                        errors.isNotEmpty() -> errors.joinToString("\n")
                        !enabled -> "Android Auto is enabled: pair your phone with the board over Bluetooth in the next minutes."
                        else -> "Android Auto is disabled: the board's Wi-Fi and Bluetooth are back to normal."
                    }
                }
            }) { Text(if (enabled) "Disable Android Auto" else "Enable Android Auto") }
            OutlinedButton(enabled = status?.str("state") == "on", onClick = {
                companion.pairPhone()
                message = "Pairing opens within 2 s: pair your phone with the board in its Bluetooth settings."
            }) { Text("Pair a phone") }
        }
        if (message.isNotEmpty()) Text(message, style = MaterialTheme.typography.bodySmall)
        Spacer(Modifier.height(8.dp))
        AndroidAutoSettings(aa) { changes ->
            scope.launch {
                val errors = companion.patchSettings(JsonObject(mapOf("android_auto" to changes)))
                message = when {
                    errors == null -> "No answer from the board."
                    errors.isNotEmpty() -> errors.joinToString("\n")
                    else -> "Saved. The bridge starts again with them within 2 s, if Android Auto is on."
                }
            }
        }
    }
}

@Composable
private fun AndroidAutoSettings(aa: JsonObject, save: (JsonObject) -> Unit) {
    var keepWifi by remember(aa) { mutableStateOf(aa.bool("keep_wifi") ?: true) }
    var name by remember(aa) { mutableStateOf(aa.str("wifi_name") ?: "") }
    var password by remember(aa) { mutableStateOf(aa.str("wifi_password") ?: "") }
    var band by remember(aa) { mutableStateOf(aa.str("wifi_band") ?: "2.4") }
    var channel by remember(aa) { mutableStateOf(aa.int("wifi_channel") ?: 0) }
    var country by remember(aa) { mutableStateOf(aa.str("country") ?: "") }
    var pairing by remember(aa) { mutableStateOf((aa.num("pairing_min") ?: 3.0).toInt().toString()) }

    Text("Settings", style = MaterialTheme.typography.titleMedium)
    Row(verticalAlignment = Alignment.CenterVertically) {
        Checkbox(checked = keepWifi, onCheckedChange = { keepWifi = it })
        Text("Stay on your Wi-Fi meanwhile (the access point gets a second, virtual interface)")
    }
    OutlinedTextField(name, { name = it }, Modifier.fillMaxWidth(), label = { Text("Wi-Fi name") },
        placeholder = { Text("made up: CarCompanion-...") }, singleLine = true)
    OutlinedTextField(password, { password = it }, Modifier.fillMaxWidth(), label = { Text("Wi-Fi password") },
        placeholder = { Text("made up on the board") }, singleLine = true)
    Choice("Band", band, listOf("2.4" to "2.4 GHz", "5" to "5 GHz (the UNO Q allows no access point there)")) {
        band = it
        channel = 0
    }
    Choice("Channel", channel, listOf(0 to "automatic (${DEFAULT_CHANNEL[band]})") +
        CHANNELS.getValue(band).map { it to it.toString() }) { channel = it }
    OutlinedTextField(country, { country = it.uppercase().take(2) }, Modifier.fillMaxWidth(),
        label = { Text("Country, for its Wi-Fi rules (e.g. IT)") }, placeholder = { Text("the board's own") }, singleLine = true)
    OutlinedTextField(pairing, { pairing = it.filter(Char::isDigit).take(2) }, Modifier.fillMaxWidth(),
        label = { Text("Pairing open for (min)") }, singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
    Button(onClick = {
        save(JsonObject(mapOf(
            "keep_wifi" to JsonPrimitive(keepWifi), "wifi_name" to JsonPrimitive(name.trim()),
            "wifi_password" to JsonPrimitive(password), "wifi_band" to JsonPrimitive(band),
            "wifi_channel" to JsonPrimitive(channel), "country" to JsonPrimitive(country.trim()),
            "pairing_min" to JsonPrimitive(pairing.toIntOrNull() ?: 3),
        )))
    }) { Text("Save") }
}

@Composable
private fun <T> Choice(label: String, value: T, options: List<Pair<T, String>>, pick: (T) -> Unit) {
    var open by remember { mutableStateOf(false) }
    ExposedDropdownMenuBox(expanded = open, onExpandedChange = { open = it }) {
        OutlinedTextField(
            value = options.firstOrNull { it.first == value }?.second ?: value.toString(), onValueChange = {},
            readOnly = true, label = { Text(label) },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = open) },
            modifier = Modifier.fillMaxWidth().menuAnchor(ExposedDropdownMenuAnchorType.PrimaryNotEditable),
        )
        ExposedDropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            for ((key, text) in options) DropdownMenuItem(text = { Text(text) }, onClick = { pick(key); open = false })
        }
    }
}

/** What the bridge does, as on Configure > Board. */
private fun statusText(board: JsonObject?, aa: JsonObject?): String {
    if (board == null) return "Asking the board ..."
    if (board.bool("on_board") == false) return "This is the PC simulator: Android Auto runs on the board only."
    if (aa == null || (aa.num("age_s") ?: 0.0) > 10) {
        return "The Android Auto bridge is not running on the board (start it once with tools/android_auto.sh)."
    }
    val paired = aa.arr("paired")?.mapNotNull { (it as? JsonPrimitive)?.content }.orEmpty()
    val pairedText = if (paired.isEmpty()) "No phone paired yet." else "Paired: ${paired.joinToString(", ")}."
    return when (aa.str("state")) {
        "error" -> "Could not start: ${aa.str("error")}. It tries again every minute. $pairedText"
        "on" -> {
            val s = aa.int("pairing_s") ?: 0
            val pairing = if (s > 0) "pairing open for ${s / 60}:${(s % 60).toString().padStart(2, '0')}" else "pairing closed"
            val own = if (aa.str("interface") == "ap0") {
                aa.str("home")?.let { "the board stays on \"$it\"" } ?: "the board's own Wi-Fi is free for your network"
            } else "the board left your Wi-Fi meanwhile"
            "Enabled: Wi-Fi \"${aa.str("wifi_name")}\" (password ${aa.str("wifi_password")}), ${aa.str("band")} GHz, " +
                "channel ${aa.int("channel")} · $own · " +
                "${if (aa.bool("phone") == true) "your phone is connected" else "waiting for your phone"} · $pairing. $pairedText"
        }
        else -> "Disabled: the board's Wi-Fi and Bluetooth are as usual. $pairedText"
    }
}
