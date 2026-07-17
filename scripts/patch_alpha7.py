from pathlib import Path
import re

root = Path('.')

(root / 'module.prop').write_text('''id=LuoShu
name=洛书
version=v14.1 Test4 Alpha7 Full Composite
versionCode=14107
author=惜故里丶
description=Android 全局字体管理；Alpha7 使用完整复合字体避免中英数字体抢占与直接加载缺字
updateJson=
webroot=webroot
''', encoding='utf-8')

service = (root / 'service.sh').read_text(encoding='utf-8')
service = re.sub(r'''\n    if command -v cmd >/dev/null 2>&1; then\n.*?\n    if \[ -f "\$MODDIR/common/wechat_xweb_bridge" \]; then\n.*?\n    fi\n''', '''\n    # Alpha7 不在开机完成后刷新字体服务或重复桥接。\n    # 新复合字体只在 WebUI 主动生成，完整重启后由系统自然加载。\n''', service, flags=re.S)
service = service.replace('find "$MODDIR/common" -maxdepth 1 -type f -exec chmod 0755 {} \\; 2>/dev/null || true', 'find "$MODDIR/common" -maxdepth 1 -type f -exec chmod 0755 {} \\; 2>/dev/null || true\n    chmod 0755 "$MODDIR/common/python/bin/luoshu-python" 2>/dev/null || true')
service = service.replace('服务脚本开始执行 (v14)', '服务脚本开始执行 (Alpha7)')
(root / 'service.sh').write_text(service, encoding='utf-8')

customize = (root / 'customize.sh').read_text(encoding='utf-8')
customize = customize.replace('LuoShu v14 - 安装脚本', 'LuoShu v14.1 Alpha7 - 安装脚本')
customize = customize.replace('║       洛 书  v14       ║', '║  洛书 v14.1 Alpha7 Full Composite  ║')
customize = customize.replace('[ -n "$FONT_COUNT" ] || FONT_COUNT=0\ncase "$FONT_COUNT" in \'\'|*[!0-9]*) FONT_COUNT=0 ;; esac', '[ -n "$FONT_COUNT" ] || FONT_COUNT=0\ncase "$FONT_COUNT" in \'\'|*[!0-9]*) FONT_COUNT=0 ;; esac\n# Alpha7 刷写阶段永远不处理字体，首次启动保持系统默认。\nFONT_COUNT=0')
customize = customize.replace('chmod 755 "$MODPATH/common/module_status.sh" "$MODPATH/common/v14_switch.sh" "$MODPATH/common/font_mix.sh" "$MODPATH/common/v14_mix.sh" 2>/dev/null || true', 'chmod 755 "$MODPATH/common/module_status.sh" "$MODPATH/common/v14_switch.sh" "$MODPATH/common/font_mix.sh" "$MODPATH/common/v14_mix.sh" "$MODPATH/common/luoshu_composite.sh" 2>/dev/null || true\nchmod 755 "$MODPATH/common/python/bin/luoshu-python" 2>/dev/null || true')
(root / 'customize.sh').write_text(customize, encoding='utf-8')

override = r'''
composite_hash_file() {
    _hf="$1"
    if command -v sha256sum >/dev/null 2>&1; then sha256sum "$_hf" | awk '{print $1}'
    elif command -v toybox >/dev/null 2>&1; then toybox sha256sum "$_hf" | awk '{print $1}'
    else cksum "$_hf" | awk '{print $1 "-" $2}'
    fi
}

build_composite_anchor() {
    _cjk_src="$1"; _latin_src="$2"; _digit_src="$3"
    _runner="$MODDIR/common/luoshu_composite.sh"
    [ -f "$MODDIR/common/composite_font.py" ] && [ -f "$_runner" ] || { echo '错误：完整复合字体引擎缺失' >&2; return 1; }
    [ -x "$MODDIR/common/python/bin/luoshu-python" ] || chmod 0755 "$MODDIR/common/python/bin/luoshu-python" 2>/dev/null || true
    _cache="$MODDIR/cache/full-composite-v1"
    mkdir -p "$_cache" "$MODDIR/cache/tmp" 2>/dev/null || return 1
    _key_src="$(composite_hash_file "$_cjk_src")-$(composite_hash_file "$_latin_src")-$(composite_hash_file "$_digit_src")-full-composite-v1"
    _key=$(printf '%s' "$_key_src" | { if command -v sha256sum >/dev/null 2>&1; then sha256sum; elif command -v toybox >/dev/null 2>&1; then toybox sha256sum; else cksum; fi; } | awk '{print $1}')
    _cached="$_cache/${_key}.otf"
    _report="$_cache/${_key}.json"
    if [ ! -s "$_cached" ]; then
        _tmp="$_cache/.${_key}.$$.tmp.otf"
        _tmp_report="$_cache/.${_key}.$$.tmp.json"
        rm -f "$_tmp" "$_tmp_report" 2>/dev/null || true
        if ! MODDIR="$MODDIR" sh "$_runner" --cjk "$_cjk_src" --latin "$_latin_src" --digit "$_digit_src" --output "$_tmp" > "$_tmp_report" 2>> "$LOG_FILE"; then
            rm -f "$_tmp" "$_tmp_report" 2>/dev/null || true
            echo '错误：完整复合字体生成失败，请查看诊断日志' >&2
            return 1
        fi
        [ -s "$_tmp" ] || { rm -f "$_tmp" "$_tmp_report"; echo '错误：复合字体输出为空' >&2; return 1; }
        if type font_validate >/dev/null 2>&1 && ! font_validate "$_tmp" text; then
            rm -f "$_tmp" "$_tmp_report" 2>/dev/null || true
            echo "错误：复合字体验证失败：$FONT_CHECK_ERROR" >&2
            return 1
        fi
        chmod 0644 "$_tmp" "$_tmp_report" 2>/dev/null || true
        mv -f "$_tmp" "$_cached" || return 1
        mv -f "$_tmp_report" "$_report" 2>/dev/null || true
    fi
    _font_anchor "$_cached" "$SYSTEM_FONTS_DIR" mix-composite
}

apply_coloros_mix() {
    _cjk_src="$1"; _latin_src="$2"; _digit_src="$3"
    _font_store_reset "$SYSTEM_FONTS_DIR"
    _ma=$(build_composite_anchor "$_cjk_src" "$_latin_src" "$_digit_src") || return 1
    alias_core "$_ma" SysSans-Hans-Regular.ttf SysSans-Hant-Regular.ttf SysFont-Hans-Regular.ttf SysFont-Hant-Regular.ttf SysFont-Static-Regular.ttf SysFont-Regular.ttf SysSans-En-Regular.ttf Roboto-Regular.ttf GoogleSans-Regular.ttf GoogleSansText-Regular.ttf
    alias_existing_list "$_ma" Opposans-Hans-Regular.ttf Opposans-Hans-Bold.ttf Opposans-Hans-Medium.ttf Opposans-Hans-Light.ttf SysSans-Hans-Bold.ttf SysSans-Hans-Medium.ttf SysSans-Hans-Light.ttf SysSans-Hant-Bold.ttf SysSans-Hant-Medium.ttf SysSans-Hant-Light.ttf SysFont-Hans-Bold.ttf SysFont-Hans-Medium.ttf SysFont-Hans-Light.ttf SysFont-Hant-Bold.ttf SysFont-Hant-Medium.ttf SysFont-Hant-Light.ttf SysFont-Static-Bold.ttf SysFont-Static-Medium.ttf SysFont-Static-Light.ttf SysFont-Bold.ttf SysFont-Medium.ttf SysFont-Light.ttf SysFont-Thin.ttf SysFont-Black.ttf SysSans-En-Bold.ttf SysSans-En-Medium.ttf SysSans-En-Light.ttf SysSans-En-Thin.ttf SysSans-En-Black.ttf Opposans-En-Regular.ttf Opposans-En-Bold.ttf Opposans-En-Medium.ttf Opposans-En-Light.ttf OPSans-En-Regular.ttf Roboto-Medium.ttf Roboto-Bold.ttf Roboto-Light.ttf Roboto-Thin.ttf RobotoFlex-Regular.ttf RobotoStatic-Regular.ttf GoogleSans-Medium.ttf GoogleSans-Bold.ttf GoogleSansText-Medium.ttf GoogleSansText-Bold.ttf GoogleSansFlex-Regular.ttf SourceSansPro-Regular.ttf SourceSansPro-SemiBold.ttf SourceSansPro-Bold.ttf DINCondensedBold.ttf DINPro-Regular.ttf DINPro-Medium.ttf DINPro-Bold.ttf OPPODIN-Regular.ttf OPPODIN-Medium.ttf OPPODIN-Bold.ttf OPPODINCondensed-Regular.ttf OPPODINCondensed-Medium.ttf OPPODINCondensed-Bold.ttf
    return 0
}

apply_hyperos_mix() {
    _cjk_src="$1"; _latin_src="$2"; _digit_src="$3"
    _font_store_reset "$SYSTEM_FONTS_DIR"
    _ma=$(build_composite_anchor "$_cjk_src" "$_latin_src" "$_digit_src") || return 1
    alias_core "$_ma" MiSansVF.ttf MiSansVF_Overlay.ttf MiSansTCVF.ttf MiSansL3.otf MiSansLatinVF.ttf Roboto-Regular.ttf GoogleSans-Regular.ttf GoogleSansText-Regular.ttf 100.ttf 200.ttf 300.ttf 350.ttf 400.ttf 500.ttf 600.ttf 700.ttf 800.ttf 900.ttf
    alias_existing_list "$_ma" Roboto-Medium.ttf Roboto-Bold.ttf Roboto-Light.ttf Roboto-Thin.ttf RobotoFlex-Regular.ttf RobotoStatic-Regular.ttf GoogleSans-Medium.ttf GoogleSans-Bold.ttf GoogleSansText-Medium.ttf GoogleSansText-Bold.ttf GoogleSansFlex-Regular.ttf
    return 0
}

apply_generic_mix() {
    _cjk_src="$1"; _latin_src="$2"; _digit_src="$3"
    _font_store_reset "$SYSTEM_FONTS_DIR"
    _ma=$(build_composite_anchor "$_cjk_src" "$_latin_src" "$_digit_src") || return 1
    alias_core "$_ma" NotoSansCJK-Regular.ttc NotoSansSC-Regular.otf NotoSansTC-Regular.otf NotoSans-Regular.ttf Roboto-Regular.ttf Roboto-Medium.ttf Roboto-Bold.ttf Roboto-Light.ttf GoogleSans-Regular.ttf GoogleSansText-Regular.ttf DroidSans.ttf
    return 0
}
'''
mix = (root / 'common/font_mix.sh').read_text(encoding='utf-8')
if 'build_composite_anchor()' not in mix:
    mix = mix.replace('\napply_mix() {', '\n' + override + '\napply_mix() {', 1)
mix = mix.replace("printf 'time=%s\\n' \"$(date +%s)\"", "printf 'isolation=full-composite-v1\\n'\n        printf 'characterIsolation=true\\n'\n        printf 'composite=true\\n'\n        printf 'xmlOverlay=false\\n'\n        printf 'time=%s\\n' \"$(date +%s)\"")
mix = mix.replace("'正在生成字体组合'", "'正在生成完整复合字体'")
mix = mix.replace("'字体组合已准备，完整重启后生效'", "'完整复合字体已准备，完整重启后生效'")
mix = mix.replace('字体组合已准备，请完整重启手机。', '完整复合字体已准备，请完整重启手机。')
(root / 'common/font_mix.sh').write_text(mix, encoding='utf-8')

js = (root / 'webroot/v14.js').read_text(encoding='utf-8')
js = js.replace('组合字体', '完整复合字体')
js = js.replace('中文、英文、数字分别选择', '中文为完整基底，英文与数字替换字形')
js = js.replace('不再单独管理 Emoji。选择三款字体后，一次生成完整组合。', '三款字体合成为同一份完整字体；所有系统槽使用相同文件，不依赖缺字回退。')
js = js.replace('数字槽优先映射系统专用数字文件；普通应用没有独立数字入口时会跟随英文字体。', '中文覆盖始终来自中文基底；英文与数字只导入对应字形，不会携带源字体中的中文字形。')
js = js.replace('中文、English 与 123 分别映射', '中文、English 与 123 来自同一份完整复合字体')
js = js.replace("formatEl.textContent = 'MIX'", "formatEl.textContent = 'COMPOSITE'")
js = js.replace("sizeEl.textContent = '3 槽'", "sizeEl.textContent = '完整字体'")
js = js.replace('timeoutMs = 70000', 'timeoutMs = 360000')
js = js.replace('> 180000', '> 900000')
js = js.replace('pending.task, 45000', 'pending.task, 240000')
js = js.replace('正在分别映射中文、英文和数字入口', '正在合并完整中文基底并替换英文、数字字形')
(root / 'webroot/v14.js').write_text(js, encoding='utf-8')

index = (root / 'webroot/index.html').read_text(encoding='utf-8')
index = index.replace('?v=14000', '?v=14107')
(root / 'webroot/index.html').write_text(index, encoding='utf-8')

(root / 'config/version_notes.conf').write_text('version=v14.1 Test4 Alpha7 Full Composite\nsummary=完整中文基底内替换英文与数字字形；所有 ROM 字体槽使用同一份完整复合字体\nsafety=不修改 fonts.xml，不在刷写或开机阶段处理字体，失败时不替换当前字体\n', encoding='utf-8')
(root / '兼容与目录说明.txt').write_text('洛书 v14.1 Test4 Alpha7 Full Composite\n\n字体目录：/sdcard/LuoShu/fonts/\nEmoji 目录：/sdcard/LuoShu/emoji/\n\n完整复合字体以中文字体作为完整基底，只替换拉丁字母和数字字形。\n所有 ROM 物理字体槽共同使用同一份完整字体，因此直接加载物理字体的应用也不会因缺少中文而空白。\n本版本不覆盖 /system/etc/fonts.xml 或 font_fallback.xml；刷写和开机阶段不生成字体。\n应用内置字体、游戏字体和网页下载字体不受系统字体模块控制。\n', encoding='utf-8')
licenses = root / 'licenses'; licenses.mkdir(exist_ok=True)
(licenses / 'THIRD_PARTY.txt').write_text('Alpha7 bundles the official CPython Android runtime and FontTools. Their complete licenses are included beside this file.\n', encoding='utf-8')
