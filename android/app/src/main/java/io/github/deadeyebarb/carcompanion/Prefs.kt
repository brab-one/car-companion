package io.github.deadeyebarb.carcompanion

import android.content.Context
import androidx.core.content.edit

/** The app's own settings (the companion's are on the board, in settings.json). */
class Prefs(context: Context) {
    private val prefs = context.getSharedPreferences("car_companion", Context.MODE_PRIVATE)

    /** Where to look for the board, tried in turn: host:port. */
    var addresses: List<String>
        get() = (prefs.getString("addresses", null) ?: DEFAULT_ADDRESS)
            .split(',', '\n', ' ').map { it.trim() }.filter { it.isNotEmpty() }
        set(value) = prefs.edit { putString("addresses", value.joinToString(", ")) }

    var sendLocation: Boolean
        get() = prefs.getBoolean("send_location", true)
        set(value) = prefs.edit { putBoolean("send_location", value) }

    var speak: Boolean
        get() = prefs.getBoolean("speak", true)
        set(value) = prefs.edit { putBoolean("speak", value) }

    var openMaps: Boolean
        get() = prefs.getBoolean("open_maps", true)
        set(value) = prefs.edit { putBoolean("open_maps", value) }

    companion object {
        /** The board's own Wi-Fi (Android Auto's access point), in the car. */
        const val DEFAULT_ADDRESS = "10.0.0.1:7000"
    }
}
