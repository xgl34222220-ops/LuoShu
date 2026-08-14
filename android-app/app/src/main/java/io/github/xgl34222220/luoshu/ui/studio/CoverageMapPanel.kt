package io.github.xgl34222220.luoshu.ui.studio

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.CoverageGroupMetrics
import io.github.xgl34222220.luoshu.CoverageProbeState

private data class CoverageLabel(val key: String, val label: String)
private val coverageLabels = listOf(
    CoverageLabel("simplifiedSample", "简体常用"),
    CoverageLabel("traditionalSample", "繁体常用"),
    CoverageLabel("japaneseKana", "日文假名"),
    CoverageLabel("koreanHangul", "韩文"),
    CoverageLabel("latinBasic", "基础拉丁"),
    CoverageLabel("latinExtended", "拉丁扩展"),
    CoverageLabel("digit", "数字"),
    CoverageLabel("punctuation", "标点"),
    CoverageLabel("math", "数学符号"),
    CoverageLabel("pua", "PUA 私用区"),
)

@Composable
internal fun CoverageMapPanel(
    coverage: CoverageProbeState,
    fontId: String,
    fontName: String,
    onInspect: (String) -> Unit,
) {
    val current = coverage.fontId == fontId && fontId.isNotBlank()
    val metrics = coverage.metrics.takeIf { current }
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(22.dp),
        color = MaterialTheme.colorScheme.surfaceContainer,
    ) {
        Column(Modifier.fillMaxWidth().padding(13.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("缺字地图", fontSize = 14.sp, fontWeight = FontWeight.Black)
                    Text(
                        fontName.ifBlank { "先选择一个字体槽位" },
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 9.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                Button(onClick = { onInspect(fontId) }, enabled = fontId.isNotBlank() && !coverage.loading) {
                    if (coverage.loading && current) CircularProgressIndicator(Modifier.size(15.dp), strokeWidth = 2.dp)
                    else Icon(Icons.Rounded.Search, null, Modifier.size(16.dp))
                    Spacer(Modifier.width(5.dp)); Text(if (metrics == null) "检测" else "重测", fontSize = 10.sp)
                }
            }
            when {
                current && coverage.loading -> Text("正在扫描 Unicode 覆盖…", fontSize = 10.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                current && coverage.error.isNotBlank() -> Text(coverage.error, color = MaterialTheme.colorScheme.error, fontSize = 10.sp)
                metrics != null -> {
                    if (metrics.recommendation.isNotBlank()) {
                        Surface(
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(15.dp),
                            color = MaterialTheme.colorScheme.primary.copy(alpha = .08f),
                        ) {
                            Row(Modifier.padding(10.dp), verticalAlignment = Alignment.CenterVertically) {
                                val good = metrics.recommendation.contains("适合全局")
                                Icon(if (good) Icons.Rounded.CheckCircle else Icons.Rounded.Warning, null, Modifier.size(17.dp), tint = if (good) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.tertiary)
                                Spacer(Modifier.width(6.dp))
                                Text(metrics.recommendation, fontWeight = FontWeight.Bold, fontSize = 10.sp)
                            }
                        }
                    }
                    coverageLabels.forEach { item -> metrics.groups[item.key]?.let { CoverageGroupRow(item.label, it) } }
                    val missing = metrics.missingByGroup.filterValues { it.isNotBlank() }
                    if (missing.isNotEmpty()) {
                        Spacer(Modifier.height(2.dp))
                        Text("代表性缺字", fontSize = 11.sp, fontWeight = FontWeight.Black)
                        missing.forEach { (key, value) ->
                            val label = when (key) { "simplified" -> "简体"; "traditional" -> "繁体"; "japanese" -> "日文"; "korean" -> "韩文"; "math" -> "数学"; else -> key }
                            Text("$label：$value", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 9.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
                        }
                    }
                }
                else -> Text("检测后会显示简繁中文、日文、韩文、拉丁扩展、数学符号与 PUA 覆盖率。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 9.sp)
            }
        }
    }
}

@Composable
private fun CoverageGroupRow(label: String, value: CoverageGroupMetrics) {
    val progress = (value.percent / 100f).coerceIn(0f, 1f)
    Column(Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(label, modifier = Modifier.weight(1f), fontSize = 9.sp, fontWeight = FontWeight.Medium)
            Text("${formatPercent(value.percent)}% · ${value.present}/${value.total}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 8.sp)
        }
        Spacer(Modifier.height(3.dp))
        LinearProgressIndicator(progress = { progress }, modifier = Modifier.fillMaxWidth().height(5.dp))
    }
}

private fun formatPercent(value: Float): String = if (value % 1f == 0f) value.toInt().toString() else "%.1f".format(value)
