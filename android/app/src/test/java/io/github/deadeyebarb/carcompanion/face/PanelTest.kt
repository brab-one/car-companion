package io.github.deadeyebarb.carcompanion.face

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Test
import java.security.MessageDigest

/**
 * The app must draw scenes pixel for pixel like the page (assets/render_canvas.js)
 * and the OLED. scenes.json holds real scenes from the companion and the SHA-256
 * of what the page's renderer draws (tools/android_test_scenes.py makes it).
 */
class PanelTest {
    private val cases = Json.parseToJsonElement(
        javaClass.classLoader!!.getResource("scenes.json")!!.readText()) as JsonArray

    @Test
    fun drawsEveryScenePixelForPixelLikeThePage() {
        val wrong = mutableListOf<String>()
        for (case in cases) {
            case as JsonObject
            val name = (case["name"] as JsonPrimitive).content
            val scene = case["scene"] as JsonObject
            val expected = (case["sha256"] as JsonArray).map { (it as JsonPrimitive).content }
            val drawn = (expected.indices).map { sha256(Panel.render(scene, it)) }
            if (drawn != expected) wrong += name
        }
        assertEquals("scenes drawn differently from the page", emptyList<String>(), wrong)
    }

    @Test
    fun anEyeIsARoundedRectangleWithASlantedTopAndAHappyCut() {
        val eye = Panel.Shape(x = 40.0, y = 64.0, w = 36.0, h = 44.0, r = 10.0, slant = 12.0, cut = 14.0, innerRight = true)
        assertEquals(true, Panel.insideEye(40.5, 64.5, eye))   // the middle
        assertEquals(false, Panel.insideEye(22.6, 42.6, eye))  // the rounded top-left corner
        // The top edge drops from 0 px at the outer side to 12 px at the inner one (inner: right):
        assertEquals(true, Panel.insideEye(32.5, 46.5, eye))   // there it is 3.5 px lower, at y 45.5
        assertEquals(false, Panel.insideEye(47.5, 46.5, eye))  // there 8.5 px lower, at y 50.5
        assertEquals(false, Panel.insideEye(40.5, 84.5, eye))  // the cut takes the bottom middle
    }

    @Test
    fun coloursAreReducedToRgb565AndDimmed() {
        assertEquals(0xFF00E7FF.toInt(), Panel.panelColor(0x00E5FF, 1.0))
        assertEquals(0xFF007480.toInt(), Panel.panelColor(0x00E5FF, 0.5))
    }

    private fun sha256(argb: IntArray): String {
        val rgba = ByteArray(argb.size * 4)
        argb.forEachIndexed { i, p ->
            rgba[i * 4] = (p shr 16).toByte()
            rgba[i * 4 + 1] = (p shr 8).toByte()
            rgba[i * 4 + 2] = p.toByte()
            rgba[i * 4 + 3] = (p ushr 24).toByte()
        }
        return MessageDigest.getInstance("SHA-256").digest(rgba).joinToString("") { "%02x".format(it) }
    }
}
