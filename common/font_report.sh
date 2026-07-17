#!/system/bin/sh
# 洛书 v14.1 测试版 3 - 设备、字体映射与存储诊断报告
set +e
MODDIR="${MODDIR:-/data/adb/modules/LuoShu}"
MODULE_DIR="$MODDIR"
[ -f "$MODDIR/common/font_check.sh" ] && . "$MODDIR/common/font_check.sh"
[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
[ -f "$MODDIR/common/rom_adapters.sh" ] && . "$MODDIR/common/rom_adapters.sh"
type check_coloros >/dev/null 2>&1 && check_coloros
type check_hyperos >/dev/null 2>&1 && check_hyperos
FONT="$1"
OUT="${2:-/sdcard/LuoShu/reports/LuoShu_Font_Report_$(date +%Y%m%d_%H%M%S).txt}"
mkdir -p "${OUT%/*}" 2>/dev/null || true

hash_file(){
    [ -f "$1" ] || { echo missing; return; }
    if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" 2>/dev/null | awk '{print $1}'
    elif command -v toybox >/dev/null 2>&1; then toybox sha256sum "$1" 2>/dev/null | awk '{print $1}'
    else cksum "$1" 2>/dev/null | awk '{print "cksum:"$1":"$2}'
    fi
}
map_line(){
    _label="$1"; _file="$2"; _path="$MODDIR/system/fonts/$_file"
    if [ -f "$_path" ]; then
        _inode=$(ls -i "$_path" 2>/dev/null | awk '{print $1}')
        _bytes=$(wc -c < "$_path" 2>/dev/null | tr -d '[:space:]')
        echo "$_label: $_file | bytes=${_bytes:-0} | inode=${_inode:-?} | sha256=$(hash_file "$_path")"
    else
        echo "$_label: $_file | missing"
    fi
}

ROOT_MANAGER="Root"
if command -v apd >/dev/null 2>&1 || [ -d /data/adb/ap ] || [ -d /data/adb/apatch ]; then ROOT_MANAGER="APatch"
elif command -v ksud >/dev/null 2>&1 || [ -d /data/adb/ksu ]; then
    _ksu_info="$(ksud -V 2>/dev/null || ksud --version 2>/dev/null || true)"
    case "$_ksu_info $(getprop ro.build.version.incremental 2>/dev/null)" in *SukiSU*|*sukisu*|*SUKISU*) ROOT_MANAGER="SukiSU Ultra" ;; *) ROOT_MANAGER="KernelSU" ;; esac
elif command -v magisk >/dev/null 2>&1 || [ -d /data/adb/magisk ]; then ROOT_MANAGER="Magisk"; fi
MOUNT_ENV="native"
if [ -d /data/adb/modules/mountify ] && [ ! -f /data/adb/modules/mountify/disable ] && [ ! -f /data/adb/modules/mountify/remove ]; then MOUNT_ENV="Mountify"
elif [ -d /data/adb/mountify ]; then MOUNT_ENV="Mountify"; fi

{
    echo "LuoShu Font Report v14.1 test3"
    echo "Generated: $(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)"
    echo "Device: $(getprop ro.product.manufacturer 2>/dev/null) $(getprop ro.product.model 2>/dev/null)"
    echo "Android: $(getprop ro.build.version.release 2>/dev/null) (SDK $(getprop ro.build.version.sdk 2>/dev/null))"
    echo "ROM: ColorOS=$(getprop ro.build.version.oplusrom 2>/dev/null) HyperOS=$(getprop ro.mi.os.version.name 2>/dev/null)"
    echo "Root manager: $ROOT_MANAGER"
    echo "Mount environment: $MOUNT_ENV"
    echo "Active font: $(head -n1 "$MODDIR/config/active_font.conf" 2>/dev/null)"
    echo "Font weight desired: $(sed -n 's/^weight=//p' "$MODDIR/config/font_weight.conf" 2>/dev/null | head -n1)"
    echo "Font weight adjustment: $(settings get secure font_weight_adjustment 2>/dev/null)"
    echo "Text reboot pending: $([ -f "$MODDIR/config/text_reboot_required.conf" ] && echo yes || echo no)"
    echo "Public font dir: /sdcard/LuoShu/fonts"
    echo
    echo "Mix source identity:"
    for _slot in cjk latin digit; do
        _id=$(sed -n "s/^${_slot}=//p" "$MODDIR/config/font_mix.conf" 2>/dev/null | head -n1)
        _path=$(sed -n "s/^${_slot}_path=//p" "$MODDIR/config/font_mix.conf" 2>/dev/null | head -n1)
        _saved=$(sed -n "s/^${_slot}_sha256=//p" "$MODDIR/config/font_mix.conf" 2>/dev/null | head -n1)
        echo "$_slot: id=$_id | path=$_path | saved=$_saved | current=$(hash_file "$_path")"
    done
    echo
    echo "Actual role mapping:"
    if [ "${IS_COLOROS:-false}" = true ]; then
        map_line CJK SysFont-Hans-Regular.ttf
        map_line LATIN SysSans-En-Regular.ttf
        map_line DIGIT DINPro-Regular.ttf
    elif [ "${IS_HYPEROS:-false}" = true ]; then
        map_line CJK MiSansVF.ttf
        map_line LATIN MiSansLatinVF.ttf
        map_line DIGIT 400.ttf
    else
        map_line CJK NotoSansCJK-Regular.ttc
        map_line LATIN Roboto-Regular.ttf
    fi
    echo
    echo "Storage detail:"
    [ -f "$MODDIR/common/preview_cache.sh" ] && MODDIR="$MODDIR" sh "$MODDIR/common/preview_cache.sh" storage 2>/dev/null || true
    echo
    echo "Storage (/data):"; df -h /data 2>/dev/null || true
    echo "Inodes (/data):"; df -i /data 2>/dev/null || true
    echo
    echo "LuoShu mounts:"
    grep -i 'LuoShu\|/system/fonts\|/data/fonts' /proc/mounts 2>/dev/null | tail -n 80 || true
    echo
    echo "Selected file: $FONT"
    if [ -f "$FONT" ]; then
        if type font_validate >/dev/null 2>&1 && font_validate "$FONT" text; then
            echo "Validation: PASS"; echo "Real format: $FONT_CHECK_FORMAT"; echo "Bytes: $FONT_CHECK_SIZE"; echo "Variable: $FONT_CHECK_VARIABLE"; [ -n "$FONT_CHECK_WARNING" ] && echo "Warning: $FONT_CHECK_WARNING"
        else echo "Validation: FAIL"; echo "Reason: ${FONT_CHECK_ERROR:-checker unavailable}"; fi
    else echo "Validation: MISSING"; fi
    echo
    echo "Recent log:"; tail -n 120 "$MODDIR/logs/fontswitch.log" 2>/dev/null
} > "$OUT"
chmod 0644 "$OUT" 2>/dev/null || true
echo "$OUT"
