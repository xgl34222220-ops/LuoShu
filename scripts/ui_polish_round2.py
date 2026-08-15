#!/usr/bin/env python3
from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    actual = text.count(old)
    if actual != count:
        raise SystemExit(f"{path}: expected {count}, found {actual}: {old[:120]!r}")
    p.write_text(text.replace(old, new, count), encoding="utf-8")


logs = "android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/logs/LogsScreenCompact.kt"
replace(logs, "import androidx.compose.foundation.lazy.items\n", "import androidx.compose.foundation.lazy.items\nimport androidx.compose.foundation.lazy.itemsIndexed\n")
replace(logs, "import androidx.compose.foundation.shape.RoundedCornerShape\n", "import androidx.compose.foundation.shape.CircleShape\nimport androidx.compose.foundation.shape.RoundedCornerShape\n")
replace(
    logs,
    '''        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                LogsTab.entries.forEach { option ->
                    Surface(
                        modifier = Modifier
                            .weight(1f)
                            .clickable { tab = option },
                        shape = RoundedCornerShape(16.dp),
                        color = if (tab == option) {
                            MaterialTheme.colorScheme.primary
                        } else {
                            MaterialTheme.colorScheme.surfaceContainerHigh
                        },
                    ) {
                        Text(
                            option.label,
                            modifier = Modifier.padding(vertical = 11.dp),
                            color = if (tab == option) {
                                MaterialTheme.colorScheme.onPrimary
                            } else {
                                MaterialTheme.colorScheme.onSurface
                            },
                            textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Black,
                        )
                    }
                }
            }
        }
''',
    '''        item {
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(22.dp),
                color = MaterialTheme.colorScheme.surfaceContainerHigh.copy(alpha = if (miuix) .62f else .90f),
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(4.dp),
                    horizontalArrangement = Arrangement.spacedBy(3.dp),
                ) {
                    LogsTab.entries.forEach { option ->
                        val active = tab == option
                        Surface(
                            modifier = Modifier.weight(1f),
                            onClick = { tab = option },
                            shape = RoundedCornerShape(18.dp),
                            color = if (active) MaterialTheme.colorScheme.primary else Color.Transparent,
                            contentColor = if (active) MaterialTheme.colorScheme.onPrimary else textSecondary,
                            shadowElevation = if (active && miuix) 2.dp else 0.dp,
                        ) {
                            Text(
                                option.label,
                                modifier = Modifier.padding(vertical = 10.dp),
                                textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                                fontSize = 12.sp,
                                fontWeight = if (active) FontWeight.Black else FontWeight.Bold,
                            )
                        }
                    }
                }
            }
        }
''',
)
replace(
    logs,
    '''                    items(state.tasks, key = { it.id }) { task ->
                        TaskCard(
                            task = task,
                            cardColor = cardColor,
                            textPrimary = textPrimary,
                            textSecondary = textSecondary,
                        )
                    }
''',
    '''                    itemsIndexed(state.tasks, key = { _, item -> item.id }) { index, task ->
                        TaskCard(
                            task = task,
                            isLast = index == state.tasks.lastIndex,
                            cardColor = cardColor,
                            textPrimary = textPrimary,
                            textSecondary = textSecondary,
                        )
                    }
''',
)
replace(
    logs,
    '''                    items(failed, key = { "issue-${it.id}" }) { task ->
                        TaskCard(
                            task = task,
                            cardColor = cardColor,
                            textPrimary = textPrimary,
                            textSecondary = textSecondary,
                        )
                    }
''',
    '''                    itemsIndexed(failed, key = { _, item -> "issue-${item.id}" }) { index, task ->
                        TaskCard(
                            task = task,
                            isLast = index == failed.lastIndex,
                            cardColor = cardColor,
                            textPrimary = textPrimary,
                            textSecondary = textSecondary,
                        )
                    }
''',
)
replace(
    logs,
    '''private fun TaskCard(
    task: TaskCenterItem,
    cardColor: Color,
    textPrimary: Color,
    textSecondary: Color,
) {
''',
    '''private fun TaskCard(
    task: TaskCenterItem,
    isLast: Boolean,
    cardColor: Color,
    textPrimary: Color,
    textSecondary: Color,
) {
''',
)
replace(
    logs,
    '''    Card(
        shape = RoundedCornerShape(22.dp),
        colors = CardDefaults.cardColors(containerColor = cardColor),
    ) {
        Column(Modifier.padding(15.dp)) {
''',
    '''    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
        Column(
            modifier = Modifier.width(22.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Spacer(Modifier.height(17.dp))
            Box(Modifier.size(10.dp).background(color, CircleShape))
            if (!isLast) {
                Spacer(Modifier.height(4.dp))
                Box(Modifier.width(2.dp).height(88.dp).background(color.copy(alpha = .18f), RoundedCornerShape(999.dp)))
            }
        }
        Spacer(Modifier.width(5.dp))
        Card(
            modifier = Modifier.weight(1f),
            shape = RoundedCornerShape(22.dp),
            colors = CardDefaults.cardColors(containerColor = cardColor),
        ) {
            Column(Modifier.padding(15.dp)) {
''',
    1,
)
# Close the additional Row/Card nesting at the end of TaskCard only.
p = Path(logs)
text = p.read_text(encoding="utf-8")
anchor = '''            if (task.timeLabel.isNotBlank()) {
                Spacer(Modifier.height(6.dp))
                Text(task.timeLabel, color = textSecondary, fontSize = 10.sp)
            }
        }
    }
}

@Composable
private fun LogSummary'''
replacement = '''            if (task.timeLabel.isNotBlank()) {
                Spacer(Modifier.height(6.dp))
                Text(task.timeLabel, color = textSecondary, fontSize = 10.sp)
            }
            }
        }
    }
}

@Composable
private fun LogSummary'''
if text.count(anchor) != 1:
    raise SystemExit("TaskCard closing anchor mismatch")
p.write_text(text.replace(anchor, replacement, 1), encoding="utf-8")

settings = "android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/settings/SettingsHubScreen.kt"
replace(
    settings,
    '''        Row(
            Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 4.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            SettingsSection.entries.forEach { item ->
                val active = item == section
                Surface(
                    onClick = {
                        sectionName = item.name
                        if (item == SettingsSection.SAFETY) model.refreshHealth()
                        if (item == SettingsSection.UPDATE) model.checkUpdate()
                    },
                    shape = RoundedCornerShape(999.dp),
                    color = if (active) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceContainerHigh,
                    contentColor = if (active) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface,
                ) {
                    Row(Modifier.padding(horizontal = 14.dp, vertical = 9.dp), verticalAlignment = Alignment.CenterVertically) {
                        Icon(item.icon, null, Modifier.size(16.dp))
                        Spacer(Modifier.width(6.dp))
                        Text(item.label, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                    }
                }
            }
        }
''',
    '''        Surface(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp),
            shape = RoundedCornerShape(23.dp),
            color = MaterialTheme.colorScheme.surfaceContainerHigh.copy(alpha = if (settings.uiStyle == UiStyle.MIUIX) .62f else .90f),
        ) {
            Row(
                Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(4.dp),
                horizontalArrangement = Arrangement.spacedBy(2.dp),
            ) {
                SettingsSection.entries.forEach { item ->
                    val active = item == section
                    Surface(
                        onClick = {
                            sectionName = item.name
                            if (item == SettingsSection.SAFETY) model.refreshHealth()
                            if (item == SettingsSection.UPDATE) model.checkUpdate()
                        },
                        modifier = Modifier.width(78.dp),
                        shape = RoundedCornerShape(19.dp),
                        color = if (active) MaterialTheme.colorScheme.primary else androidx.compose.ui.graphics.Color.Transparent,
                        contentColor = if (active) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurfaceVariant,
                        shadowElevation = if (active && settings.uiStyle == UiStyle.MIUIX) 2.dp else 0.dp,
                    ) {
                        Row(
                            Modifier.padding(horizontal = 10.dp, vertical = 9.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.Center,
                        ) {
                            Icon(item.icon, null, Modifier.size(15.dp))
                            Spacer(Modifier.width(5.dp))
                            Text(item.label, fontSize = 10.sp, fontWeight = if (active) FontWeight.Black else FontWeight.Bold)
                        }
                    }
                }
            }
        }
''',
)

# Lock the new segmented controls/timeline into the UI regression script.
test = "scripts/font_library_ui_layout_test.sh"
p = Path(test)
text = p.read_text(encoding="utf-8")
needle = '''grep -q 'selfMountSummary(h)' "$SETTINGS"
'''
if text.count(needle) != 1:
    raise SystemExit("UI regression insertion anchor missing")
text = text.replace(
    needle,
    needle
    + '''grep -q 'RoundedCornerShape(23.dp)' "$SETTINGS"
'''
    + '''grep -q 'Modifier.width(78.dp)' "$SETTINGS"
'''
    + '''grep -q 'itemsIndexed(state.tasks' "$LOGS_COMPACT"
'''
    + '''grep -q 'Box(Modifier.size(10.dp).background(color, CircleShape))' "$LOGS_COMPACT"
'''
    + '''grep -q 'RoundedCornerShape(22.dp)' "$LOGS_COMPACT"
''',
    1,
)
p.write_text(text, encoding="utf-8")

print("round 2 UI polish applied")
