package io.github.xgl34222220.luoshu.ui.logs

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.RootShell
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle

internal data class DiagnosticExportState(
    val busy: Boolean = false,
    val path: String = "",
    val error: String = "",
) {
    val resultVisible: Boolean get() = path.isNotBlank() || error.isNotBlank()
}

internal suspend fun exportSanitizedDiagnostic(): DiagnosticExportState {
    val command = """
        MOD=/data/adb/modules/LuoShu
        CFG="${'$'}MOD/config"
        LOG="${'$'}MOD/logs/fontswitch.log"
        OUT_DIR=/sdcard/LuoShu/reports
        OUT="${'$'}OUT_DIR/LuoShu-diagnostic-summary.txt"
        mkdir -p "${'$'}OUT_DIR" 2>/dev/null || exit 20
        read_value() {
            sed -n "s/^${'$'}2=//p" "${'$'}1" 2>/dev/null | head -n1 | tr -d '\r\n'
        }
        version="${'$'}(read_value "${'$'}MOD/module.prop" version)"
        versionCode="${'$'}(read_value "${'$'}MOD/module.prop" versionCode)"
        active="${'$'}(head -n1 "${'$'}CFG/active_font.conf" 2>/dev/null | tr -d '\r\n')"
        case "${'$'}active" in
            ''|default) activeType=default ;;
            mix) activeType=composite ;;
            *) activeType=custom ;;
        esac
        inventory=missing
        [ -s "${'$'}CFG/device_font_inventory.json" ] && inventory=available
        engine="${'$'}(read_value "${'$'}CFG/device-font-engine.conf" state)"
        template="${'$'}(read_value "${'$'}CFG/device-font-template.state" state)"
        alignment="${'$'}(read_value "${'$'}CFG/device-font-load-verification.conf" state)"
        alignmentMode="${'$'}(read_value "${'$'}CFG/device-font-load-verification.conf" mode)"
        cachePending=no
        [ -s "${'$'}CFG/device-font-cache-pending.conf" ] && cachePending=yes
        rootManager=Root
        if command -v apd >/dev/null 2>&1 || [ -d /data/adb/apatch ]; then
            rootManager=APatch
        elif command -v ksud >/dev/null 2>&1 || [ -d /data/adb/ksu ]; then
            rootManager=KernelSU
        elif command -v magisk >/dev/null 2>&1 || [ -d /data/adb/magisk ]; then
            rootManager=Magisk
        fi
        mountEngine=unknown
        if [ -f "${'$'}MOD/common/mount_compat.sh" ]; then
            . "${'$'}MOD/common/mount_compat.sh" >/dev/null 2>&1 || true
            if type luoshu_detect_mount_engine >/dev/null 2>&1; then
                mountEngine="${'$'}(luoshu_detect_mount_engine 2>/dev/null)"
            fi
        fi
        warningCount="${'$'}(tail -n 500 "${'$'}LOG" 2>/dev/null | grep -Eic 'warn|警告' 2>/dev/null)"
        errorCount="${'$'}(tail -n 500 "${'$'}LOG" 2>/dev/null | grep -Eic 'error|failed|失败|错误' 2>/dev/null)"
        [ -n "${'$'}warningCount" ] || warningCount=0
        [ -n "${'$'}errorCount" ] || errorCount=0
        {
            printf 'report=luoshu-sanitized-diagnostic-v1\n'
            printf 'time=%s\n' "${'$'}(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)"
            printf 'moduleVersion=%s\n' "${'$'}{version:-unknown}"
            printf 'moduleVersionCode=%s\n' "${'$'}{versionCode:-0}"
            printf 'activeFontType=%s\n' "${'$'}activeType"
            printf 'inventory=%s\n' "${'$'}inventory"
            printf 'engineState=%s\n' "${'$'}{engine:-missing}"
            printf 'templateState=%s\n' "${'$'}{template:-missing}"
            printf 'alignmentState=%s\n' "${'$'}{alignment:-pending}"
            printf 'alignmentMode=%s\n' "${'$'}{alignmentMode:-compatibility}"
            printf 'cachePending=%s\n' "${'$'}cachePending"
            printf 'rootManager=%s\n' "${'$'}rootManager"
            printf 'mountEngine=%s\n' "${'$'}mountEngine"
            printf 'androidSdk=%s\n' "${'$'}(getprop ro.build.version.sdk 2>/dev/null)"
            printf 'recentWarningCount=%s\n' "${'$'}warningCount"
            printf 'recentErrorCount=%s\n' "${'$'}errorCount"
            printf 'privacy=device fingerprint, serial, model, font names, filenames and private paths omitted\n'
        } > "${'$'}OUT" 2>/dev/null || exit 21
        chmod 0644 "${'$'}OUT" 2>/dev/null || true
        printf '%s\n' "${'$'}OUT"
    """.trimIndent()
    val result = RootShell.exec(command, timeoutMs = 20_000L)
    if (result.code != 0) {
        return DiagnosticExportState(error = result.stderr.ifBlank { "脱敏诊断报告生成失败" })
    }
    val path = result.stdout.lineSequence().lastOrNull { it.trim().startsWith("/") }?.trim().orEmpty()
    return if (path.isBlank()) {
        DiagnosticExportState(error = "报告已执行，但没有返回保存路径")
    } else {
        DiagnosticExportState(path = path)
    }
}

@Composable
internal fun DiagnosticExportButton(
    style: UiStyle,
    state: DiagnosticExportState,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        onClick = onClick,
        enabled = !state.busy,
        modifier = modifier.size(52.dp),
        shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 18.dp else 17.dp),
        color = MaterialTheme.colorScheme.surfaceContainerHigh,
        contentColor = MaterialTheme.colorScheme.primary,
        shadowElevation = 6.dp,
    ) {
        Box(contentAlignment = Alignment.Center) {
            if (state.busy) {
                CircularProgressIndicator(Modifier.size(21.dp), strokeWidth = 2.dp)
            } else {
                Icon(Icons.Rounded.Description, contentDescription = "生成脱敏诊断报告")
            }
        }
    }
}

@Composable
internal fun DiagnosticExportDialog(
    style: UiStyle,
    state: DiagnosticExportState,
    onDismiss: () -> Unit,
) {
    val failed = state.error.isNotBlank()
    AlertDialog(
        onDismissRequest = onDismiss,
        shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 34.dp else 28.dp),
        icon = {
            Icon(
                if (failed) Icons.Rounded.Warning else Icons.Rounded.CheckCircle,
                contentDescription = null,
                tint = if (failed) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary,
            )
        },
        title = {
            Text(if (failed) "诊断报告生成失败" else "脱敏诊断报告已生成", fontWeight = FontWeight.Black)
        },
        text = {
            Column(Modifier.fillMaxWidth()) {
                Text(
                    if (failed) state.error else "报告只包含引擎状态和错误数量，不包含设备指纹、序列号、型号、字体名称、字体文件名或私人路径。",
                    color = if (failed) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 12.sp,
                )
                if (!failed) {
                    Spacer(Modifier.size(12.dp))
                    Surface(
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(18.dp),
                        color = MaterialTheme.colorScheme.surfaceContainer,
                    ) {
                        Row(Modifier.padding(13.dp), verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Rounded.Description, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                            Spacer(Modifier.width(9.dp))
                            Text(state.path, modifier = Modifier.weight(1f), fontSize = 11.sp, fontWeight = FontWeight.Medium)
                        }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("完成") } },
    )
}
