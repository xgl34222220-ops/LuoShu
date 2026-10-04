package io.github.xgl34222220.luoshu

import org.json.JSONObject

/** Export only bounded numeric protocol fields; stderr also contains private scope identities. */
internal fun inventoryTimingFields(action: String, stderr: String): List<String> {
    if (action !in setOf("cached", "preview", "scan", "refresh", "fingerprint")) return emptyList()
    val inventory = Regex("\\[font-inventory] stage=$action elapsed_ms=([0-9]+(?:[.][0-9]{1,3})?) count=([0-9]+) code=([0-9]+)")
    val fields = linkedMapOf<String, String>()
    for (line in stderr.lineSequence()) {
        if (line.length > 2_048) continue
        val match = inventory.matchEntire(line)
        if (match != null) {
            val duration = match.groupValues[1].toDoubleOrNull() ?: continue
            val count = match.groupValues[2].toIntOrNull() ?: continue
            val code = match.groupValues[3].toIntOrNull() ?: continue
            if (duration.isFinite() && duration in 0.0..180_000.0 && count >= 0 && code in 0..255) {
                fields["inventory"] = "phase=inventory duration_ms=$duration count=$count code=$code"
            }
        } else if (line.startsWith("[font-request] {")) {
            val root = runCatching { JSONObject(line.removePrefix("[font-request] ")) }.getOrNull() ?: continue
            if (root.opt("event") != "finished") continue
            val duration = (root.opt("elapsed_ms") as? Number)?.toDouble() ?: continue
            val code = (root.opt("code") as? Int) ?: continue
            val cleaned = (root.opt("cleaned") as? Boolean) ?: continue
            val reason = root.opt("reason") as? String ?: continue
            if (duration.isFinite() && duration in 0.0..180_000.0 && code in 0..255 &&
                reason in setOf("success", "worker-error", "cancel", "timeout", "client-disconnect", "error")) {
                fields["scope"] = "phase=scope duration_ms=$duration code=$code cleaned=$cleaned reason=$reason"
            }
        }
        if (fields.size == 2) break
    }
    return fields.values.toList()
}
