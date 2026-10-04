package io.github.xgl34222220.luoshu

import org.json.JSONObject

/** Export only bounded numeric protocol fields; stderr also contains private scope identities. */
internal fun inventoryTimingFields(action: String, stderr: String): List<String> {
    if (action !in setOf("cached", "preview", "scan", "refresh", "fingerprint")) return emptyList()
    val inventory = Regex("\\[font-inventory] stage=$action elapsed_ms=([0-9]+(?:[.][0-9]{1,3})?) count=([0-9]+) code=([0-9]+)")
    val phaseNames = listOf("storage", "snapshot", "cache", "build", "verify", "write", "output")
    val detail = Regex("\\[font-inventory-detail] stage=$action " +
        phaseNames.joinToString(" ") { "${it}_ms=([0-9]+(?:[.][0-9]{1,3})?)" } +
        " cache_hit=([01]) snapshot_count=([0-9]+) build_count=([0-9]+) write_count=([0-9]+) code=([0-9]+)")
    val fields = linkedMapOf<String, String>()
    for (line in stderr.lineSequence()) {
        if (line.length > 2_048) continue
        val match = inventory.matchEntire(line)
        val detailMatch = detail.matchEntire(line)
        if (match != null) {
            val duration = match.groupValues[1].toDoubleOrNull() ?: continue
            val count = match.groupValues[2].toIntOrNull() ?: continue
            val code = match.groupValues[3].toIntOrNull() ?: continue
            if (duration.isFinite() && duration in 0.0..180_000.0 && count >= 0 && code in 0..255) {
                fields["inventory"] = "phase=inventory duration_ms=$duration count=$count code=$code"
            }
        } else if (detailMatch != null) {
            val durations = (1..7).map { detailMatch.groupValues[it].toDoubleOrNull() ?: Double.NaN }
            val counters = (8..12).map { detailMatch.groupValues[it].toIntOrNull() ?: -1 }
            if (durations.all { it.isFinite() && it in 0.0..180_000.0 } &&
                counters[0] in 0..1 && counters[1] in 0..2 && counters[2] in 0..1 &&
                counters[3] in 0..2 && counters[4] in 0..255) {
                fields["inventory_detail"] = "phase=inventory_detail " +
                    phaseNames.mapIndexed { index, name -> "${name}_ms=${durations[index]}" }.joinToString(" ") +
                    " cache_hit=${counters[0]} snapshot_count=${counters[1]} build_count=${counters[2]} write_count=${counters[3]} code=${counters[4]}"
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
        if (fields.size == 3) break
    }
    return fields.values.toList()
}
