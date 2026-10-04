package io.github.deadeyebarb.carcompanion

import android.content.Intent
import android.net.Uri

/** Google Maps' turn-by-turn navigation for "navigate to ..." (PROTOCOL.md, `navigate`). */
object Maps {
    private const val PACKAGE = "com.google.android.apps.maps"

    fun intent(nav: Companion.Navigation): Intent {
        val target = if (nav.lat != null && nav.lon != null) "${nav.lat},${nav.lon}" else Uri.encode(nav.query ?: nav.name)
        return Intent(Intent.ACTION_VIEW, Uri.parse("google.navigation:q=$target")).setPackage(PACKAGE)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    }

    /** Without Google Maps: the link, in a browser. */
    fun fallback(nav: Companion.Navigation): Intent? =
        nav.url?.let { Intent(Intent.ACTION_VIEW, Uri.parse(it)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK) }
}
