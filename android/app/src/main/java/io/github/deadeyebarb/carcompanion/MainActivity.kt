package io.github.deadeyebarb.carcompanion

import android.Manifest
import android.content.ActivityNotFoundException
import android.content.Intent
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Chat
import androidx.compose.material.icons.filled.DirectionsCar
import androidx.compose.material.icons.filled.Face
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import io.github.deadeyebarb.carcompanion.ui.AndroidAutoScreen
import io.github.deadeyebarb.carcompanion.ui.CarCompanionTheme
import io.github.deadeyebarb.carcompanion.ui.ChatScreen
import io.github.deadeyebarb.carcompanion.ui.FaceScreen
import io.github.deadeyebarb.carcompanion.ui.SettingsScreen
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private val permissions = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
        CompanionService.start(this)  // with the location permission now, if it was given
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        intent?.getStringExtra(EXTRA_BOARD)?.let { useBoard(it) }
        companion.start()
        askPermissions()

        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                companion.navigation.collect { nav -> if (companion.prefs.openMaps) navigate(nav) }
            }
        }

        setContent {
            CarCompanionTheme {
                var tab by rememberSaveable { mutableStateOf(Tab.FACE) }
                Scaffold(
                    bottomBar = {
                        NavigationBar {
                            for (t in Tab.entries) {
                                NavigationBarItem(
                                    selected = tab == t,
                                    onClick = { tab = t },
                                    icon = { Icon(t.icon, contentDescription = null) },
                                    label = { Text(t.label) },
                                )
                            }
                        }
                    },
                ) { padding ->
                    val modifier = Modifier.padding(padding)
                    when (tab) {
                        Tab.FACE -> FaceScreen(companion, modifier)
                        Tab.CHAT -> ChatScreen(companion, modifier, ::navigate)
                        Tab.ANDROID_AUTO -> AndroidAutoScreen(companion, modifier)
                        Tab.SETTINGS -> SettingsScreen(companion, modifier) { CompanionService.start(this) }
                    }
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        intent.getStringExtra(EXTRA_BOARD)?.let { useBoard(it) }
    }

    /** For testing: `adb shell am start -n ... -e board 10.0.2.2:7001` (the board through the PC). */
    private fun useBoard(address: String) {
        companion.prefs.addresses = listOf(address)
        companion.restart()
    }

    private fun askPermissions() {
        val wanted = mutableListOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION)
        if (Build.VERSION.SDK_INT >= 33) wanted += Manifest.permission.POST_NOTIFICATIONS
        permissions.launch(wanted.toTypedArray())
    }

    fun navigate(nav: Companion.Navigation) {
        try {
            startActivity(Maps.intent(nav))
        } catch (_: ActivityNotFoundException) {
            Maps.fallback(nav)?.let { runCatching { startActivity(it) } }
        }
    }

    private enum class Tab(val label: String, val icon: androidx.compose.ui.graphics.vector.ImageVector) {
        FACE("Face", Icons.Filled.Face),
        CHAT("Chat", Icons.AutoMirrored.Filled.Chat),
        ANDROID_AUTO("Android Auto", Icons.Filled.DirectionsCar),
        SETTINGS("Settings", Icons.Filled.Settings),
    }

    companion object Extras {
        const val EXTRA_BOARD = "board"
    }
}
