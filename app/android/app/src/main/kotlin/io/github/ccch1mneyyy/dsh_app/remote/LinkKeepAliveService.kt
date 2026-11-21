package io.github.ccch1mneyyy.dsh_app.remote

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import io.github.ccch1mneyyy.dsh_app.MainActivity
import io.github.ccch1mneyyy.dsh_app.R
import io.github.ccch1mneyyy.dsh_app.i18n.AppStrings

/**
 * Keeps the process up while a remote host (SSH or relay) is connected and the app is in the
 * background.
 *
 * The local engine runs its own foreground service; a phone that only talks to remote hosts has
 * none, so Android freezes the process as soon as the app leaves the screen and the SSH/relay
 * sockets stop sending their heartbeats. Started on the way out, stopped on the way back or when
 * the link drops. The notification is the system's price for a foreground service: minimal
 * importance, silent, no badge.
 */
class LinkKeepAliveService : Service() {

    private var wakeLock: PowerManager.WakeLock? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }
        ensureChannel(this)
        val notification = build(this)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(ID, notification)
        }
        acquireWakeLock()
        // The system may take the process back; come back only while the app still wants it.
        return START_STICKY
    }

    override fun onTaskRemoved(rootIntent: Intent?) {
        // Swiping the app away means the person is done: no resurrection without the app.
        stopSelf()
        super.onTaskRemoved(rootIntent)
    }

    override fun onDestroy() {
        wakeLock?.let { if (it.isHeld) it.release() }
        wakeLock = null
        super.onDestroy()
    }

    private fun acquireWakeLock() {
        if (wakeLock?.isHeld == true) return
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "dsh-app:remote-link").apply {
            setReferenceCounted(false)
            acquire()
        }
    }

    companion object {
        const val ACTION_START = "io.github.ccch1mneyyy.dsh_app.LINK_KEEPALIVE_START"
        const val ACTION_STOP = "io.github.ccch1mneyyy.dsh_app.LINK_KEEPALIVE_STOP"
        private const val CHANNEL = "remote-link"
        private const val ID = 0x524C

        /** Best effort: Android may refuse a background start with too little grace left. */
        fun start(context: Context) {
            val intent = Intent(context, LinkKeepAliveService::class.java).setAction(ACTION_START)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) context.startForegroundService(intent)
            else context.startService(intent)
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, LinkKeepAliveService::class.java))
        }

        private fun build(context: Context): Notification {
            val open = PendingIntent.getActivity(
                context,
                0,
                Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
            )
            return Notification.Builder(context, CHANNEL)
                .setSmallIcon(R.drawable.ic_stat_dsh)
                .setContentTitle(AppStrings.get(context, R.string.link_keepalive_title))
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .setShowWhen(false)
                .setContentIntent(open)
                .build()
        }

        private fun ensureChannel(context: Context) {
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
            val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            if (nm.getNotificationChannel(CHANNEL) != null) return
            nm.createNotificationChannel(
                NotificationChannel(
                    CHANNEL,
                    AppStrings.get(context, R.string.link_keepalive_channel),
                    NotificationManager.IMPORTANCE_MIN,
                ).apply {
                    setShowBadge(false)
                    setSound(null, null)
                    enableVibration(false)
                },
            )
        }
    }
}
