package io.github.xgl34222220.luoshu

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.util.UUID

private const val IMPORT_BRIDGE = "/data/adb/modules/LuoShu/common/app_bridge.sh"
private const val MAX_IMPORT_BYTES = 268_435_456L
private val ALLOWED_EXTENSIONS = setOf("ttf", "otf", "ttc", "zip")

private data class ImportSummary(
    val imported: Int,
    val duplicates: Int,
    val failed: List<String>,
) {
    val title: String
        get() = if (failed.isEmpty()) "导入完成" else "导入结果"

    val message: String
        get() = buildString {
            append("成功导入 ").append(imported).append(" 个文件")
            if (duplicates > 0) append("，跳过 ").append(duplicates).append(" 个重复字体")
            if (failed.isNotEmpty()) {
                append("\n\n失败：\n")
                failed.take(6).forEach { append("• ").append(it).append('\n') }
                if (failed.size > 6) append("其余 ").append(failed.size - 6).append(" 项请查看日志")
            }
        }.trimEnd()
}

@Composable
internal fun NativeImportOverlay(
    viewModel: LuoShuViewModel,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf(false) }
    var summary by remember { mutableStateOf<ImportSummary?>(null) }

    val launcher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenMultipleDocuments(),
    ) { uris ->
        if (uris.isEmpty() || busy) return@rememberLauncherForActivityResult
        busy = true
        scope.launch {
            summary = withContext(Dispatchers.IO) { importDocuments(context.applicationContext, uris) }
            busy = false
            viewModel.refreshFonts(force = true)
        }
    }

    Button(
        onClick = { launcher.launch(arrayOf("*/*")) },
        enabled = viewModel.snapshot.installed && !busy && !viewModel.operationBusy && !viewModel.mixState.busy,
        modifier = modifier,
        shape = RoundedCornerShape(18.dp),
    ) {
        if (busy) {
            CircularProgressIndicator(
                modifier = Modifier.width(18.dp).height(18.dp),
                strokeWidth = 2.dp,
                color = MaterialTheme.colorScheme.onPrimary,
            )
        } else {
            Icon(Icons.Rounded.Add, contentDescription = null)
        }
        Spacer(Modifier.width(7.dp))
        Text(if (busy) "导入中" else "导入字体", fontWeight = FontWeight.Bold)
    }

    summary?.let { result ->
        AlertDialog(
            onDismissRequest = { summary = null },
            title = { Text(result.title, fontWeight = FontWeight.Black) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(result.message)
                    Text(
                        "支持 TTF、OTF、TTC 与字体模块 ZIP。ZIP 只提取字体文件，不执行包内脚本。",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            },
            confirmButton = {
                TextButton(onClick = { summary = null }) { Text("完成") }
            },
        )
    }
}

private suspend fun importDocuments(context: Context, uris: List<Uri>): ImportSummary {
    val cacheDir = File(context.cacheDir, "native_import")
    cacheDir.mkdirs()
    var imported = 0
    var duplicates = 0
    val failed = mutableListOf<String>()

    uris.take(32).forEachIndexed { index, uri ->
        var temp: File? = null
        val displayName = queryDisplayName(context, uri) ?: "font-${index + 1}"
        try {
            val extension = displayName.substringAfterLast('.', "").lowercase()
            require(extension in ALLOWED_EXTENSIONS) { "仅支持 TTF、OTF、TTC 和 ZIP" }
            temp = File(cacheDir, "${System.currentTimeMillis()}-${UUID.randomUUID()}.$extension")
            copyUriWithLimit(context, uri, temp)
            val result = RootShell.exec(
                "sh ${RootShell.quote(IMPORT_BRIDGE)} import_file " +
                    "${RootShell.quote(temp.absolutePath)} ${RootShell.quote(displayName)}",
                timeoutMs = if (extension == "zip") 180_000L else 60_000L,
            )
            if (result.code != 0) error(result.stderr.ifBlank { "Root 导入失败" })
            val root = firstJson(result.stdout)
            if (root.optString("status") != "ok") error(root.optString("message", "导入失败"))
            val duplicate = root.optJSONObject("data")?.optBoolean("duplicate", false) == true
            if (duplicate) duplicates += 1 else imported += 1
        } catch (error: Throwable) {
            failed += "$displayName：${error.message ?: "导入失败"}"
        } finally {
            temp?.delete()
        }
    }
    cacheDir.listFiles()?.filter { it.isFile }?.forEach { file ->
        if (System.currentTimeMillis() - file.lastModified() > 3_600_000L) file.delete()
    }
    return ImportSummary(imported = imported, duplicates = duplicates, failed = failed)
}

private fun queryDisplayName(context: Context, uri: Uri): String? {
    context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
        if (cursor.moveToFirst()) {
            val index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if (index >= 0) return cursor.getString(index)?.substringAfterLast('/')
        }
    }
    return uri.lastPathSegment?.substringAfterLast('/')
}

private fun copyUriWithLimit(context: Context, uri: Uri, target: File) {
    context.contentResolver.openInputStream(uri)?.use { input ->
        FileOutputStream(target).use { output ->
            val buffer = ByteArray(128 * 1024)
            var total = 0L
            while (true) {
                val count = input.read(buffer)
                if (count < 0) break
                total += count
                require(total <= MAX_IMPORT_BYTES) { "文件超过 256 MB 限制" }
                output.write(buffer, 0, count)
            }
            require(total > 0L) { "文件为空" }
            output.fd.sync()
        }
    } ?: error("无法读取所选文件")
}

private fun firstJson(raw: String): JSONObject {
    val line = raw.lineSequence().firstOrNull { it.trimStart().startsWith("{") }
        ?: error("模块没有返回导入结果")
    return JSONObject(line.trim())
}
