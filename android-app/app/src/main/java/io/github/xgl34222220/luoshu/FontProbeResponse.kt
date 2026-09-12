package io.github.xgl34222220.luoshu

import org.json.JSONObject

/** Font tools report their structured errors on stdout, including nonzero exits. */
internal fun parseFontProbeResponse(result: ShellResult, fallback: String): JSONObject {
    val root = result.stdout.lineSequence()
        .map(String::trim)
        .filter { it.startsWith("{") }
        .mapNotNull { runCatching { JSONObject(it) }.getOrNull() }
        .firstOrNull { it.has("status") }
    if (result.code != 0 || root?.optString("status") != "ok") {
        val message = root?.optString("message")?.takeIf(String::isNotBlank)
            ?: result.stderr.trim().takeIf(String::isNotBlank)
            ?: fallback
        error(message)
    }
    return root
}
