package io.github.deadeyebarb.carcompanion.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import io.github.deadeyebarb.carcompanion.BuildConfig
import io.github.deadeyebarb.carcompanion.Companion

/** The app's own settings: where the board is, and what the phone does for him. */
@Composable
fun SettingsScreen(companion: Companion, modifier: Modifier = Modifier, startService: () -> Unit) {
    val prefs = companion.prefs
    var addresses by remember { mutableStateOf(prefs.addresses.joinToString(", ")) }
    var sendLocation by remember { mutableStateOf(prefs.sendLocation) }
    var speak by remember { mutableStateOf(prefs.speak) }
    var openMaps by remember { mutableStateOf(prefs.openMaps) }

    Column(modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)) {
        ConnectionLine(companion)
        Text("The board", style = MaterialTheme.typography.titleMedium)
        OutlinedTextField(addresses, { addresses = it }, Modifier.fillMaxWidth(), label = { Text("Addresses, tried in turn") })
        Text("10.0.0.1:7000 is the board's own Wi-Fi in the car (Android Auto's access point). At home, add its " +
            "address on your network, e.g. 192.168.1.172:7000.", style = MaterialTheme.typography.bodySmall)
        Button(onClick = {
            prefs.addresses = addresses.split(',', '\n', ' ').map { it.trim() }.filter { it.isNotEmpty() }
            companion.restart()
        }) { Text("Connect") }

        Text("The phone", style = MaterialTheme.typography.titleMedium)
        Toggle("Send my location to him (GPS), also in the background", sendLocation) {
            sendLocation = it
            prefs.sendLocation = it
            if (it) startService()
        }
        Toggle("Read his answers aloud", speak) {
            speak = it
            prefs.speak = it
        }
        Toggle("Open Google Maps when he finds a route (\"navigate to ...\")", openMaps) {
            openMaps = it
            prefs.openMaps = it
        }
        Text("Car Companion ${BuildConfig.VERSION_NAME}", style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun Toggle(text: String, checked: Boolean, change: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(text, Modifier.weight(1f))
        Switch(checked = checked, onCheckedChange = change)
    }
}
