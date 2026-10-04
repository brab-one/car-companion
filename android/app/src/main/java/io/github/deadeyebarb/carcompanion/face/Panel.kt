package io.github.deadeyebarb.carcompanion.face

import io.github.deadeyebarb.carcompanion.arr
import io.github.deadeyebarb.carcompanion.int
import io.github.deadeyebarb.carcompanion.num
import io.github.deadeyebarb.carcompanion.obj
import io.github.deadeyebarb.carcompanion.str
import kotlinx.serialization.json.JsonObject
import java.util.Base64
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToLong

/**
 * Draws scenes pixel by pixel on 128 × 128 displays, the way the OLED will and
 * exactly like the page's assets/render_canvas.js: no anti-aliasing, colours
 * reduced to RGB565, brightness applied (PROTOCOL.md, "Scenes"). Pure Kotlin,
 * so the tests compare it with the page's renderer on any PC.
 */
object Panel {
    const val SIZE = 128

    /** A picture in ARGB pixels: a place picture (128 × 128) or a clip's sheet (128 wide). */
    class Sheet(val width: Int, val height: Int, val pixels: IntArray)

    interface Pictures {
        fun image(name: String): Sheet?
        fun clip(file: String): Sheet?
    }

    /** How many displays the scene has (eyes); other kinds keep [previous]. */
    fun displays(scene: JsonObject, previous: Int): Int =
        scene.arr("displays")?.size ?: max(1, previous)

    /** Display [index] of [scene] as ARGB pixels, row by row. */
    fun render(scene: JsonObject, index: Int, pictures: Pictures? = null): IntArray {
        val img = IntArray(SIZE * SIZE) { BLACK }
        val brightness = scene.num("brightness") ?: 1.0
        when (scene.str("kind")) {
            "eyes" -> {
                val display = scene.arr("displays")?.getOrNull(index) as? JsonObject
                for (shape in display?.arr("shapes").orEmpty()) fillEye(img, Shape.of(shape as JsonObject), brightness)
                display?.obj("visor")?.let { fillVisor(img, it, brightness) }
            }
            "image" -> pictures?.image(scene.str("image") ?: "")?.let { copyPanel(img, it, 0, brightness) }
            "clip" -> pictures?.clip(scene.str("file") ?: "")?.let {
                copyPanel(img, it, (scene.int("frame") ?: 0) * SIZE, brightness)
            }
            else -> Unit  // "off", and kinds this app does not know yet: black
        }
        val bubble = scene.obj("bubble")
        if (bubble != null && index == 0) fillBubble(img, bubble, brightness)
        return img
    }

    // ---- shapes -----------------------------------------------------------------

    class Shape(
        val x: Double, val y: Double, val w: Double, val h: Double, val r: Double,
        val slant: Double = 0.0, val cut: Double = 0.0, val innerRight: Boolean = false, val color: String = "#000000",
    ) {
        companion object {
            fun of(o: JsonObject) = Shape(
                o.num("x") ?: 0.0, o.num("y") ?: 0.0, o.num("w") ?: 0.0, o.num("h") ?: 0.0, o.num("r") ?: 0.0,
                o.num("slant") ?: 0.0, o.num("cut") ?: 0.0, o.str("inner") == "right", o.str("color") ?: "#000000",
            )
        }
    }

    /** The eye shape: a rounded rectangle, its top edge slanted, its bottom bitten
     *  off by an ellipse for happy eyes (the same rules as the OLED's). */
    fun insideEye(px: Double, py: Double, eye: Shape): Boolean {
        val hw = eye.w / 2
        val hh = eye.h / 2
        val ax = abs(px - eye.x)
        val ay = abs(py - eye.y)
        if (ax > hw || ay > hh) return false
        // Rounded corners.
        val dx = ax - (hw - eye.r)
        val dy = ay - (hh - eye.r)
        if (dx > 0 && dy > 0 && dx * dx + dy * dy > eye.r * eye.r) return false
        // Slant: the top edge drops by `slant` px at the inner side; a negative one drops the outer side.
        val fromLeft = (px - (eye.x - hw)) / eye.w
        val t = if (eye.innerRight) fromLeft else 1 - fromLeft  // 0 outer edge, 1 inner edge
        val drop = if (eye.slant >= 0) eye.slant * t else -eye.slant * (1 - t)
        if (py < eye.y - hh + drop) return false
        // Cut: an ellipse covers the bottom `cut` px (happy eyes).
        if (eye.cut > 0) {
            val rx = eye.w * 0.75
            val ry = eye.h * 0.5
            val cy = eye.y + hh - eye.cut + ry
            val u = (px - eye.x) / rx
            val v = (py - cy) / ry
            if (u * u + v * v < 1) return false
        }
        return true
    }

    private fun fillEye(img: IntArray, eye: Shape, brightness: Double) {
        val color = panelColor(hex(eye.color), brightness)
        val x0 = max(0, floor(eye.x - eye.w / 2).toInt())
        val x1 = min(SIZE, ceil(eye.x + eye.w / 2).toInt())
        val y0 = max(0, floor(eye.y - eye.h / 2).toInt())
        val y1 = min(SIZE, ceil(eye.y + eye.h / 2).toInt())
        for (y in y0 until y1) for (x in x0 until x1) {
            if (insideEye(x + 0.5, y + 0.5, eye)) img[y * SIZE + x] = color
        }
    }

    // The visor: a rounded band over the eyes, tinted by `alpha`, with two "/"
    // reflection stripes at `glint`.
    private fun fillVisor(img: IntArray, visor: JsonObject, brightness: Double) {
        val tint = panelColor(hex(visor.str("color") ?: "#000000"), brightness)
        val shine = panelColor(hex(visor.str("shine") ?: "#FFFFFF"), brightness)
        val band = Shape.of(visor).let { Shape(it.x, it.y, it.w, it.h, it.r) }
        val left = band.x - band.w / 2
        val top = band.y - band.h / 2
        val stripe = (visor.num("glint") ?: 0.2) * band.w
        val alphaTint = visor.num("alpha") ?: 0.82
        for (y in max(0, floor(top).toInt()) until min(SIZE, ceil(top + band.h).toInt())) {
            for (x in max(0, floor(left).toInt()) until min(SIZE, ceil(left + band.w).toInt())) {
                if (!insideEye(x + 0.5, y + 0.5, band)) continue
                val s = x + 0.5 - left + (y + 0.5 - top)
                val shiny = (s >= stripe && s < stripe + 5) || (s >= stripe + 9 && s < stripe + 11)
                val color = if (shiny) shine else tint
                val alpha = if (shiny) 0.9 else alphaTint
                val old = img[y * SIZE + x]
                img[y * SIZE + x] = rgb(
                    mix(color shr 16 and 255, old shr 16 and 255, alpha),
                    mix(color shr 8 and 255, old shr 8 and 255, alpha),
                    mix(color and 255, old and 255, alpha),
                )
            }
        }
    }

    // The speech bubble: a black rounded box with a 1 px outline, a solid tail
    // pointing up at the face, and the text as a 1-bit picture made by the board.
    private fun fillBubble(img: IntArray, bubble: JsonObject, brightness: Double) {
        val color = panelColor(hex(bubble.str("color") ?: "#FFFFFF"), brightness)
        fun set(x: Int, y: Int, on: Boolean) {
            if (x < 0 || y < 0 || x >= SIZE || y >= SIZE) return
            img[y * SIZE + x] = if (on) color else BLACK
        }
        val outer = Shape.of(bubble).let { Shape(it.x, it.y, it.w, it.h, it.r) }
        val inner = Shape(outer.x, outer.y, outer.w - 2, outer.h - 2, max(0.0, outer.r - 1))
        val top = outer.y - outer.h / 2
        val tail = bubble.arr("tail")
        val tipX = (tail?.getOrNull(0) as? kotlinx.serialization.json.JsonPrimitive)?.content?.toDoubleOrNull() ?: outer.x
        val tipY = (tail?.getOrNull(1) as? kotlinx.serialization.json.JsonPrimitive)?.content?.toDoubleOrNull() ?: top
        for (y in floor(tipY).toInt() until ceil(outer.y + outer.h / 2).toInt()) {
            for (x in floor(outer.x - outer.w / 2).toInt() until ceil(outer.x + outer.w / 2).toInt()) {
                val px = x + 0.5
                val py = y + 0.5
                if (insideEye(px, py, outer)) set(x, y, !insideEye(px, py, inner))
                else if (py < top && abs(px - tipX) <= (4 * (py - tipY)) / (top - tipY)) set(x, y, true)
            }
        }
        val text = bubble.obj("text") ?: return
        val bits = runCatching { Base64.getDecoder().decode(text.str("bits") ?: "") }.getOrNull() ?: return
        val w = text.int("w") ?: 0
        val h = text.int("h") ?: 0
        val tx = text.int("x") ?: 0
        val ty = text.int("y") ?: 0
        val stride = (w + 7) / 8
        for (y in 0 until h) for (x in 0 until w) {
            val byte = bits.getOrNull(y * stride + (x shr 3))?.toInt() ?: 0
            if (byte and (0x80 shr (x and 7)) != 0) set(tx + x, ty + y, true)
        }
    }

    // ---- pictures -----------------------------------------------------------------

    private fun copyPanel(img: IntArray, sheet: Sheet, top: Int, brightness: Double) {
        if (sheet.width < SIZE || top < 0 || top + SIZE > sheet.height) return
        for (y in 0 until SIZE) for (x in 0 until SIZE) {
            img[y * SIZE + x] = panelColor(sheet.pixels[(top + y) * sheet.width + x] and 0xFFFFFF, brightness)
        }
    }

    // ---- colours ------------------------------------------------------------------

    private const val BLACK = 0xFF000000.toInt()

    private fun hex(color: String): Int = color.removePrefix("#").toIntOrNull(16) ?: 0

    /** The panel stores RGB565; dimming happens in the panel, so it is applied afterwards. */
    fun panelColor(rgb: Int, brightness: Double): Int {
        val r5 = rgb shr 19 and 31
        val g6 = rgb shr 10 and 63
        val b5 = rgb shr 3 and 31
        return rgb(
            ((r5 shl 3) or (r5 shr 2)).dim(brightness),
            ((g6 shl 2) or (g6 shr 4)).dim(brightness),
            ((b5 shl 3) or (b5 shr 2)).dim(brightness),
        )
    }

    private fun Int.dim(brightness: Double) = (this * brightness).roundHalfUp()

    private fun mix(color: Int, old: Int, alpha: Double) = (color * alpha + old * (1 - alpha)).roundHalfUp()

    /** Like JavaScript's Math.round: halves go up. */
    private fun Double.roundHalfUp(): Int = floor(this + 0.5).roundToLong().toInt()

    private fun rgb(r: Int, g: Int, b: Int) = (0xFF shl 24) or (r shl 16) or (g shl 8) or b
}
