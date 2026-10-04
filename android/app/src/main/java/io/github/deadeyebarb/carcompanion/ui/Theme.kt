package io.github.deadeyebarb.carcompanion.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

val Cyan = Color(0xFF00E5FF)

private val colors = darkColorScheme(
    primary = Cyan,
    onPrimary = Color.Black,
    secondary = Color(0xFF7CFF6B),
    background = Color(0xFF0E1116),
    surface = Color(0xFF161B22),
    surfaceVariant = Color(0xFF1F2630),
    onBackground = Color(0xFFE6EDF3),
    onSurface = Color(0xFFE6EDF3),
)

@Composable
fun CarCompanionTheme(content: @Composable () -> Unit) = MaterialTheme(colorScheme = colors, content = content)
