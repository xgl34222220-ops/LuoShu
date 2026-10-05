package io.github.xgl34222220.luoshu

import android.content.Context
import android.util.AtomicFile
import java.io.File
import org.json.JSONObject

/** Display-only history. Root permission, live mounts and task state are never restored. */
internal class ModuleSnapshotStore(context: Context) {
    private val file = AtomicFile(File(context.applicationContext.filesDir, "module-display-v1.json"))
    private val lock = Any()

    fun load(): ModuleSnapshot? = synchronized(lock) {
        runCatching {
            if (!file.baseFile.isFile || file.baseFile.length() !in 1..16_384L) return@synchronized null
            decodeModuleDisplay(file.openRead().bufferedReader().use { it.readText() })
        }.getOrNull()
    }

    fun save(snapshot: ModuleSnapshot) = synchronized(lock) {
        if (snapshot.loading || snapshot.statusCached || !snapshot.installed || !snapshot.rootGranted) {
            file.delete()
            return@synchronized
        }
        val output = file.startWrite()
        try {
            output.write(encodeModuleDisplay(snapshot).toByteArray(Charsets.UTF_8))
            file.finishWrite(output)
        } catch (error: Throwable) {
            file.failWrite(output)
            throw error
        }
    }
}

internal fun encodeModuleDisplay(snapshot: ModuleSnapshot): String = JSONObject()
    .put("schema", 1)
    .put("version", snapshot.version)
    .put("versionCode", snapshot.versionCode)
    .put("activeFont", snapshot.activeFont)
    .toString()

internal fun decodeModuleDisplay(raw: String): ModuleSnapshot? = runCatching {
    val data = JSONObject(raw)
    if (data.optInt("schema") != 1) return@runCatching null
    val version = data.optString("version").takeIf { it.isNotBlank() && it.length <= 120 }
        ?: return@runCatching null
    val code = data.optInt("versionCode").takeIf { it > 0 } ?: return@runCatching null
    val active = data.optString("activeFont", "default").takeIf { it.isNotBlank() && it.length <= 240 }
        ?: return@runCatching null
    ModuleSnapshot(statusCached = true, version = version, versionCode = code, activeFont = active)
}.getOrNull()
