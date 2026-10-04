package io.github.deadeyebarb.carcompanion.net

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.longOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener

/**
 * A small Socket.IO client: Engine.IO v4 over a WebSocket, the default namespace,
 * events both ways, and answers to the server's pings. That is all the board's
 * page needs (Arduino's WebUI brick runs python-socketio; PROTOCOL.md, "Transport").
 */
class SocketIo(private val http: OkHttpClient, private val listener: Listener) {
    interface Listener {
        fun onConnected()
        fun onEvent(name: String, data: JsonElement)
        /** Once, when the connection ends or could not be made. */
        fun onClosed(reason: String)
    }

    private var socket: WebSocket? = null
    @Volatile private var closed = false

    /** [base] like "http://10.0.0.1:7000". */
    fun connect(base: String) {
        val url = base.trimEnd('/').replaceFirst("http", "ws") + "/socket.io/?EIO=4&transport=websocket"
        socket = http.newWebSocket(Request.Builder().url(url).build(), object : WebSocketListener() {
            override fun onMessage(webSocket: WebSocket, text: String) = received(webSocket, text)
            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) = end("closed ($code)")
            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) =
                end(t.message ?: t.javaClass.simpleName)
        })
    }

    fun emit(name: String, data: JsonElement): Boolean = socket?.send(encodeEvent(name, data)) ?: false

    fun close() {
        socket?.close(1000, null)
        end("closed by the app")
    }

    private fun received(webSocket: WebSocket, text: String) {
        when (val packet = parse(text)) {
            is Packet.Open -> webSocket.send("40")  // join the default namespace
            Packet.Ping -> webSocket.send("3")
            Packet.Connected -> listener.onConnected()
            is Packet.Event -> listener.onEvent(packet.name, packet.data)
            is Packet.Error -> {
                webSocket.close(1000, null)
                end(packet.message)
            }
            Packet.Close -> {
                webSocket.close(1000, null)
                end("closed by the board")
            }
            Packet.Other -> Unit
        }
    }

    private fun end(reason: String) {
        if (closed) return
        closed = true
        listener.onClosed(reason)
    }

    sealed interface Packet {
        data class Open(val pingIntervalMs: Long, val pingTimeoutMs: Long) : Packet
        data object Ping : Packet
        data object Close : Packet
        data object Connected : Packet
        data class Event(val name: String, val data: JsonElement) : Packet
        data class Error(val message: String) : Packet
        data object Other : Packet
    }

    companion object {
        private val json = Json { ignoreUnknownKeys = true }

        /** One Engine.IO packet as text, e.g. `0{...}` (open), `2` (ping), `42["msg",{...}]` (an event). */
        fun parse(text: String): Packet {
            if (text.isEmpty()) return Packet.Other
            return when (text[0]) {
                '0' -> {
                    val open = runCatching { json.parseToJsonElement(text.substring(1)) as JsonObject }.getOrNull()
                    Packet.Open(
                        (open?.get("pingInterval") as? JsonPrimitive)?.longOrNull ?: 25_000,
                        (open?.get("pingTimeout") as? JsonPrimitive)?.longOrNull ?: 20_000,
                    )
                }
                '1' -> Packet.Close
                '2' -> Packet.Ping
                '4' -> parseSocketIo(text.substring(1))
                else -> Packet.Other
            }
        }

        // A Socket.IO packet: its type, then (for events) an optional ack id and a JSON array.
        private fun parseSocketIo(text: String): Packet {
            if (text.isEmpty()) return Packet.Other
            return when (text[0]) {
                '0' -> Packet.Connected
                '1' -> Packet.Close
                '2' -> {
                    val start = text.indexOf('[')
                    val array = if (start < 0) null
                    else runCatching { json.parseToJsonElement(text.substring(start)) as JsonArray }.getOrNull()
                    val name = (array?.getOrNull(0) as? JsonPrimitive)?.content
                    if (array == null || name == null) Packet.Other
                    else Packet.Event(name, array.getOrNull(1) ?: kotlinx.serialization.json.JsonNull)
                }
                '4' -> Packet.Error("the board refused the connection: ${text.substring(1)}")
                else -> Packet.Other
            }
        }

        fun encodeEvent(name: String, data: JsonElement): String = "42" + JsonArray(listOf(JsonPrimitive(name), data))
    }
}
