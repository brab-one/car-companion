package io.github.deadeyebarb.carcompanion

import android.Manifest
import android.app.Notification
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.IBinder
import android.os.Looper
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.ProcessLifecycleOwner
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

/**
 * Keeps the app connected to the board while it is in the background (Android
 * Auto has the screen in the car) and sends the phone's GPS position to it.
 * When he suggests a route then, a notification opens Google Maps.
 */
class CompanionService : Service() {
    private val jobs = mutableListOf<Job>()
    private val locations = LocationListener { location: Location ->
        if (prefs.sendLocation) companion.sendLocation(location)
    }
    private val prefs get() = companion.prefs

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        ServiceCompat.startForeground(this, NOTIFICATION_ID, notification("Looking for the board ..."),
            ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION)
        companion.start()
        val scope = (application as CompanionApp).scope
        jobs += scope.launch {
            companion.connection.collect { c ->
                val text = if (c.link == Companion.Link.CONNECTED) "Connected to the board (${c.address})"
                else "Looking for the board ..."
                getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, notification(text))
            }
        }
        jobs += scope.launch {
            companion.navigation.collect { nav -> if (!inForeground()) notifyNavigation(nav) }
        }
        val manager = getSystemService(LocationManager::class.java)
        for (provider in listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER)) {
            if (!manager.allProviders.contains(provider)) continue
            try {
                manager.requestLocationUpdates(provider, LOCATION_MS, LOCATION_M, locations, Looper.getMainLooper())
            } catch (_: SecurityException) {
                // the permission was taken back meanwhile: no positions then
            }
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }
        return START_STICKY
    }

    override fun onDestroy() {
        getSystemService(LocationManager::class.java).removeUpdates(locations)
        jobs.forEach { it.cancel() }
        super.onDestroy()
    }

    private fun inForeground() =
        ProcessLifecycleOwner.get().lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)

    private fun notification(text: String): Notification {
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val stop = PendingIntent.getService(this, 1, Intent(this, CompanionService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE)
        return NotificationCompat.Builder(this, CompanionApp.CHANNEL_CONNECTION)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle("Car Companion")
            .setContentText(text)
            .setOngoing(true)
            .setContentIntent(open)
            .addAction(0, "Stop", stop)
            .build()
    }

    private fun notifyNavigation(nav: Companion.Navigation) {
        if (!prefs.openMaps) return
        val intent = if (packageManager.resolveActivity(Maps.intent(nav), 0) != null) Maps.intent(nav)
        else Maps.fallback(nav) ?: return
        val go = PendingIntent.getActivity(this, 2, intent, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val notification = NotificationCompat.Builder(this, CompanionApp.CHANNEL_NAVIGATION)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle("Navigate to ${nav.name}")
            .setContentText("Tap to start Google Maps")
            .setContentIntent(go)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()
        getSystemService(NotificationManager::class.java).notify(NAVIGATION_ID, notification)
    }

    companion object Starter {
        private const val NOTIFICATION_ID = 1
        private const val NAVIGATION_ID = 2
        private const val ACTION_STOP = "stop"
        private const val LOCATION_MS = 2_000L
        private const val LOCATION_M = 5f

        /** Runs only with the location permission: Android requires it for this kind of service. */
        fun start(context: Context) {
            if (ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION)
                != PackageManager.PERMISSION_GRANTED) return
            ContextCompat.startForegroundService(context, Intent(context, CompanionService::class.java))
        }
    }
}
