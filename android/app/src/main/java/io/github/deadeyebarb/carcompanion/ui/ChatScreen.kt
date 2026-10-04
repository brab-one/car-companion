package io.github.deadeyebarb.carcompanion.ui

import android.app.Activity
import android.content.Intent
import android.speech.RecognizerIntent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Navigation
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.deadeyebarb.carcompanion.Companion
import io.github.deadeyebarb.carcompanion.str

/** Questions to him, typed or spoken, and his answers; "navigate to ..." opens Google Maps. */
@Composable
fun ChatScreen(companion: Companion, modifier: Modifier = Modifier, navigate: (Companion.Navigation) -> Unit) {
    val chat by companion.chat.collectAsStateWithLifecycle()
    val status by companion.status.collectAsStateWithLifecycle()
    var text by rememberSaveable { mutableStateOf("") }
    val list = rememberLazyListState()
    LaunchedEffect(chat.size) { if (chat.isNotEmpty()) list.animateScrollToItem(chat.size - 1) }

    // The phone's speech recognition: what you say becomes the question.
    val listen = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            result.data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull()?.let { companion.ask(it) }
        }
    }

    Column(modifier.fillMaxSize().imePadding().padding(horizontal = 12.dp)) {
        ConnectionLine(companion)
        LazyColumn(Modifier.weight(1f).fillMaxWidth(), state = list, verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (chat.isEmpty()) item {
                Text("Ask him about the car, where you are, the peaks around, or say \"navigate to ...\".",
                    style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(vertical = 16.dp))
            }
            items(chat) { item -> ChatItem(item, navigate) }
        }
        val assistant = status?.str("assistant")
        if (assistant != null && assistant != "idle") {
            Text("He is $assistant ...", style = MaterialTheme.typography.labelMedium, color = Cyan)
        }
        Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(
                value = text, onValueChange = { text = it }, modifier = Modifier.weight(1f),
                placeholder = { Text("Type a question ...") }, singleLine = true,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                keyboardActions = KeyboardActions(onSend = { companion.ask(text); text = "" }),
            )
            IconButton(onClick = { companion.ask(text); text = "" }) {
                Icon(Icons.AutoMirrored.Filled.Send, contentDescription = "Ask")
            }
            IconButton(onClick = {
                runCatching {
                    listen.launch(Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
                        .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                        .putExtra(RecognizerIntent.EXTRA_PROMPT, "Ask him"))
                }
            }) { Icon(Icons.Filled.Mic, contentDescription = "Speak") }
        }
    }
}

@Composable
private fun ChatItem(item: Companion.Chat, navigate: (Companion.Navigation) -> Unit) {
    when (item) {
        is Companion.Chat.Question -> Bubble(item.text, mine = true)
        is Companion.Chat.Answer -> Bubble(item.text, mine = false,
            note = when (item.source) { "data" -> "from the car and the map"; "model" -> "AI model"; else -> null })
        is Companion.Chat.Line -> Bubble(item.text, mine = false, italic = true)
        is Companion.Chat.Navigate -> Box(Modifier.fillMaxWidth()) {
            Button(onClick = { navigate(item.navigation) }) {
                Icon(Icons.Filled.Navigation, contentDescription = null)
                Text("  Navigate to ${item.navigation.name}")
            }
        }
    }
}

@Composable
private fun Bubble(text: String, mine: Boolean, note: String? = null, italic: Boolean = false) {
    Box(Modifier.fillMaxWidth(), contentAlignment = if (mine) Alignment.CenterEnd else Alignment.CenterStart) {
        Surface(
            shape = RoundedCornerShape(14.dp),
            color = if (mine) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceVariant,
            modifier = Modifier.widthIn(max = 320.dp),
        ) {
            Column(Modifier.padding(horizontal = 12.dp, vertical = 8.dp)) {
                Text(text, color = if (mine) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface,
                    fontStyle = if (italic) FontStyle.Italic else FontStyle.Normal)
                note?.let { Text(it, style = MaterialTheme.typography.labelSmall) }
            }
        }
    }
}
