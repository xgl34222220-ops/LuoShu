package io.github.xgl34222220.luoshu

import android.content.Context
import android.util.AtomicFile
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File

internal const val GOOGLE_FONT_DIAGNOSTIC_SCHEMA = "luoshu-google-font-diagnostic-v1"
private const val MAX_DIAGNOSTIC_BYTES = 131_072

/** Pin the read-only helper, phase and App user. Never run a maintenance action here. */
internal fun googleFontDiagnosticCommand(user: Int, phase: String): String {
    require(user in 0..21474)
    require(phase in setOf("before-maintenance", "explicit-report"))
    val path = "/data/adb/modules/LuoShu/common/google_font_diagnostic.sh"
    return "if [ -f ${RootShell.quote(path)} ]; then /system/bin/sh ${RootShell.quote(path)} " +
        "--user $user --phase $phase; else printf '%s\\n' '配套模块缺少复发诊断，请更新模块后重试。' >&2; exit 127; fi"
}

internal fun parseGoogleFontDiagnostic(raw: String, user: Int, phase: String): JSONObject {
    require(raw.toByteArray(Charsets.UTF_8).size <= MAX_DIAGNOSTIC_BYTES) { "诊断报告超出安全大小。" }
    val json = JSONObject(raw.trim())
    require(json.optString("schema") == GOOGLE_FONT_DIAGNOSTIC_SCHEMA) { "复发诊断格式无法核验。" }
    require(json.get("user") is Int && json.getInt("user") == user) { "Android 用户发生变化，报告已拒绝。" }
    require(json.optString("phase") == phase) { "诊断阶段无法核验。" }
    require(json.optLong("capturedAtEpochMs", -1L) > 0L) { "诊断采样时间缺失。" }
    require(json.optJSONObject("collection") != null && json.optJSONObject("component") != null) {
        "诊断关键字段缺失。"
    }
    return json
}

internal fun attachPreviousGoogleFontEvidence(current: JSONObject, previous: JSONObject?): JSONObject {
    val result = JSONObject(current.toString())
    if (previous == null) return result.put("previousSnapshotAvailable", false)
    val age = current.getLong("capturedAtEpochMs") - previous.getLong("capturedAtEpochMs")
    result.put("previousSnapshotAvailable", true)
    result.put("previousSnapshotAgeMs", if (age >= 0L) age else JSONObject.NULL)
    val currentBoot = (current.opt("bootToken") as? String)?.takeIf { it.matches(Regex("[a-f0-9]{20}")) }
    val previousBoot = (previous.opt("bootToken") as? String)?.takeIf { it.matches(Regex("[a-f0-9]{20}")) }
    result.put("previousSnapshotSameBoot", currentBoot != null && currentBoot == previousBoot)
    result.put("previousSnapshot", previous)
    return result
}

/** The preflight lives only in this App's private files; no component/cache write occurs. */
internal class GoogleFontDiagnosticEvidence(context: Context) {
    private val context = context.applicationContext
    private val before = AtomicFile(File(this.context.filesDir, "google-font-before-maintenance.json"))

    private suspend fun collect(user: Int, phase: String): JSONObject {
        val result = RootShell.exec(googleFontDiagnosticCommand(user, phase), timeoutMs = 12_000L)
        result.requireCleaned()
        check(result.code == 0) { result.stderr.ifBlank { "无法取得复发现场，请检查配套模块。" } }
        return parseGoogleFontDiagnostic(result.stdout, user, phase)
    }

    suspend fun captureBeforeMaintenance(user: Int) {
        val snapshot = collect(user, "before-maintenance")
        withContext(Dispatchers.IO) {
            val stream = before.startWrite()
            try {
                stream.write(snapshot.toString().toByteArray(Charsets.UTF_8))
                before.finishWrite(stream)
            } catch (error: Throwable) {
                before.failWrite(stream)
                throw error
            }
        }
    }

    suspend fun export(user: Int): String {
        val current = collect(user, "explicit-report")
        val previous = withContext(Dispatchers.IO) {
            if (!before.baseFile.isFile || before.baseFile.length() > MAX_DIAGNOSTIC_BYTES) null else {
                runCatching {
                    parseGoogleFontDiagnostic(before.readFully().toString(Charsets.UTF_8), user, "before-maintenance")
                }.getOrNull()
            }
        }
        val report = attachPreviousGoogleFontEvidence(current, previous).toString(2)
        val source = withContext(Dispatchers.IO) {
            File.createTempFile("luoshu-google-diagnostic-", ".json", context.cacheDir).also {
                it.writeText(report, Charsets.UTF_8)
            }
        }
        val destination = "/sdcard/LuoShu/reports/LuoShu-google-font-diagnostic-${current.getLong("capturedAtEpochMs")}.json"
        try {
            val result = RootShell.exec(
                "mkdir -p /sdcard/LuoShu/reports && " +
                    "cp ${RootShell.quote(source.absolutePath)} ${RootShell.quote(destination)} && " +
                    "chmod 0644 ${RootShell.quote(destination)} && printf '%s\\n' ${RootShell.quote(destination)}",
                timeoutMs = 15_000L,
            )
            result.requireCleaned()
            check(result.code == 0 && result.stdout.trim() == destination) {
                "现场已采集，但保存到共享存储失败，请重试导出。"
            }
            return destination
        } finally {
            withContext(NonCancellable + Dispatchers.IO) { source.delete() }
        }
    }
}
