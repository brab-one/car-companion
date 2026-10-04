package io.github.deadeyebarb.carcompanion

import android.content.Context
import android.speech.tts.TextToSpeech
import java.util.Locale

/** Reads his answers and lines aloud with the phone's voice, in their language. */
class Speaker(context: Context) {
    private var ready = false
    private val tts = TextToSpeech(context.applicationContext) { status -> ready = status == TextToSpeech.SUCCESS }

    fun say(text: String, lang: String?) {
        if (!ready || text.isBlank()) return
        tts.language = if (lang == "de") Locale.GERMAN else Locale.ENGLISH
        tts.speak(text, TextToSpeech.QUEUE_ADD, null, text.hashCode().toString())
    }
}
