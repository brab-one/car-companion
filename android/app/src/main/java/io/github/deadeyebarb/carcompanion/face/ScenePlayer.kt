package io.github.deadeyebarb.carcompanion.face

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlin.math.max
import kotlin.math.min

/**
 * Plays the companion's scenes at the board's own pace, like the page's
 * assets/scene_player.js. Each scene carries the time the board made it
 * (`t`, seconds); the app shows it a fixed moment later, so scenes a bumpy
 * Wi-Fi delivers in bunches still show evenly. The delay adapts: a few tens of
 * ms on a smooth connection, a few hundred on a busy one.
 */
class ScenePlayer(
    private val scope: CoroutineScope,
    private val clock: () -> Double = { System.nanoTime() / 1e9 },
    private val draw: (JsonObject) -> Unit,
) {
    private var offset: Double? = null   // app clock minus board clock, at the best moment of the network seen
    private var jitter = 0.0             // how much later than that scenes have arrived, lately
    private var shown = Double.NEGATIVE_INFINITY
    private var since = clock()

    /** After (re)connecting: the board may have restarted, with a new clock. */
    fun reset() {
        offset = null
        jitter = 0.0
        shown = Double.NEGATIVE_INFINITY
        since = clock()
    }

    /** A scene the board made at its time [t] (without t: shown at once). Call on one thread. */
    fun push(scene: JsonObject, t: Double?) {
        if (t == null) {
            draw(scene)
            return
        }
        val now = clock()
        if (now - since > RESYNC_S) reset()
        val lag = now - t
        val best = offset?.let { min(it, lag) } ?: lag
        offset = best
        jitter = max(lag - best, jitter * DECAY)
        val wait = t + best + min(MAX_S, MIN_S + jitter) - now
        if (wait <= 0) show(scene, t)
        else scope.launch {
            delay((wait * 1000).toLong())
            show(scene, t)
        }
    }

    private fun show(scene: JsonObject, t: Double) {
        if (t < shown) return  // a newer scene is already on the display
        shown = t
        draw(scene)
    }

    private companion object {
        const val MIN_S = 0.03    // the delay on a smooth connection
        const val MAX_S = 0.5     // scenes later than this are shown at once
        const val DECAY = 0.995   // per scene: the delay shrinks again after a bumpy moment
        const val RESYNC_S = 600.0  // the two clocks drift apart a little; start over now and then
    }
}
