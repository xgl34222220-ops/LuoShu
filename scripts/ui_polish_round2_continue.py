#!/usr/bin/env python3
from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    actual = text.count(old)
    if actual != count:
        raise SystemExit(f"{path}: expected {count}, found {actual}: {old[:120]!r}")
    p.write_text(text.replace(old, new, count), encoding="utf-8")


# The first helper intentionally reaches the Settings replacement only after all
# task-center changes have been applied. Refuse to continue if those edits are absent.
logs = Path("android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/logs/LogsScreenCompact.kt")
logs_text = logs.read_text(encoding="utf-8")
for required in (
    "itemsIndexed(state.tasks",
    "Box(Modifier.size(10.dp).background(color, CircleShape))",
    "isLast: Boolean",
):
    if required not in logs_text:
        raise SystemExit(f"task-center patch incomplete: {required}")

settings = "android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/settings/SettingsHubScreen.kt"
replace(
    settings,
    '''        Row(
            Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 6.dp),
            horizontalArrangement = Arrangement.spacedBy(7.dp),
        ) {
            SettingsSection.entries.forEach { item ->
                val active = item == section
                Surface(
                    onClick = {
                        sectionName = item.name
                        if (item == SettingsSection.SAFETY) model.refreshHealth()
                        if (item == SettingsSection.UPDATE) model.checkUpdate()
                    },
                    shape = RoundedCornerShape(17.dp),
                    color = if (active) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceContainer,
                    contentColor = if (active) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onSurfaceVariant,
                ) {
                    Row(Modifier.padding(horizontal = 13.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                        LuoShuGlyph(
                            imageVector = item.icon,
                            contentDescription = null,
                            size = LuoShuIconTokens.SectionGlyph,
                            opticalScale = item.opticalScale,
                        )
                        Spacer(Modifier.width(6.dp))
                        Text(item.label, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                    }
                }
            }
        }
''',
    '''        Surface(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 5.dp),
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
                        color = if (active) MaterialTheme.colorScheme.primaryContainer else androidx.compose.ui.graphics.Color.Transparent,
                        contentColor = if (active) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onSurfaceVariant,
                        shadowElevation = if (active && settings.uiStyle == UiStyle.MIUIX) 2.dp else 0.dp,
                    ) {
                        Row(
                            Modifier.padding(horizontal = 9.dp, vertical = 8.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.Center,
                        ) {
                            LuoShuGlyph(
                                imageVector = item.icon,
                                contentDescription = null,
                                size = LuoShuIconTokens.SectionGlyph,
                                opticalScale = item.opticalScale,
                            )
                            Spacer(Modifier.width(5.dp))
                            Text(item.label, fontSize = 10.sp, fontWeight = if (active) FontWeight.Black else FontWeight.SemiBold)
                        }
                    }
                }
            }
        }
''',
)

# The first helper exits before updating the regression script, so do that here.
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
    + '''grep -q 'isLast: Boolean' "$LOGS_COMPACT"
''',
    1,
)
p.write_text(text, encoding="utf-8")
print("second UI polish continuation applied")
