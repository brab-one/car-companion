package io.github.deadeyebarb.carcompanion.net

import io.github.deadeyebarb.carcompanion.message
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Test

/** Engine.IO v4 / Socket.IO packets as the board's WebUI (python-socketio) sends them. */
class SocketIoTest {
    @Test
    fun readsTheHandshakeAndPings() {
        assertEquals(SocketIo.Packet.Open(25_000, 20_000),
            SocketIo.parse("""0{"sid":"abc","upgrades":[],"pingTimeout":20000,"pingInterval":25000,"maxPayload":10485760}"""))
        assertEquals(SocketIo.Packet.Ping, SocketIo.parse("2"))
        assertEquals(SocketIo.Packet.Connected, SocketIo.parse("""40{"sid":"xyz"}"""))
        assertEquals(SocketIo.Packet.Close, SocketIo.parse("1"))
    }

    @Test
    fun readsEvents() {
        val packet = SocketIo.parse("""42["msg",{"type":"scene","t":12.5}]""") as SocketIo.Packet.Event
        assertEquals("msg", packet.name)
        assertEquals(JsonPrimitive("scene"), (packet.data as JsonObject)["type"])
        assertEquals("msg", (SocketIo.parse("""4217["msg",{}]""") as SocketIo.Packet.Event).name)  // with an ack id
        assertEquals(SocketIo.Packet.Other, SocketIo.parse("""42not json"""))
    }

    @Test
    fun writesEvents() {
        assertEquals("""42["msg",{"type":"hello","client":"android","version":1}]""",
            SocketIo.encodeEvent("msg", message("hello", "client" to "android", "version" to 1)))
    }
}
