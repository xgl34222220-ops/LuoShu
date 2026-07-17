#!/system/bin/sh
# 洛书 v10.0 - fonts.xml 生成模板

# 扫描字体文件字重
scan_weights() {
    font_dir="$1"
    font_id="$2"
    
    has_thin="" has_light="" has_regular="" has_medium=""
    has_semibold="" has_bold="" has_black="" has_heavy=""
    thin_file="" light_file="" regular_file="" medium_file=""
    semibold_file="" bold_file="" black_file="" heavy_file=""
    
    for f in "$font_dir"/*.ttf "$font_dir"/*.otf "$font_dir"/*.TTF "$font_dir"/*.OTF; do
        [ -f "$f" ] || continue
        base=$(basename "$f")
        lower=$(echo "$base" | tr '[:upper:]' '[:lower:]')
        
        case "$lower" in
            *thin*)     has_thin="true";     thin_file="$base"     ;;
            *light*)    has_light="true";    light_file="$base"    ;;
            *semibold*|*semi*)  has_semibold="true"; semibold_file="$base" ;;
            *medium*)   has_medium="true";   medium_file="$base"   ;;
            *bold*)     has_bold="true";     bold_file="$base"     ;;
            *black*)    has_black="true";    black_file="$base"    ;;
            *heavy*)    has_heavy="true";    heavy_file="$base"    ;;
            *regular*)  has_regular="true";  regular_file="$base"  ;;
        esac
        
        if [ -z "$has_regular" ]; then
            case "$lower" in
                *thin*|*light*|*semi*|*medium*|*bold*|*black*|*heavy*) ;;
                *) has_regular="true"; regular_file="$base" ;;
            esac
        fi
    done
    
    if [ -z "$has_regular" ]; then
        if [ -n "$bold_file" ]; then regular_file="$bold_file"
        elif [ -n "$medium_file" ]; then regular_file="$medium_file"
        elif [ -n "$light_file" ]; then regular_file="$light_file"
        else
            for f in "$font_dir"/*.ttf "$font_dir"/*.otf; do
                [ -f "$f" ] && { regular_file=$(basename "$f"); break; }
            done
        fi
        has_regular="true"
    fi
    
    # 输出变量
    echo "$has_thin|$thin_file|$has_light|$light_file|$has_regular|$regular_file|$has_medium|$medium_file|$has_semibold|$semibold_file|$has_bold|$bold_file|$has_black|$black_file|$has_heavy|$heavy_file"
}

# 生成字体 XML（用于命令行切换时调用）
generate_font_xml() {
    family_name="$1"
    font_dir="$2"
    output_path="$3"
    
    weights=$(scan_weights "$font_dir" "$family_name")
    
    has_thin=$(echo "$weights" | cut -d'|' -f1)
    thin_file=$(echo "$weights" | cut -d'|' -f2)
    has_light=$(echo "$weights" | cut -d'|' -f3)
    light_file=$(echo "$weights" | cut -d'|' -f4)
    has_regular=$(echo "$weights" | cut -d'|' -f5)
    regular_file=$(echo "$weights" | cut -d'|' -f6)
    has_medium=$(echo "$weights" | cut -d'|' -f7)
    medium_file=$(echo "$weights" | cut -d'|' -f8)
    has_semibold=$(echo "$weights" | cut -d'|' -f9)
    semibold_file=$(echo "$weights" | cut -d'|' -f10)
    has_bold=$(echo "$weights" | cut -d'|' -f11)
    bold_file=$(echo "$weights" | cut -d'|' -f12)
    has_black=$(echo "$weights" | cut -d'|' -f13)
    black_file=$(echo "$weights" | cut -d'|' -f14)
    has_heavy=$(echo "$weights" | cut -d'|' -f15)
    heavy_file=$(echo "$weights" | cut -d'|' -f16)
    
    fb="$regular_file"
    [ -z "$fb" ] && fb="$bold_file"
    
    cat > "$output_path" << XMLEOF
<?xml version="1.0" encoding="utf-8"?>
<!--
    洛书 v10.0 - 字体配置
    字体：$family_name
-->
<familyset version="24">

    <!-- 主字体：无衬线 -->
    <family name="sans-serif">
XMLEOF
    [ -n "$has_thin" ]     && echo "        <font weight=\"100\" style=\"normal\">$thin_file</font>"     >> "$output_path"
    [ -n "$has_light" ]    && echo "        <font weight=\"300\" style=\"normal\">$light_file</font>"    >> "$output_path"
                                echo "        <font weight=\"400\" style=\"normal\">$regular_file</font>" >> "$output_path"
    [ -n "$has_medium" ]   && echo "        <font weight=\"500\" style=\"normal\">$medium_file</font>"   >> "$output_path"
    [ -n "$has_semibold" ] && echo "        <font weight=\"600\" style=\"normal\">$semibold_file</font>" >> "$output_path"
    [ -n "$has_bold" ]     && echo "        <font weight=\"700\" style=\"normal\">$bold_file</font>"     >> "$output_path"
    [ -n "$has_black" ]    && echo "        <font weight=\"900\" style=\"normal\">$black_file</font>"    >> "$output_path"
    [ -n "$has_heavy" ]    && echo "        <font weight=\"900\" style=\"normal\">$heavy_file</font>"    >> "$output_path"
    cat >> "$output_path" << XMLEOF
    </family>

    <!-- 字重变体 -->
XMLEOF
    [ -n "$has_thin" ] && cat >> "$output_path" << XMLEOF
    <family name="sans-serif-thin">
        <font weight="100" style="normal">$thin_file</font>
    </family>
XMLEOF
    [ -n "$has_light" ] && cat >> "$output_path" << XMLEOF
    <family name="sans-serif-light">
        <font weight="300" style="normal">$light_file</font>
    </family>
XMLEOF
    [ -n "$has_medium" ] && cat >> "$output_path" << XMLEOF
    <family name="sans-serif-medium">
        <font weight="500" style="normal">$medium_file</font>
    </family>
XMLEOF
    [ -n "$has_black" ] && cat >> "$output_path" << XMLEOF
    <family name="sans-serif-black">
        <font weight="900" style="normal">$black_file</font>
    </family>
XMLEOF

    cat >> "$output_path" << XMLEOF

    <!-- 压缩体 -->
    <family name="sans-serif-condensed">
        <font weight="400" style="normal">$fb</font>
    </family>
    <family name="sans-serif-condensed-light">
        <font weight="300" style="normal">${light_file:-$fb}</font>
    </family>

    <!-- 衬线体 -->
    <family name="serif">
        <font weight="400" style="normal">$fb</font>
XMLEOF
    [ -n "$has_bold" ] && echo "        <font weight=\"700\" style=\"normal\">$bold_file</font>" >> "$output_path"
    echo '    </family>' >> "$output_path"

    cat >> "$output_path" << XMLEOF

    <!-- 等宽体 -->
    <family name="monospace">
        <font weight="400" style="normal">$fb</font>
XMLEOF
    [ -n "$has_bold" ] && echo "        <font weight=\"700\" style=\"normal\">$bold_file</font>" >> "$output_path"
    echo '    </family>' >> "$output_path"

    cat >> "$output_path" << XMLEOF

    <!-- Google Sans -->
    <family name="google-sans">
        <font weight="400" style="normal">$fb</font>
XMLEOF
    [ -n "$has_medium" ] && echo "        <font weight=\"500\" style=\"normal\">$medium_file</font>" >> "$output_path"
    [ -n "$has_bold" ] && echo "        <font weight=\"700\" style=\"normal\">$bold_file</font>" >> "$output_path"
    echo '    </family>' >> "$output_path"

    cat >> "$output_path" << XMLEOF
    <family name="google-sans-text">
        <font weight="400" style="normal">$fb</font>
XMLEOF
    [ -n "$has_medium" ] && echo "        <font weight=\"500\" style=\"normal\">$medium_file</font>" >> "$output_path"
    echo '    </family>' >> "$output_path"

    # CJK 回退
    for lang in zh-Hans zh-Hant ja ko; do
        echo "    <family lang=\"$lang\">" >> "$output_path"
        echo "        <font weight=\"400\" style=\"normal\">$fb</font>" >> "$output_path"
        [ -n "$has_bold" ] && echo "        <font weight=\"700\" style=\"normal\">$bold_file</font>" >> "$output_path"
        echo "    </family>" >> "$output_path"
    done

    cat >> "$output_path" << XMLEOF

    <!-- Emoji（独立定义，不在 sans-serif 中混合） -->
    <family name="emoji">
        <font weight="400" style="normal">NotoColorEmoji.ttf</font>
    </family>

    <!-- 符号字体（关键：修复 1️⃣2️⃣3️⃣ 等 emoji 数字方块） -->
    <family>
        <font weight="400" style="normal">NotoSansSymbols-Regular.ttf</font>
    </family>
    <family>
        <font weight="400" style="normal">NotoSansSymbols2-Regular.ttf</font>
    </family>

    <!-- 数学符号 -->
    <family>
        <font weight="400" style="normal">NotoSansMath-Regular.ttf</font>
    </family>

    <!-- ColorOS -->
    <family name="oplus-sans">
        <font weight="400" style="normal">$fb</font>
XMLEOF
    [ -n "$has_bold" ] && echo "        <font weight=\"700\" style=\"normal\">$bold_file</font>" >> "$output_path"
    echo '    </family>' >> "$output_path"

    cat >> "$output_path" << XMLEOF
    <family name="oplus-sans-medium">
        <font weight="500" style="normal">${medium_file:-$fb}</font>
    </family>
    <family name="oplus-display">
        <font weight="400" style="normal">$fb</font>
    </family>

    <!-- WebView 回退 -->
    <family name="arial"><font weight="400" style="normal">$fb</font></family>
    <family name="helvetica"><font weight="400" style="normal">$fb</font></family>
    <family name="tahoma"><font weight="400" style="normal">$fb</font></family>
    <family name="verdana"><font weight="400" style="normal">$fb</font></family>
    <family name="times"><font weight="400" style="normal">$fb</font></family>
    <family name="roboto">
        <font weight="400" style="normal">$fb</font>
XMLEOF
    [ -n "$has_medium" ] && echo "        <font weight=\"500\" style=\"normal\">$medium_file</font>" >> "$output_path"
    [ -n "$has_bold" ] && echo "        <font weight=\"700\" style=\"normal\">$bold_file</font>" >> "$output_path"
    echo '    </family>' >> "$output_path"

    cat >> "$output_path" << XMLEOF
    <family name="courier"><font weight="400" style="normal">$fb</font></family>

    <!-- 其他 -->
    <family name="casual"><font weight="400" style="normal">$fb</font></family>
    <family name="cursive"><font weight="400" style="normal">$fb</font></family>
    <family name="sans-serif-smallcaps"><font weight="400" style="normal">$fb</font></family>
    <family name="serif-monospace"><font weight="400" style="normal">$fb</font></family>

</familyset>
XMLEOF
}

# 默认字体（不替换）
generate_default_xml() {
    output_path="$1"
    cat > "$output_path" << 'XMLEOF'
<?xml version="1.0" encoding="utf-8"?>
<familyset version="24">
    <family name="sans-serif">
        <font weight="400" style="normal">Roboto-Regular.ttf</font>
        <font weight="700" style="normal">Roboto-Bold.ttf</font>
    </family>
</familyset>
XMLEOF
}
