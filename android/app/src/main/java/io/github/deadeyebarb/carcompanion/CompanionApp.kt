package io.github.deadeyebarb.carcompanion

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob

class CompanionApp : Application() {
    /** All on the main thread: the messages are handled there, in order. */
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    lateinit var companion: Companion
        private set

    override fun onCreate() {
        super.onCreate()
        companion = Companion(this, scope)
        val notifications = getSystemService(NotificationManager::class.java)
        notifications.createNotificationChannel(
            NotificationChannel(CHANNEL_CONNECTION, "Connection to the board", NotificationManager.IMPORTANCE_LOW))
        notifications.createNotificationChannel(
            NotificationChannel(CHANNEL_NAVIGATION, "Navigation he suggests", NotificationManager.IMPORTANCE_HIGH))
    }

    companion object Channels {
        const val CHANNEL_CONNECTION = "connection"
        const val CHANNEL_NAVIGATION = "navigation"
    }
}

val Context.companion: Companion get() = (applicationContext as CompanionApp).companion
