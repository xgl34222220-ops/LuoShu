#!/system/bin/sh
# ============================================================
# 洛书 v10.0 - 音量键选择器
# 基于 Volume-Key-Selector by Zackptg5 @ GitHub
# 适配 Magisk / KernelSU / SukiSU
# ============================================================

# ---------- 检测单个音量键按下 ----------
# 返回: 0=上键(VOLUMEUP), 1=下键(VOLUMEDOWN), 2=超时/不支持
chooseport() {
    delay="${1:-3}"
    events_file="${TMPDIR:-/tmp}/luoshu_events_$$"
    count=0
    max_retry=6

    rm -f "$events_file" 2>/dev/null

    while [ "$count" -lt "$max_retry" ]; do
        count=$((count + 1))

        # 使用 getevent 捕获一个输入事件（带超时）
        # -l = 长格式输出, -q = 安静模式, -c 1 = 只捕获1个事件
        (timeout "$delay" /system/bin/getevent -lqc 1 2>&1 > "$events_file") &
        pid=$!
        wait "$pid" 2>/dev/null

        if [ -f "$events_file" ] && [ -s "$events_file" ]; then
            if grep -q 'KEY_VOLUMEUP *DOWN' "$events_file" 2>/dev/null; then
                rm -f "$events_file" 2>/dev/null
                return 0
            elif grep -q 'KEY_VOLUMEDOWN *DOWN' "$events_file" 2>/dev/null; then
                rm -f "$events_file" 2>/dev/null
                return 1
            fi
        fi
    done

    rm -f "$events_file" 2>/dev/null
    return 2
}

# ---------- 音量键菜单选择 ----------
# 参数: $1=选项列表(用|分隔), $2=超时秒数(默认3)
# 输出: 返回选择的索引(0-based), 存储在 VK_SELECTED 变量
# 交互: 音量上=下一个, 音量下=确认选择, 超时=自动确认
volume_key_menu() {
    options_str="$1"
    timeout_sec="${2:-5}"
    sel=0
    total=0
    # 计算选项数量
    total=$(echo "$options_str" | tr '|' '\n' | grep -c '^')
    [ "$total" -eq 0 ] && total=1

    # 只有一个选项，直接选
    if [ "$total" -le 1 ]; then
        VK_SELECTED=0
        return 0
    fi

    # 显示菜单并等待选择
    while true; do
        # 清屏（用空行分隔）
        ui_print ""
        ui_print "  ╔══════════════════════════════════╗"
        ui_print "  ║      请用音量键选择字体        ║"
        ui_print "  ╚══════════════════════════════════╝"
        ui_print ""

        # 显示所有选项，高亮当前选中
        i=0
        while IFS= read -r opt; do
            [ -z "$opt" ] && continue
            if [ "$i" -eq "$sel" ]; then
                ui_print "  ▶ $(printf '%2d' $((i + 1))). $opt  ←"
            else
                ui_print "    $(printf '%2d' $((i + 1))). $opt"
            fi
            i=$((i + 1))
        done <<EOF
$(echo "$options_str" | tr '|' '\n')
EOF

        ui_print ""
        ui_print "  [音量+] ▲ 下一个    [音量-] ▼ 确认"
        ui_print "  ${timeout_sec}秒无操作自动确认当前选择"
        ui_print ""

        # 等待按键
        chooseport "$timeout_sec"
        key_result=$?

        case "$key_result" in
            0) # 上键(+) = 下一个
                sel=$(( (sel + 1) % total ))
                ;;
            1) # 下键(-) = 确认
                VK_SELECTED="$sel"
                # 获取选中的名称
                selected_name=$(echo "$options_str" | tr '|' '\n' | sed -n "$((sel + 1))p")
                ui_print "  ✓ 已选择: $selected_name"
                ui_print ""
                return 0
                ;;
            2) # 超时 = 自动确认
                VK_SELECTED="$sel"
                selected_name=$(echo "$options_str" | tr '|' '\n' | sed -n "$((sel + 1))p")
                ui_print "  ✓ 自动选择: $selected_name"
                ui_print ""
                return 0
                ;;
        esac
    done
}
