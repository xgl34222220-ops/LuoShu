package io.github.xgl34222220.luoshu

import android.os.SystemClock
import android.util.Log

/** Local, debug-build timing markers for adb acceptance tests. No names, paths or telemetry. */
internal object FontLoadDiagnostics {
    fun mark(event: String, count: Int? = null, verified: Boolean? = null) {
        if (!BuildConfig.STARTUP_DIAGNOSTICS) return
        val fields = buildString {
            append("event=").append(event)
            append(" elapsed_ms=").append(SystemClock.elapsedRealtime())
            if (count != null) append(" count=").append(count)
            if (verified != null) append(" verified=").append(verified)
        }
        Log.i("LuoShuStartup", fields)
    }
}
