package io.github.xgl34222220.luoshu.ui.studio

import android.content.Context

internal class StudioProfileBridgeStore(context: Context) {
    private val preferences = context.applicationContext.getSharedPreferences(
        "studio-profile-bridge-v1",
        Context.MODE_PRIVATE,
    )

    fun saveCurrent(raw: String) {
        if (raw.isBlank()) return
        preferences.edit().putString("current", raw).apply()
    }

    fun loadCurrent(): String = preferences.getString("current", "").orEmpty()

    fun savePending(raw: String) {
        if (raw.isBlank()) return
        preferences.edit().putString("pending", raw).apply()
    }

    fun peekPending(): String = preferences.getString("pending", "").orEmpty()

    fun clearPending() {
        preferences.edit().remove("pending").apply()
    }
}
