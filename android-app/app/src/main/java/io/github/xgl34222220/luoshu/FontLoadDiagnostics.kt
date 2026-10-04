package io.github.xgl34222220.luoshu

import android.os.SystemClock
import android.util.Log

/** Local, debug-build timing markers for adb acceptance tests. No names, paths or telemetry. */
internal object FontLoadDiagnostics {
    fun inventoryStages(stage: String, result: ShellResult) {
        if (!BuildConfig.STARTUP_DIAGNOSTICS) return
        inventoryTimingFields(stage, result.stderr).forEach {
            Log.i("LuoShuStartup", "event=font_request_phase stage=$stage $it")
        }
    }

    fun axisRequest(durationMs: Long, result: ShellResult) {
        if (!BuildConfig.STARTUP_DIAGNOSTICS) return
        Log.i("LuoShuAxis", "event=axis_request duration_ms=$durationMs code=${result.code} stdout_bytes=${result.stdout.toByteArray(Charsets.UTF_8).size}")
        // Only our bounded numeric stage markers are accepted. No font IDs,
        // paths, font metadata, or arbitrary command errors enter local logs.
        result.stderr.lineSequence().filter {
            it.matches(Regex("axis_stage=(source_start|source_ready|metadata_start|metadata_end) uptime=[0-9]+[.][0-9]+"))
        }.take(4).forEach { Log.i("LuoShuAxis", it) }
    }

    fun applyRequest(stage: String, durationMs: Long, code: Int) {
        if (!BuildConfig.STARTUP_DIAGNOSTICS) return
        Log.i("LuoShuStartup", "event=font_apply_request stage=$stage elapsed_ms=${SystemClock.elapsedRealtime()} duration_ms=$durationMs code=$code")
    }

    fun request(stage: String, durationMs: Long, code: Int) {
        if (!BuildConfig.STARTUP_DIAGNOSTICS) return
        Log.i("LuoShuStartup", "event=font_request stage=$stage elapsed_ms=${SystemClock.elapsedRealtime()} duration_ms=$durationMs code=$code")
    }

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
