package io.github.xgl34222220.luoshu.ui.logs

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.AppFontTaskTimings
import io.github.xgl34222220.luoshu.RootShell
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens
import io.github.xgl34222220.luoshu.ui.theme.LuoShuHeaderAction
import io.github.xgl34222220.luoshu.ui.theme.LuoShuSmoothShape
import io.github.xgl34222220.luoshu.ui.theme.luoShuGlassHighlight

internal data class DiagnosticExportState(
    val busy: Boolean = false,
    val path: String = "",
    val error: String = "",
    val xmlParity: String = "",
    val shadowedByUpdatableFont: String = "",
    val fontAudit: String = "",
) {
    val resultVisible: Boolean get() = path.isNotBlank() || error.isNotBlank()
}

internal suspend fun exportSanitizedDiagnostic(): DiagnosticExportState {
    val taskTiming = RootShell.quote(AppFontTaskTimings.sanitizedSnapshot())
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
        safe_uint() {
            case "${'$'}1" in ''|*[!0-9]*) printf unknown ;; *) printf '%s' "${'$'}1" ;; esac
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
        legacyMode=no
        [ -f "${'$'}CFG/font_runtime_legacy_v14_4.conf" ] && legacyMode=yes
        stockScanPending=no
        [ -f "${'$'}CFG/stock_inventory_scan_pending" ] && stockScanPending=yes
        templatePresent=no
        [ -s "${'$'}CFG/device-font-template.json" ] && templatePresent=yes
        templatePending="${'$'}(read_value "${'$'}CFG/device-font-template-pending.conf" state)"
        case "${'$'}templatePending" in ''|pending-stock-boot) ;; *) templatePending=unknown ;; esac
        templatePendingReason="${'$'}(read_value "${'$'}CFG/device-font-template-pending.conf" reason)"
        case "${'$'}templatePendingReason" in
            '') templatePendingReason=none ;;
            active-font:*) templatePendingReason=active-font ;;
            payload-transaction:*) templatePendingReason=payload-transaction ;;
            module-font-payload:*) templatePendingReason=module-font-payload ;;
            module-xml-payload:*) templatePendingReason=module-xml-payload ;;
            device-payload-installed|template-capture-busy) ;;
            *) templatePendingReason=unknown ;;
        esac
        bootScanResult="${'$'}(read_value "${'$'}CFG/boot-stock-scan.state" result)"
        case "${'$'}bootScanResult" in success|busy|timeout|cleanup-pending|failed) ;; *) bootScanResult=unknown ;; esac
        bootScanPublished="${'$'}(read_value "${'$'}CFG/boot-stock-scan.state" inventoryPublished)"
        case "${'$'}bootScanPublished" in yes|no) ;; *) bootScanPublished=unknown ;; esac
        bootScanSchema="${'$'}(read_value "${'$'}CFG/boot-stock-scan.state" schema)"
        bootScanBudget="${'$'}(safe_uint "${'$'}(read_value "${'$'}CFG/boot-stock-scan.state" budgetSeconds)")"
        bootScanElapsed="${'$'}(safe_uint "${'$'}(read_value "${'$'}CFG/boot-stock-scan.state" elapsedSeconds)")"
        bootScanCurrentBoot=unknown
        if [ "${'$'}bootScanSchema" = luoshu-boot-stock-scan-v1 ]; then
            scanBoot="${'$'}(read_value "${'$'}CFG/boot-stock-scan.state" bootId)"
            currentBoot="${'$'}(head -n1 /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n')"
            if [ -n "${'$'}scanBoot" ] && [ -n "${'$'}currentBoot" ]; then
                bootScanCurrentBoot=no
                [ "${'$'}scanBoot" != "${'$'}currentBoot" ] || bootScanCurrentBoot=yes
            fi
        else
            bootScanSchema=unknown
            bootScanResult=unknown
            bootScanPublished=unknown
            bootScanBudget=unknown
            bootScanElapsed=unknown
        fi
        payloadBootState="${'$'}(read_value "${'$'}CFG/font-payload-boot.conf" state)"
        case "${'$'}payloadBootState" in prepared|booting|confirmed|failed) ;; *) payloadBootState=unknown ;; esac
        rebootPending=no
        [ -f "${'$'}CFG/text_reboot_required.conf" ] && rebootPending=yes
        bootComplete="${'$'}(getprop sys.boot_completed 2>/dev/null)"
        case "${'$'}bootComplete" in 0|1) ;; *) bootComplete=unknown ;; esac
        uptimeSeconds="${'$'}(cut -d. -f1 /proc/uptime 2>/dev/null)"
        alignment="${'$'}(read_value "${'$'}CFG/device-font-load-verification.conf" state)"
        alignmentMode="${'$'}(read_value "${'$'}CFG/device-font-load-verification.conf" mode)"
        alignmentReason="${'$'}(read_value "${'$'}CFG/device-font-load-verification.conf" reason)"
        selfMountState="${'$'}(read_value "${'$'}CFG/self-mount.conf" state)"
        selfMountBackend="${'$'}(read_value "${'$'}CFG/self-mount.conf" backend)"
        selfMountFailed="${'$'}(read_value "${'$'}CFG/self-mount.conf" failed)"
        moduleDirectory=missing
        [ -d "${'$'}MOD" ] && moduleDirectory=present
        pendingModuleDirectory=missing
        [ -d /data/adb/modules_update/LuoShu ] && pendingModuleDirectory=present
        postMountScript=missing
        [ -f "${'$'}MOD/post-mount.sh" ] && postMountScript=present
        cacheState=none
        if [ -s "${'$'}CFG/device-font-cache-pending.conf" ]; then
            cacheState="${'$'}(MODDIR="${'$'}MOD" MODULE_DIR="${'$'}MOD" sh "${'$'}MOD/common/device_font_cache.sh" state 2>/dev/null | sed -n 's/^cacheState=//p' | head -n1)"
            [ -n "${'$'}cacheState" ] || cacheState=pending
        fi
        cachePending=no
        [ "${'$'}cacheState" = pending ] && cachePending=yes
        rootManager=Root
        if command -v apd >/dev/null 2>&1 || [ -d /data/adb/ap ] || [ -d /data/adb/apatch ]; then
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
        foreignFontModules="${'$'}(read_value "${'$'}CFG/foreign-font-modules.conf" foreignFontModules)"
        fontLoaderPresent="${'$'}(read_value "${'$'}CFG/foreign-font-modules.conf" fontLoaderPresent)"
        warningCount="${'$'}(tail -n 500 "${'$'}LOG" 2>/dev/null | grep -Eic 'warn|警告' 2>/dev/null)"
        errorCount="${'$'}(tail -n 500 "${'$'}LOG" 2>/dev/null | grep -Eic '(^|[^A-Za-z])(errors?|failed)([^A-Za-z]|$)|失败|错误' 2>/dev/null)"
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
            printf 'legacyMode=%s\n' "${'$'}legacyMode"
            printf 'stockScanPending=%s\n' "${'$'}stockScanPending"
            printf 'templatePresent=%s\n' "${'$'}templatePresent"
            printf 'templateCaptureRevision=%s\n' "${'$'}(safe_uint "${'$'}(read_value "${'$'}CFG/device-font-template.state" captureRevision)")"
            printf 'templatePendingState=%s\n' "${'$'}{templatePending:-none}"
            printf 'templatePendingReason=%s\n' "${'$'}templatePendingReason"
            printf 'bootScanResult=%s\n' "${'$'}bootScanResult"
            printf 'bootScanReceiptSchema=%s\n' "${'$'}bootScanSchema"
            printf 'bootScanCurrentBoot=%s\n' "${'$'}bootScanCurrentBoot"
            printf 'bootScanBudgetSeconds=%s\n' "${'$'}bootScanBudget"
            printf 'bootScanElapsedSeconds=%s\n' "${'$'}bootScanElapsed"
            printf 'bootScanInventoryPublished=%s\n' "${'$'}bootScanPublished"
            printf 'bootScanTimingScope=stock-scan-launcher-including-cleanup; not phone boot duration\n'
            printf 'payloadBootState=%s\n' "${'$'}payloadBootState"
            printf 'rebootPending=%s\n' "${'$'}rebootPending"
            printf 'sysBootCompleted=%s\n' "${'$'}bootComplete"
            printf 'uptimeSeconds=%s\n' "${'$'}(safe_uint "${'$'}uptimeSeconds")"
            printf 'alignmentState=%s\n' "${'$'}{alignment:-pending}"
            printf 'alignmentMode=%s\n' "${'$'}{alignmentMode:-compatibility}"
            printf 'alignmentReason=%s\n' "${'$'}{alignmentReason:-none}"
            printf 'selfMountState=%s\n' "${'$'}{selfMountState:-missing}"
            printf 'selfMountBackend=%s\n' "${'$'}{selfMountBackend:-missing}"
            printf 'selfMountFailed=%s\n' "${'$'}{selfMountFailed:-none}"
            printf 'moduleDirectory=%s\n' "${'$'}moduleDirectory"
            printf 'pendingModuleDirectory=%s\n' "${'$'}pendingModuleDirectory"
            printf 'postMountScript=%s\n' "${'$'}postMountScript"
            printf 'cachePending=%s\n' "${'$'}cachePending"
            printf 'cacheState=%s\n' "${'$'}cacheState"
            printf 'rootManager=%s\n' "${'$'}rootManager"
            printf 'mountEngine=%s\n' "${'$'}mountEngine"
            printf 'foreignFontModules=%s\n' "${'$'}{foreignFontModules:-none}"
            printf 'fontLoaderPresent=%s\n' "${'$'}{fontLoaderPresent:-unknown}"
            printf 'androidSdk=%s\n' "${'$'}(getprop ro.build.version.sdk 2>/dev/null)"
            printf 'recentWarningCount=%s\n' "${'$'}warningCount"
            printf 'recentErrorCount=%s\n' "${'$'}errorCount"
            printf 'privacy=device identifiers, accounts, chat content and source font names omitted; system slots and APK font resource names may be included\n'
        } > "${'$'}OUT" 2>/dev/null || exit 21
        printf '\n[app-font-task-timing]\n%s' $taskTiming >> "${'$'}OUT"
        LAYOUT_HELPER="${'$'}MOD/common/font_layout_diagnostic.sh"
        LAYOUT_OUT="${'$'}OUT_DIR/LuoShu-font-layout.json"
        if [ -f "${'$'}LAYOUT_HELPER" ]; then
            if MODDIR="${'$'}MOD" sh "${'$'}LAYOUT_HELPER" --output "${'$'}LAYOUT_OUT" >/dev/null 2>&1; then
                printf '\n[font-layout]\n' >> "${'$'}OUT"
                cat "${'$'}LAYOUT_OUT" >> "${'$'}OUT"
            else
                printf '\nlayoutDiagnostic=unavailable\n' >> "${'$'}OUT"
            fi
        else
            printf '\nlayoutDiagnostic=module-helper-missing\n' >> "${'$'}OUT"
        fi
        PARITY_HELPER="${'$'}MOD/common/device_font_load_verify.sh"
        if [ -f "${'$'}PARITY_HELPER" ]; then
            MODDIR="${'$'}MOD" MODULE_DIR="${'$'}MOD" sh "${'$'}PARITY_HELPER" parity >/dev/null 2>&1 || true
        fi
        xmlParity="${'$'}(read_value "${'$'}CFG/device-font-xml-parity.conf" xmlParity | tr -cd 'A-Za-z0-9._@#+:;,=()-' | cut -c1-600)"
        case "${'$'}xmlParity" in ok|mismatch:*|unknown:*) ;; '') xmlParity=not-collected ;; *) xmlParity=unknown ;; esac
        shadowedFont="${'$'}(read_value "${'$'}CFG/device-font-xml-parity.conf" shadowedByUpdatableFont | tr -cd 'A-Za-z0-9._@#+,-' | cut -c1-300)"
        [ -n "${'$'}shadowedFont" ] || shadowedFont=not-collected
        printf '\n[xml-parity]\nxmlParity=%s\nshadowedByUpdatableFont=%s\n' "${'$'}xmlParity" "${'$'}shadowedFont" >> "${'$'}OUT"
        if [ -f "${'$'}PARITY_HELPER" ]; then
            MODDIR="${'$'}MOD" MODULE_DIR="${'$'}MOD" sh "${'$'}PARITY_HELPER" audit >/dev/null 2>&1 || true
        fi
        fontAudit="${'$'}(read_value "${'$'}CFG/device-font-process-audit.conf" fontAudit | tr -cd 'A-Za-z0-9._:,=/-' | cut -c1-300)"
        case "${'$'}fontAudit" in ok|gap:*|unknown:*|inactive:*) ;; '') fontAudit=not-collected ;; *) fontAudit=unknown ;; esac
        printf '\n[font-audit]\nfontAudit=%s\n' "${'$'}fontAudit" >> "${'$'}OUT"
        grep -E '^[A-Za-z]+[.][A-Za-z]+=' "${'$'}CFG/device-font-process-audit.conf" 2>/dev/null | head -n 80 \
            | tr -cd 'A-Za-z0-9._@#+/:;,=()\n-' | cut -c1-1200 >> "${'$'}OUT"
        chmod 0644 "${'$'}OUT" 2>/dev/null || true
        printf 'xmlParity=%s\n' "${'$'}xmlParity"
        printf 'shadowedByUpdatableFont=%s\n' "${'$'}shadowedFont"
        printf 'fontAudit=%s\n' "${'$'}fontAudit"
        printf '%s\n' "${'$'}OUT"
    """.trimIndent()
    val result = RootShell.exec(command, timeoutMs = 45_000L)
    if (result.code != 0) {
        return DiagnosticExportState(error = result.stderr.ifBlank { "脱敏诊断报告生成失败" })
    }
    val path = result.stdout.lineSequence().lastOrNull { it.trim().startsWith("/") }?.trim().orEmpty()
    val lines = result.stdout.lineSequence().map { it.trim() }.toList()
    val xmlParity = lines.lastOrNull { it.startsWith("xmlParity=") }?.substringAfter('=').orEmpty()
    val shadowed = lines.lastOrNull { it.startsWith("shadowedByUpdatableFont=") }?.substringAfter('=').orEmpty()
    val fontAudit = lines.lastOrNull { it.startsWith("fontAudit=") }?.substringAfter('=').orEmpty()
    return if (path.isBlank()) {
        DiagnosticExportState(error = "报告已执行，但没有返回保存路径")
    } else {
        DiagnosticExportState(
            path = path,
            xmlParity = xmlParity,
            shadowedByUpdatableFont = shadowed,
            fontAudit = fontAudit,
        )
    }
}

/** One-line conclusion for the FontManager / fonts.xml / font_fallback.xml parity check. */
internal fun xmlParityConclusion(xmlParity: String, shadowedByUpdatableFont: String): String {
    if (xmlParity.isBlank()) return ""
    val parity = when {
        xmlParity == "ok" -> "三路字体配置一致（FontManager / fonts.xml / font_fallback.xml）"
        xmlParity.startsWith("mismatch:") && xmlParity.contains("stock-inode:") ->
            "三路字体配置文件名一致，但仍指向原厂文件（同名不同 inode），详见报告 xmlParity"
        xmlParity.startsWith("mismatch:") -> "三路字体配置不一致：浏览器或内嵌网页可能与系统显示不同，详见报告 xmlParity"
        else -> "三路字体配置一致性未能采集"
    }
    val shadow = shadowedByUpdatableFont.trim()
    val unknown = setOf("", "none", "unknown", "not-collected")
    return if (shadow in unknown) parity else "${parity}；被系统热更新字体遮盖：${shadow}"
}

private val fontAuditProcessLabels = mapOf(
    "systemServer" to "system_server",
    "systemui" to "SystemUI",
    "launcher" to "桌面",
    "webview" to "WebView",
)

/** Processes whose stock mappings are expected (font server, Chromium per-script fonts). */
private val fontAuditServerLike = setOf("systemServer", "webview")

/**
 * One-line conclusion for the per-process font audit (`fontAudit=ok|gap:<proc>=N/M,...`),
 * where N = stock font files still mapped and M = of those, slots LuoShu replaced.
 */
internal fun fontAuditConclusion(fontAudit: String): String {
    val value = fontAudit.trim()
    return when {
        value.isBlank() || value == "not-collected" -> ""
        value == "ok" -> "按进程字体审计：SystemUI / 桌面未发现仍加载的原厂字体文件"
        value.startsWith("inactive:") -> "按进程字体审计：当前没有洛书字体负载，已跳过"
        value.startsWith("gap:") -> {
            val parts = value.removePrefix("gap:").split(',').mapNotNull { item ->
                val name = item.substringBefore('=')
                val counts = item.substringAfter('=', "").split('/')
                val stock = counts.getOrNull(0)?.toIntOrNull() ?: return@mapNotNull null
                val slot = counts.getOrNull(1)?.toIntOrNull() ?: 0
                val label = fontAuditProcessLabels[name] ?: return@mapNotNull null
                when {
                    name in fontAuditServerLike && slot > 0 -> "${label} 仍加载已替换槽位的原厂字体 ${slot} 个"
                    name in fontAuditServerLike -> null
                    slot > 0 -> "${label} 仍加载原厂字体 ${stock} 个（其中 ${slot} 个是洛书已替换的槽位）"
                    stock > 0 -> "${label} 仍加载原厂字体 ${stock} 个"
                    else -> null
                }
            }
            if (parts.isEmpty()) "按进程字体审计：结果无法解析，详见报告 [font-audit]" else parts.joinToString("；")
        }
        else -> "按进程字体审计未能采集"
    }
}

@Composable
internal fun DiagnosticExportButton(
    style: UiStyle,
    state: DiagnosticExportState,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    LuoShuHeaderAction(
        icon = Icons.Rounded.Description,
        contentDescription = "生成脱敏诊断报告",
        onClick = onClick,
        enabled = !state.busy,
        loading = state.busy,
        containerColor = LocalMiuixTokens.current.elevatedCardBackground,
        modifier = modifier,
        opticalScale = .96f,
    )
}

@Composable
internal fun DiagnosticExportDialog(
    style: UiStyle,
    state: DiagnosticExportState,
    onDismiss: () -> Unit,
) {
    val failed = state.error.isNotBlank()
    val tokens = LocalMiuixTokens.current
    val shape = LuoShuSmoothShape(34.dp)
    AlertDialog(
        onDismissRequest = onDismiss,
        modifier = Modifier.shadow(tokens.cardShadowElevation, shape)
            .luoShuGlassHighlight(shape).border(1.dp, tokens.glassOutlineBrush, shape),
        shape = shape,
        containerColor = tokens.glassDialogColor,
        tonalElevation = 0.dp,
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
                    if (failed) state.error else "报告包含引擎状态、字体度量、系统字体槽位及相关应用的字体资源信息，用于排查偏移和漏替换。不包含设备标识、账号或聊天内容。",
                    color = if (failed) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 12.sp,
                )
                val parityLine = if (failed) "" else xmlParityConclusion(state.xmlParity, state.shadowedByUpdatableFont)
                if (parityLine.isNotBlank()) {
                    Spacer(Modifier.size(8.dp))
                    Text(
                        parityLine,
                        color = if (state.xmlParity.startsWith("mismatch:") || parityLine.contains('；')) {
                            MaterialTheme.colorScheme.error
                        } else {
                            MaterialTheme.colorScheme.onSurfaceVariant
                        },
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Medium,
                    )
                }
                val auditLine = if (failed) "" else fontAuditConclusion(state.fontAudit)
                if (auditLine.isNotBlank()) {
                    Spacer(Modifier.size(6.dp))
                    Text(
                        auditLine,
                        color = if (state.fontAudit.startsWith("gap:")) {
                            MaterialTheme.colorScheme.error
                        } else {
                            MaterialTheme.colorScheme.onSurfaceVariant
                        },
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Medium,
                    )
                }
                if (!failed) {
                    Spacer(Modifier.size(12.dp))
                    Surface(
                        modifier = Modifier.fillMaxWidth(),
                        shape = LuoShuSmoothShape(18.dp),
                        color = tokens.glassCardColor,
                        border = BorderStroke(1.dp, tokens.glassOutlineBrush),
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
