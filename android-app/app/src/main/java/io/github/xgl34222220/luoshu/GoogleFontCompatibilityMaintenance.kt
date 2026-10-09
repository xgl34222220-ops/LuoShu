package io.github.xgl34222220.luoshu

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Process
import android.util.Log
import androidx.core.content.ContextCompat
import io.github.xgl34222220.luoshu.ui.settings.googleFontCommand
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.json.JSONObject

/** Owns finite maintenance requests, never an Activity or a waiting service. */
internal class GoogleFontCompatibilityMaintenance(
    context: Context,
    private val scope: CoroutineScope,
) {
    private val context = context.applicationContext
    private val appUser = Process.myUid() / 100000
    private val gate = GoogleFontMaintenanceGate()
    private val evidence = GoogleFontDiagnosticEvidence(this.context)
    private val _completion = MutableStateFlow(0L)
    val completion: StateFlow<Long> = _completion.asStateFlow()
    private var registered = false
    private var trustedSnapshot = false
    private var request: Job? = null
    private var closed = false

    private val packageReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent?.action != Intent.ACTION_PACKAGE_REPLACED ||
                intent.data?.scheme != "package" ||
                intent.data?.schemeSpecificPart != GMS_PACKAGE
            ) return
            // This system broadcast is only a trigger. The backend independently
            // verifies the install, package revision and owned undo before writing.
            if (!closed && gate.packageReplaced()) startRequest()
        }
    }

    fun register() {
        if (registered || closed) return
        // Manifest PACKAGE_REPLACED receivers do not run on our API 28+ floor.
        // Cached processes may receive this later; the next foreground pass is
        // the fallback when Android queues it or this process was not alive.
        val filter = IntentFilter(Intent.ACTION_PACKAGE_REPLACED).apply {
            addDataScheme("package")
        }
        try {
            ContextCompat.registerReceiver(
                context,
                packageReceiver,
                filter,
                ContextCompat.RECEIVER_NOT_EXPORTED,
            )
            registered = true
        } catch (error: RuntimeException) {
            // Foreground/boot verification still works if a ROM refuses this
            // optional notification; startup must not fail with the receiver.
            Log.w(TAG, "GMS update event unavailable: ${error.javaClass.simpleName}")
        }
    }

    fun update(snapshot: ModuleSnapshot, resumed: Boolean) {
        if (closed) return
        val trusted = googleFontMaintenanceEligible(
            snapshot.loading, snapshot.statusCached, snapshot.rootGranted,
            snapshot.installed, snapshot.enabled,
        )
        trustedSnapshot = trusted
        if (!trusted) request?.cancel()
        if (gate.update(trusted, resumed)) startRequest()
    }

    fun detachHost() {
        trustedSnapshot = false
        gate.update(trusted = false, resumed = false)
        request?.cancel()
    }

    private fun startRequest() {
        if (closed || !scope.isActive) return
        request = scope.launch {
            var attempted = false
            try {
                if (!trustedSnapshot) return@launch
                attempted = true
                // Preserve the observed state before reconcile can repair it or
                // checkpoint a new revision. A missing/partial diagnostic must
                // never silently become proof that the phone's fonts are fixed.
                try {
                    evidence.captureBeforeMaintenance(appUser)
                } catch (cancelled: CancellationException) {
                    throw cancelled
                } catch (error: Exception) {
                    Log.w(TAG, "Pre-maintenance font evidence unavailable: ${error.javaClass.simpleName}")
                }
                val result = RootShell.exec(
                    googleFontCommand("reconcile-owned", appUser),
                    timeoutMs = 180_000L,
                )
                result.requireCleaned()
                if (result.code != 0) {
                    Log.w(TAG, "Owned Google font maintenance did not complete: code=${result.code}")
                } else {
                    val response = JSONObject(result.stdout.trim())
                    if (response.optString("status") == "error") {
                        Log.w(TAG, "Owned Google font maintenance could not verify component state")
                    } else if (response.optBoolean("recoveredAfterUpgrade", false)) {
                        Log.i(TAG, "Verified owned Google font compatibility after GMS package update")
                    }
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                Log.w(TAG, "Owned Google font maintenance result unavailable: ${error.javaClass.simpleName}")
            } finally {
                if (attempted) _completion.value += 1L
                request = null
                if (!closed && scope.isActive && gate.completed()) startRequest()
            }
        }
    }

    fun close() {
        if (closed) return
        closed = true
        detachHost()
        if (registered) {
            context.unregisterReceiver(packageReceiver)
            registered = false
        }
        request?.cancel()
    }

    private companion object {
        const val GMS_PACKAGE = "com.google.android.gms"
        const val TAG = "LuoShuGoogleFonts"
    }
}
