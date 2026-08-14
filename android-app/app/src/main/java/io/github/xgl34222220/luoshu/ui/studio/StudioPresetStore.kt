package io.github.xgl34222220.luoshu.ui.studio

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import java.util.UUID
import kotlinx.coroutines.flow.first
import org.json.JSONArray
import org.json.JSONObject

private val Context.studioPresetDataStore by preferencesDataStore(name = "studio_presets")
private val studioPresetsKey = stringPreferencesKey("presets_json")
private const val STUDIO_PRESET_STORE_SCHEMA = 1
private const val STUDIO_PRESET_MAX_ITEMS = 20

internal data class StoredStudioPreset(
    val id: String,
    val name: String,
    val profileRaw: String,
    val createdAt: Long,
    val updatedAt: Long,
    val lastUsedAt: Long,
    val favorite: Boolean,
)

internal class StudioPresetStore(private val context: Context) {
    suspend fun list(): List<StoredStudioPreset> = readAll().sortedWith(presetOrder)

    suspend fun save(name: String, profileRaw: String): StoredStudioPreset {
        val cleanName = sanitizePresetName(name)
        require(profileRaw.isNotBlank()) { "组合方案不能为空" }
        val now = System.currentTimeMillis()
        val preset = StoredStudioPreset(
            id = UUID.randomUUID().toString(),
            name = cleanName,
            profileRaw = profileRaw,
            createdAt = now,
            updatedAt = now,
            lastUsedAt = 0L,
            favorite = false,
        )
        mutate { current ->
            (listOf(preset) + current)
                .distinctBy { it.id }
                .sortedWith(presetOrder)
                .take(STUDIO_PRESET_MAX_ITEMS)
        }
        return preset
    }

    suspend fun rename(id: String, name: String) {
        val clean = sanitizePresetName(name)
        val now = System.currentTimeMillis()
        mutate { current ->
            current.map { item -> if (item.id == id) item.copy(name = clean, updatedAt = now) else item }
        }
    }

    suspend fun delete(id: String) {
        mutate { current -> current.filterNot { it.id == id } }
    }

    suspend fun touch(id: String) {
        val now = System.currentTimeMillis()
        mutate { current ->
            current.map { item -> if (item.id == id) item.copy(lastUsedAt = now) else item }
        }
    }

    suspend fun toggleFavorite(id: String) {
        val now = System.currentTimeMillis()
        mutate { current ->
            current.map { item ->
                if (item.id == id) item.copy(favorite = !item.favorite, updatedAt = now) else item
            }
        }
    }

    suspend fun replaceAll(items: List<StoredStudioPreset>) {
        context.studioPresetDataStore.edit { preferences ->
            preferences[studioPresetsKey] = encodePresets(
                items.distinctBy { it.id }.sortedWith(presetOrder).take(STUDIO_PRESET_MAX_ITEMS),
            )
        }
    }

    private suspend fun mutate(block: (List<StoredStudioPreset>) -> List<StoredStudioPreset>) {
        context.studioPresetDataStore.edit { preferences ->
            val current = decodePresets(preferences[studioPresetsKey].orEmpty())
            preferences[studioPresetsKey] = encodePresets(
                block(current).sortedWith(presetOrder).take(STUDIO_PRESET_MAX_ITEMS),
            )
        }
    }

    private suspend fun readAll(): List<StoredStudioPreset> {
        val raw = context.studioPresetDataStore.data.first()[studioPresetsKey].orEmpty()
        return decodePresets(raw)
    }
}

internal fun sanitizePresetName(value: String): String = value
    .trim()
    .replace(Regex("[\\r\\n\\t]+"), " ")
    .replace(Regex("\\s{2,}"), " ")
    .take(48)
    .ifBlank { "未命名方案" }

internal fun encodePresets(items: List<StoredStudioPreset>): String {
    val array = JSONArray()
    items.take(STUDIO_PRESET_MAX_ITEMS).forEach { item ->
        array.put(
            JSONObject()
                .put("id", item.id)
                .put("name", item.name)
                .put("profile", JSONObject(item.profileRaw))
                .put("profileRaw", item.profileRaw)
                .put("createdAt", item.createdAt)
                .put("updatedAt", item.updatedAt)
                .put("lastUsedAt", item.lastUsedAt)
                .put("favorite", item.favorite),
        )
    }
    return JSONObject()
        .put("schema", STUDIO_PRESET_STORE_SCHEMA)
        .put("presets", array)
        .toString()
}

internal fun decodePresets(raw: String): List<StoredStudioPreset> {
    if (raw.isBlank()) return emptyList()
    val root = runCatching { JSONObject(raw) }.getOrNull() ?: return emptyList()
    if (root.optInt("schema", -1) != STUDIO_PRESET_STORE_SCHEMA) return emptyList()
    val array = root.optJSONArray("presets") ?: return emptyList()
    val result = mutableListOf<StoredStudioPreset>()
    for (index in 0 until minOf(array.length(), STUDIO_PRESET_MAX_ITEMS)) {
        val item = array.optJSONObject(index) ?: continue
        val id = item.optString("id").trim()
        val rawProfile = item.optString("profileRaw")
        val profile = if (rawProfile.isNotBlank() && runCatching { JSONObject(rawProfile) }.isSuccess) {
            rawProfile
        } else {
            item.optJSONObject("profile")?.toString() ?: continue
        }
        if (id.isBlank()) continue
        result += StoredStudioPreset(
            id = id,
            name = sanitizePresetName(item.optString("name")),
            profileRaw = profile,
            createdAt = item.optLong("createdAt", 0L).coerceAtLeast(0L),
            updatedAt = item.optLong("updatedAt", 0L).coerceAtLeast(0L),
            lastUsedAt = item.optLong("lastUsedAt", 0L).coerceAtLeast(0L),
            favorite = item.optBoolean("favorite", false),
        )
    }
    return result.distinctBy { it.id }.sortedWith(presetOrder)
}

private val presetOrder = compareByDescending<StoredStudioPreset> { it.favorite }
    .thenByDescending { it.lastUsedAt }
    .thenByDescending { it.updatedAt }
    .thenByDescending { it.createdAt }
