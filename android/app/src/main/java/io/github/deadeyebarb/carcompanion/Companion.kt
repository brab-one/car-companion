package io.github.deadeyebarb.carcompanion

import android.content.Context
import android.location.Location
import io.github.deadeyebarb.carcompanion.face.Pictures
import io.github.deadeyebarb.carcompanion.face.ScenePlayer
import io.github.deadeyebarb.carcompanion.net.SocketIo
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit
import kotlin.math.min

/**
 * The app's side of the companion: the connection to the board, what it last
 * said (scene, status, car, settings, chat), and what the app asks of it.
 * Every message is {type, ...} on the WebUI's "msg" event (PROTOCOL.md).
 * Lives as long as the app; the screens and the service only watch and ask.
 */
class Companion(context: Context, private val scope: CoroutineScope) {
    val prefs = Prefs(context)
    private val http = OkHttpClient.Builder()
        .connectTimeout(4, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()
    val pictures = Pictures(http, scope)
    private val speaker = Speaker(context)

    enum class Link { CONNECTING, CONNECTED }
    data class Connection(val link: Link, val address: String, val problem: String? = null)

    private val _connection = MutableStateFlow(Connection(Link.CONNECTING, prefs.addresses.firstOrNull() ?: ""))
    val connection: StateFlow<Connection> = _connection
    private val _scene = MutableStateFlow<JsonObject?>(null)
    val scene: StateFlow<JsonObject?> = _scene
    private val _status = MutableStateFlow<JsonObject?>(null)
    val status: StateFlow<JsonObject?> = _status
    private val _car = MutableStateFlow<JsonObject?>(null)
    val car: StateFlow<JsonObject?> = _car
    private val _config = MutableStateFlow<Map<String, JsonObject>>(emptyMap())
    val config: StateFlow<Map<String, JsonObject>> = _config
    private val _board = MutableStateFlow<JsonObject?>(null)
    val board: StateFlow<JsonObject?> = _board
    private val _chat = MutableStateFlow<List<Chat>>(emptyList())
    val chat: StateFlow<List<Chat>> = _chat
    private val _navigation = MutableSharedFlow<Navigation>(extraBufferCapacity = 4)
    /** "Navigate to ...": the activity opens Google Maps, or the service posts a notification. */
    val navigation: SharedFlow<Navigation> = _navigation

    sealed interface Chat {
        data class Question(val text: String) : Chat
        data class Answer(val text: String, val source: String?) : Chat
        data class Line(val text: String) : Chat
        data class Navigate(val navigation: Navigation) : Chat
    }

    data class Navigation(val name: String, val lat: Double?, val lon: Double?, val query: String?, val url: String?)

    private val player = ScenePlayer(scope) { _scene.value = it }
    private var job: Job? = null
    private var socket: SocketIo? = null
    private val waiting = mutableMapOf<String, CompletableDeferred<JsonObject>>()  // "config_result:settings" -> reply

    /** Keep looking for the board and stay connected (again after [stop], or new addresses). */
    fun start() {
        if (job?.isActive == true) return
        job = scope.launch { run() }
    }

    fun stop() {
        job?.cancel()
        job = null
        socket?.close()
    }

    fun restart() {
        stop()
        start()
    }

    private suspend fun run() {
        var attempt = 0
        while (scope.isActive) {
            for (address in prefs.addresses) {
                if (session(address)) attempt = 0
            }
            delay(min(15_000L, 1_000L shl min(attempt++, 4)))  // 1 s, 2 s, 4 s ... 15 s between rounds
        }
    }

    /** One connection to [address], until it ends. True if it got connected. */
    private suspend fun session(address: String): Boolean {
        val base = "http://$address"
        val events = Channel<Pair<String, JsonElement>>(Channel.UNLIMITED)
        var problem: String? = null
        val io = SocketIo(http, object : SocketIo.Listener {
            override fun onConnected() { events.trySend(CONNECTED to JsonPrimitive(true)) }
            override fun onEvent(name: String, data: JsonElement) { events.trySend(name to data) }
            override fun onClosed(reason: String) {
                problem = reason
                events.trySend(CLOSED to JsonPrimitive(reason))
            }
        })
        _connection.value = Connection(Link.CONNECTING, address, _connection.value.problem)
        var connected = false
        socket = io
        io.connect(base)
        try {
            while (true) {
                // The board pings every 25 s and sends scenes far more often: silence means it is gone.
                val (name, data) = withTimeoutOrNull(if (connected) SILENT_MS else CONNECT_MS) { events.receive() }
                    ?: run { problem = if (connected) "no answer from the board" else "not found"; null }
                    ?: break
                when (name) {
                    CLOSED -> break
                    CONNECTED -> {
                        connected = true
                        pictures.base = base
                        _connection.value = Connection(Link.CONNECTED, address)
                        send(message("hello", "client" to "android", "version" to 1))
                    }
                    "msg" -> (data as? JsonObject)?.let { handle(it) }
                }
            }
        } finally {
            io.close()
            if (socket === io) socket = null
            waiting.values.forEach { it.cancel() }
            waiting.clear()
            _connection.value = Connection(Link.CONNECTING, address, problem)
        }
        return connected
    }

    // ---- what the companion says (like the page's app.js) ----------------------------

    private fun handle(m: JsonObject) {
        when (m.str("type")) {
            "state" -> {
                _config.value = m.obj("config")?.mapNotNull { (k, v) -> (v as? JsonObject)?.let { k to it } }?.toMap().orEmpty()
                player.reset()
                pictures.forget()
                m.obj("scene")?.let { _scene.value = it }
                m.obj("status")?.let { _status.value = it }
                m.obj("car")?.let { _car.value = it }
            }
            "config" -> {
                val name = m.str("name") ?: return
                val data = m.obj("data") ?: return
                _config.value = _config.value + (name to data)
            }
            "scene" -> m.obj("scene")?.let { player.push(it, m.num("t")) }
            "status" -> _status.value = m
            "car" -> _car.value = m
            "board" -> _board.value = m
            "images", "clip_files" -> pictures.forget()
            "answer" -> {
                val text = m.str("text") ?: return
                addChat(Chat.Answer(text, m.str("source")))
                if (prefs.speak) speaker.say(text, m.str("lang"))
            }
            "say" -> {
                val text = m.str("text") ?: return
                addChat(Chat.Line(text))
                if (prefs.speak) speaker.say(text, null)
            }
            "navigate" -> {
                val nav = Navigation(m.str("name") ?: "", m.num("lat"), m.num("lon"), m.str("query"), m.str("url"))
                addChat(Chat.Navigate(nav))
                _navigation.tryEmit(nav)
            }
            "config_result" -> waiting.remove("config_result:${m.str("name")}")?.complete(m)
        }
    }

    private fun addChat(item: Chat) {
        _chat.value = (_chat.value + item).takeLast(CHAT_KEEP)
    }

    // ---- what the app asks --------------------------------------------------------------

    fun send(msg: JsonObject): Boolean = socket?.emit("msg", msg) ?: false

    fun ask(text: String) {
        val question = text.trim()
        if (question.isEmpty()) return
        addChat(Chat.Question(question))
        if (!send(message("ask", "text" to question))) addChat(Chat.Line("Not connected to the board yet."))
    }

    fun play(animation: String) = send(message("play", "name" to animation))

    /** The phone's GPS position, for his places, answers and navigation. */
    fun sendLocation(location: Location) {
        send(message("location",
            "lat" to location.latitude, "lon" to location.longitude,
            "speed_kmh" to if (location.hasSpeed()) location.speed * 3.6 else null,
            "acc_m" to if (location.hasAccuracy()) location.accuracy else null,
            "time" to location.time / 1000.0))
    }

    fun boardInfo() = send(message("board_info"))

    fun pairPhone() = send(message("android_auto_pair"))

    /**
     * Changes some fields of settings.json on the board (config_patch). Returns the
     * board's problems with them (empty: saved), or null without an answer.
     */
    suspend fun patchSettings(data: JsonObject): List<String>? {
        val reply = CompletableDeferred<JsonObject>()
        waiting["config_result:settings"] = reply
        if (!send(message("config_patch", "name" to "settings", "data" to data))) {
            waiting.remove("config_result:settings")
            return null
        }
        val result = withTimeoutOrNull(REPLY_MS) { runCatching { reply.await() }.getOrNull() } ?: return null
        return result.arr("errors")?.mapNotNull { (it as? JsonPrimitive)?.content }.orEmpty()
    }

    val settings: JsonObject? get() = _config.value["settings"]

    private companion object Limits {
        const val CONNECTED = "\u0000connected"
        const val CLOSED = "\u0000closed"
        const val CONNECT_MS = 6_000L
        const val SILENT_MS = 50_000L
        const val REPLY_MS = 5_000L
        const val CHAT_KEEP = 100
    }
}
