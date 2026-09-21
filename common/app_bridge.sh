#!/system/bin/sh
# 洛书 v2.0.0 原生 App 核心桥：状态、字体库、导入、预览、切换与复合任务接口。
set +e

MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then
        MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"
    else
        MODDIR="/data/adb/modules/LuoShu"
    fi
fi
FONT_MANAGER="$MODDIR/common/font_manager.sh"
FONT_SWITCH_TASK="$MODDIR/common/font_switch_task.sh"
SAFE_SWITCH="$MODDIR/common/legacy_v14_4/font_switch_safe.sh"
MIX_ENGINE="$MODDIR/common/font_mix_controller.sh"
NATIVE_IMPORT="$MODDIR/common/native_import.sh"
AXIS_INFO="$MODDIR/common/font_axis_info.py"
SLOT_TRACE="$MODDIR/common/device_font_slot_trace.py"
DEVICE_FONT_CACHE="$MODDIR/common/device_font_cache.sh"
LOAD_VERIFY="$MODDIR/common/device_font_load_verify.sh"
PYROOT="$MODDIR/common/python"
PYBIN="$PYROOT/bin/luoshu-python"
USER_FONTS_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}/fonts"
AXES_TASK_FILE="$MODDIR/config/axes_task.conf"
SWITCH_TASK_FILE="$MODDIR/config/switch_task.conf"
TEXT_REBOOT_REQUIRED="$MODDIR/config/text_reboot_required.conf"
[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
[ -f "$MODDIR/common/mount_compat.sh" ] && . "$MODDIR/common/mount_compat.sh"
[ -f "$MODDIR/common/font_boot_state.sh" ] && . "$MODDIR/common/font_boot_state.sh"

json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '
}

read_prop() {
    sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'
}

root_manager() {
    if command -v apd >/dev/null 2>&1 || [ -d /data/adb/ap ] || [ -d /data/adb/apatch ]; then
        printf 'APatch'
    elif command -v ksud >/dev/null 2>&1 || [ -d /data/adb/ksu ]; then
        # A display label must not wait on a root-manager daemon invocation.
        case "${KSU_VER:-} $(getprop ro.build.version.incremental 2>/dev/null)" in
            *SukiSU*|*sukisu*|*SUKISU*) printf 'SukiSU Ultra' ;;
            *) printf 'KernelSU' ;;
        esac
    elif command -v magisk >/dev/null 2>&1 || [ -d /data/adb/magisk ]; then
        printf 'Magisk'
    else
        printf 'Root'
    fi
}

mount_engine() {
    if type luoshu_detect_mount_engine >/dev/null 2>&1; then
        case "$(luoshu_detect_mount_engine)" in
            self-mount) printf '洛书自挂载' ;;
            magic-mount|magic-mount-rs) printf 'Magic Mount' ;;
            mountify) printf 'Mountify' ;;
            meta-overlayfs|dual-dir-metamodule) printf 'Meta OverlayFS' ;;
            hybrid-mount) printf 'Hybrid Mount' ;;
            native-module-mount) printf 'Root 原生挂载' ;;
            *) printf '洛书自挂载' ;;
        esac
        return
    fi
    printf '洛书自挂载'
}

select_task_file() {
    # queued/running is only trustworthy while its matching worker still exists.
    # Reconcile both controllers before selecting the one visible to the App.
    [ -f "$MIX_ENGINE" ] && MODDIR="$MODDIR" sh "$MIX_ENGINE" reconcile >/dev/null 2>&1 || true
    [ -f "$FONT_SWITCH_TASK" ] && MODDIR="$MODDIR" sh "$FONT_SWITCH_TASK" reconcile >/dev/null 2>&1 || true
    _axes_state="$(read_prop "$AXES_TASK_FILE" state)"
    _switch_state="$(read_prop "$SWITCH_TASK_FILE" state)"
    case "$_axes_state" in queued|running) printf 'mix|%s\n' "$AXES_TASK_FILE"; return ;; esac
    case "$_switch_state" in queued|running) printf 'switch|%s\n' "$SWITCH_TASK_FILE"; return ;; esac

    _axes_finished="$(read_prop "$AXES_TASK_FILE" finished)"
    _switch_finished="$(read_prop "$SWITCH_TASK_FILE" finished)"
    case "$_axes_finished" in ''|*[!0-9]*) _axes_finished=0 ;; esac
    case "$_switch_finished" in ''|*[!0-9]*) _switch_finished=0 ;; esac
    if [ "$_axes_finished" -ge "$_switch_finished" ] 2>/dev/null; then
        case "$_axes_state" in success|failed) printf 'mix|%s\n' "$AXES_TASK_FILE"; return ;; esac
        case "$_switch_state" in success|failed) printf 'switch|%s\n' "$SWITCH_TASK_FILE"; return ;; esac
    else
        case "$_switch_state" in success|failed) printf 'switch|%s\n' "$SWITCH_TASK_FILE"; return ;; esac
        case "$_axes_state" in success|failed) printf 'mix|%s\n' "$AXES_TASK_FILE"; return ;; esac
    fi
    printf 'none|\n'
}

status_json() {
    # App refresh is also a safe late-boot convergence point. The helper will
    # never consume a marker created during this same boot.
    type luoshu_text_reboot_reconcile >/dev/null 2>&1 && \
        LUOSHU_BOOT_RECONCILE_CACHED_ONLY=1 luoshu_text_reboot_reconcile >/dev/null 2>&1 || true
    _installed=false
    _version='未安装'
    _version_code=0
    if [ -f "$MODDIR/module.prop" ]; then
        _installed=true
        _version="$(read_prop "$MODDIR/module.prop" version)"
        _version_code="$(read_prop "$MODDIR/module.prop" versionCode)"
    fi
    _active="$(head -n1 "$MODDIR/config/active_font.conf" 2>/dev/null | tr -d '\r\n')"
    [ -n "$_active" ] || _active='default'
    _verification_file="$MODDIR/config/device-font-load-verification.conf"
    _verification_state="$(read_prop "$_verification_file" state)"
    _verification_mode="$(read_prop "$_verification_file" mode)"
    _verification_reason="$(read_prop "$_verification_file" reason)"
    _verification_active="$(read_prop "$_verification_file" activeFont)"
    _mount_state="$(read_prop "$MODDIR/config/self-mount.conf" state)"
    _mount_failed="$(read_prop "$MODDIR/config/self-mount.conf" failed)"
    [ -n "$_verification_state" ] || _verification_state='pending'
    [ -n "$_verification_mode" ] || _verification_mode='unknown'
    [ -n "$_mount_state" ] || _mount_state='unknown'

    _selected="$(select_task_file)"
    _task_type="${_selected%%|*}"
    _task_file="${_selected#*|}"
    _task_id=''
    _task_state='idle'
    _task_message='暂无后台任务'
    _task_progress=0
    if [ -n "$_task_file" ]; then
        _task_id="$(read_prop "$_task_file" task)"
        _task_state="$(read_prop "$_task_file" state)"
        _task_message="$(read_prop "$_task_file" message)"
        if [ "$_task_type" = mix ]; then
            _task_progress="$(read_prop "$_task_file" percent)"
        elif [ "$_task_state" = success ] || [ "$_task_state" = failed ]; then
            _task_progress=100
        else
            _task_progress=10
        fi
    fi
    case "$_task_progress" in ''|*[!0-9]*) _task_progress=0 ;; esac
    [ -n "$_task_state" ] || _task_state='idle'
    [ -n "$_task_message" ] || _task_message='暂无后台任务'

    _reboot_required=false
    [ -f "$TEXT_REBOOT_REQUIRED" ] && _reboot_required=true

    _effective_active='unknown'
    _font_effect_state='pending'
    if [ "$_active" = default ]; then
        _effective_active=default
        _font_effect_state=system
    elif [ "$_reboot_required" = true ]; then
        _font_effect_state=pending-reboot
    elif [ -n "$_verification_active" ] && [ "$_verification_active" != "$_active" ]; then
        _verification_state=pending
        _verification_mode=unknown
        _verification_reason=stale-verification
    elif [ "$_verification_state" = failed ] || [ "$_mount_state" = failed ]; then
        # The atomic self-mount transaction rolls every LuoShu layer back on
        # failure, so the only safe effective-font claim is the ROM default.
        _effective_active=default
        _font_effect_state=failed
        if [ "$_mount_state" = failed ]; then
            _verification_reason=self-mount-failed
        fi
    elif [ "$_verification_state" = verified ]; then
        case "$_verification_mode" in
            aligned|mount-verified|mount-confirmed)
                _effective_active="$_active"
                _font_effect_state=verified
                ;;
            *) _font_effect_state=unverified ;;
        esac
    else
        _font_effect_state=unverified
    fi

    printf '{"status":"ok","data":{"root":true,"installed":%s,"version":"%s","versionCode":%s,"active":"%s","effectiveActive":"%s","fontEffectState":"%s","verificationState":"%s","verificationMode":"%s","verificationReason":"%s","mountState":"%s","mountFailure":"%s","taskType":"%s","taskId":"%s","taskState":"%s","taskMessage":"%s","taskProgress":%s,"rebootRequired":%s,"rootManager":"%s","mountEngine":"%s","moduleDir":"%s"}}\n' \
        "$_installed" "$(json_escape "$_version")" "${_version_code:-0}" "$(json_escape "$_active")" \
        "$(json_escape "$_effective_active")" "$(json_escape "$_font_effect_state")" \
        "$(json_escape "$_verification_state")" "$(json_escape "$_verification_mode")" \
        "$(json_escape "$_verification_reason")" "$(json_escape "$_mount_state")" "$(json_escape "$_mount_failed")" \
        "$(json_escape "$_task_type")" "$(json_escape "$_task_id")" "$(json_escape "$_task_state")" \
        "$(json_escape "$_task_message")" "$_task_progress" "$_reboot_required" \
        "$(json_escape "$(root_manager)")" "$(json_escape "$(mount_engine)")" "$(json_escape "$MODDIR")"
}

manager_ready() {
    [ -x "$FONT_MANAGER" ] || [ -f "$FONT_MANAGER" ] || {
        printf '{"status":"error","message":"字体管理器不存在"}\n'
        return 1
    }
    return 0
}

switch_task_ready() {
    [ -x "$FONT_SWITCH_TASK" ] || [ -f "$FONT_SWITCH_TASK" ] || {
        printf '{"status":"error","message":"字体切换守卫不存在"}\n'
        return 1
    }
    return 0
}

mix_ready() {
    [ -x "$MIX_ENGINE" ] || [ -f "$MIX_ENGINE" ] || {
        printf '{"status":"error","message":"复合字体引擎不存在"}\n'
        return 1
    }
    return 0
}

font_file_sha256() {
    _file="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$_file" 2>/dev/null | awk '{print $1}'
    elif command -v busybox >/dev/null 2>&1; then
        busybox sha256sum "$_file" 2>/dev/null | awk '{print $1}'
    fi
}

preview_role_number() {
    case "$1" in
        thin) echo 100 ;; extralight) echo 200 ;; light) echo 300 ;; regular|normal) echo 400 ;;
        medium) echo 500 ;; semibold) echo 600 ;; bold) echo 700 ;; extrabold) echo 800 ;;
        black|heavy) echo 900 ;; *) echo 400 ;;
    esac
}

find_preview_source() {
    _family="$1"
    _target="${2:-400}"
    case "$_target" in ''|*[!0-9]*) _target=400 ;; esac
    _variable=''
    _best=''
    _best_score=99999
    for _f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
              "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_f" ] || continue
        if type detect_font_family >/dev/null 2>&1; then
            _detected="$(detect_font_family "$(basename "$_f")")"
        else
            _detected="$(basename "$_f")"; _detected="${_detected%.*}"; _detected="${_detected%-Regular}"
        fi
        [ "$_detected" = "$_family" ] || continue
        if type is_variable_font >/dev/null 2>&1 && is_variable_font "$_f" 2>/dev/null; then
            [ -n "$_variable" ] || _variable="$_f"
            continue
        fi
        _role=regular
        type detect_font_weight >/dev/null 2>&1 && _role="$(detect_font_weight "$(basename "$_f")")"
        _number="$(preview_role_number "$_role")"
        _score=$((_number - _target)); [ "$_score" -ge 0 ] 2>/dev/null || _score=$((-_score))
        if [ -z "$_best" ] || [ "$_score" -lt "$_best_score" ] 2>/dev/null; then
            _best="$_f"; _best_score="$_score"
        fi
    done
    if [ -n "$_variable" ]; then printf '%s\n' "$_variable"
    elif [ -n "$_best" ]; then printf '%s\n' "$_best"
    else return 1
    fi
}

preview_source_json() {
    _family="$1"
    _src="$(find_preview_source "$_family" "${2:-400}")"
    [ -f "$_src" ] || { printf '{"status":"error","message":"找不到预览字体"}\n'; return 1; }
    _bytes="$(wc -c < "$_src" 2>/dev/null | tr -d '[:space:]')"
    case "$_bytes" in ''|*[!0-9]*) _bytes=0 ;; esac
    _sha="$(font_file_sha256 "$_src")"
    printf '{"status":"ok","data":{"family":"%s","file":"%s","bytes":%s,"sha256":"%s"}}\n' \
        "$(json_escape "$_family")" "$(json_escape "$(basename "$_src")")" "$_bytes" "$(json_escape "$_sha")"
}

preview_export() {
    _family="$1"
    _dest="$2"
    _weight="${3:-400}"
    case "$_dest" in
        /data/user/0/io.github.xgl34222220.luoshu/cache/*|/data/data/io.github.xgl34222220.luoshu/cache/*|\
        /data/user/0/io.github.xgl34222220.luoshu.debug/cache/*|/data/data/io.github.xgl34222220.luoshu.debug/cache/*) ;;
        *) printf '{"status":"error","message":"预览目标目录不受信任"}\n'; return 1 ;;
    esac
    _src="$(find_preview_source "$_family" "$_weight")"
    [ -f "$_src" ] || { printf '{"status":"error","message":"找不到预览字体"}\n'; return 1; }
    mkdir -p "${_dest%/*}" 2>/dev/null || true
    cp -f "$_src" "$_dest" 2>/dev/null || { printf '{"status":"error","message":"无法导出预览字体"}\n'; return 1; }
    chmod 0644 "$_dest" 2>/dev/null || true
    _sha="$(font_file_sha256 "$_src")"
    printf '{"status":"ok","data":{"path":"%s","source":"%s","sha256":"%s"}}\n' \
        "$(json_escape "$_dest")" "$(json_escape "$(basename "$_src")")" "$(json_escape "$_sha")"
}

slot_trace_json() {
    [ -x "$PYBIN" ] && [ -f "$SLOT_TRACE" ] || {
        printf '{"status":"error","message":"字体槽追踪组件不可用"}\n'
        return 1
    }
    _inventory="$MODDIR/config/device_font_inventory.json"
    [ -s "$_inventory" ] || {
        printf '{"status":"error","message":"本机字体扫描清单不存在，请重新刷写或执行原厂字体扫描"}\n'
        return 1
    }

    _cache_id="$(read_prop "$MODDIR/config/device-font-engine.conf" cacheId)"
    _payload=''
    _overlay=''

    # 1) Prefer the engine-selected cache, but never let a stale/missing cacheId
    # make coverage unavailable after an in-place module upgrade.
    if [ -n "$_cache_id" ]; then
        _trace_root="$MODDIR/config/device-font-cache/$_cache_id"
        if [ -s "$_trace_root/payload/manifest.json" ] && [ -s "$_trace_root/overlay/overlay-manifest.json" ]; then
            _payload="$_trace_root/payload/manifest.json"
            _overlay="$_trace_root/overlay/overlay-manifest.json"
        fi
    fi

    # 2) Older non-cache payloads are still valid trace sources when both
    # manifests exist.
    if [ -z "$_payload" ]; then
        _direct_payload="$MODDIR/config/device-font-payload/manifest.json"
        _direct_overlay="$MODDIR/config/device-font-overlay/overlay-manifest.json"
        if [ -s "$_direct_payload" ] && [ -s "$_direct_overlay" ]; then
            _payload="$_direct_payload"
            _overlay="$_direct_overlay"
        fi
    fi

    # 3) Update migration intentionally clears device-font-engine.conf. If a
    # content-addressed cache survived and still matches the current template,
    # source and inventory, recover it through the cache resolver instead of
    # requiring another font switch merely to populate cacheId again.
    _active="$(head -n1 "$MODDIR/config/active_font.conf" 2>/dev/null | tr -d '\r\n')"
    [ -n "$_active" ] || _active=default
    if [ -z "$_payload" ] && [ "$_active" != default ] && [ -f "$DEVICE_FONT_CACHE" ]; then
        _lookup_root="$(MODDIR="$MODDIR" MODULE_DIR="$MODDIR" sh "$DEVICE_FONT_CACHE" lookup "$_active" 2>/dev/null || true)"
        case "$_lookup_root" in
            "$MODDIR"/config/device-font-cache/*)
                if [ -s "$_lookup_root/payload/manifest.json" ] && [ -s "$_lookup_root/overlay/overlay-manifest.json" ]; then
                    _payload="$_lookup_root/payload/manifest.json"
                    _overlay="$_lookup_root/overlay/overlay-manifest.json"
                fi
                ;;
        esac
    fi

    _candidates="$MODDIR/config/device_font_candidates.json"

    # Current LuoShu releases use the physical-safe next-boot payload as the
    # authoritative runtime. It deliberately has no v2 device-font manifest.
    # Trace that live payload directly instead of making the App depend on an
    # obsolete manifest that the switch core never creates.
    _runtime_core="$(read_prop "$MODDIR/config/font_runtime_legacy_v14_4.conf" core)"
    if { [ "$_runtime_core" = physical-safe-v1 ] || [ ! -s "$_payload" ] || [ ! -s "$_overlay" ]; } && \
       [ "$_active" != default ] && [ -d "$MODDIR/.luoshu-payload" ]; then
        set -- "$SLOT_TRACE" \
            --inventory "$_inventory" \
            --physical-root "$MODDIR/.luoshu-payload" \
            --active-font "$_active" \
            --mount-state "$MODDIR/config/self-mount.conf" \
            --output "$MODDIR/config/device-font-slot-trace.json"
        [ ! -s "$_candidates" ] || set -- "$@" --candidates "$_candidates"

        _load_state="$(read_prop "$MODDIR/config/device-font-load-verification.conf" state)"
        _boot_state="$(read_prop "$MODDIR/config/font-payload-boot.conf" state)"
        _mount_state="$(read_prop "$MODDIR/config/self-mount.conf" state)"
        if [ "$_load_state" = verified ] || \
           { [ "$_boot_state" = confirmed ] && \
             { [ "$_mount_state" = mounted ] || [ "$_mount_state" = confirmed ] || [ "$_mount_state" = degraded ]; }; }; then
            set -- "$@" --physical-confirmed
        fi

        PYTHONHOME="$PYROOT" \
        PYTHONPATH="$MODDIR/common:$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages" \
        LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
            "$PYBIN" "$@"
        return $?
    fi

    [ -s "$_payload" ] && [ -s "$_overlay" ] || {
        printf '{"status":"error","message":"当前物理字体负载不存在，无法生成字体覆盖数据"}\n'
        return 1
    }

    set -- "$SLOT_TRACE" --inventory "$_inventory" --payload "$_payload" --overlay "$_overlay" \
        --output "$MODDIR/config/device-font-slot-trace.json"
    _verification="$MODDIR/config/device-font-load-verification.json"
    [ ! -s "$_verification" ] || set -- "$@" --verification "$_verification"
    [ ! -s "$_candidates" ] || set -- "$@" --candidates "$_candidates"
    PYTHONHOME="$PYROOT" \
    PYTHONPATH="$MODDIR/common:$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages" \
    LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$PYBIN" "$@"
}

coverage_busy() {
    _selected="$(select_task_file)"
    _task_file="${_selected#*|}"
    [ -n "$_task_file" ] || return 1
    _state="$(read_prop "$_task_file" state)"
    case "$_state" in queued|running) return 0 ;; *) return 1 ;; esac
}

coverage_mark_rebuild() {
    _font="$1"
    _pending="$MODDIR/config/font-payload-rebuild-pending.conf"
    _tmp="${_pending}.tmp.$$"
    mkdir -p "$MODDIR/config" 2>/dev/null || return 1
    {
        printf 'state=pending\n'
        printf 'font=%s\n' "$_font"
        printf 'reason=coverage-remediate\n'
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_tmp" 2>/dev/null || return 1
    mv -f "$_tmp" "$_pending" 2>/dev/null || { rm -f "$_tmp" 2>/dev/null; return 1; }
    chmod 0600 "$_pending" 2>/dev/null || true
}

coverage_reapply() {
    coverage_busy && {
        printf '{"status":"error","message":"已有字体任务正在运行，请等待完成"}\n'
        return 1
    }
    _active="$(head -n1 "$MODDIR/config/active_font.conf" 2>/dev/null | tr -d '\r\n')"
    [ -n "$_active" ] || _active=default
    [ "$_active" != default ] || {
        printf '{"status":"error","message":"当前使用系统默认字体，没有可补齐的洛书字体负载"}\n'
        return 1
    }
    coverage_mark_rebuild "$_active" || {
        printf '{"status":"error","message":"无法创建字体补齐事务"}\n'
        return 1
    }

    if [ "$_active" = mix ]; then
        mix_ready || { rm -f "$MODDIR/config/font-payload-rebuild-pending.conf"; return 1; }
        _source="$MODDIR/config/axes_mix.conf"
        [ -s "$_source" ] || _source="$MODDIR/config/font_mix.conf"
        _cjk="$(read_prop "$_source" cjk)"
        _latin="$(read_prop "$_source" latin)"
        _digit="$(read_prop "$_source" digit)"
        _cjk_weight="$(read_prop "$_source" cjkWeight)"; [ -n "$_cjk_weight" ] || _cjk_weight=400
        _latin_weight="$(read_prop "$_source" latinWeight)"; [ -n "$_latin_weight" ] || _latin_weight=400
        _digit_weight="$(read_prop "$_source" digitWeight)"; [ -n "$_digit_weight" ] || _digit_weight=400
        _cjk_axes="$(read_prop "$_source" cjkAxes)"; [ -n "$_cjk_axes" ] || _cjk_axes="wght=$_cjk_weight"
        _latin_axes="$(read_prop "$_source" latinAxes)"; [ -n "$_latin_axes" ] || _latin_axes="wght=$_latin_weight"
        _digit_axes="$(read_prop "$_source" digitAxes)"; [ -n "$_digit_axes" ] || _digit_axes="wght=$_digit_weight"
        if [ -z "$_cjk" ] || [ -z "$_latin" ] || [ -z "$_digit" ]; then
            rm -f "$MODDIR/config/font-payload-rebuild-pending.conf" 2>/dev/null || true
            printf '{"status":"error","message":"当前组合字体配置不完整，无法自动补齐"}\n'
            return 1
        fi
        _out="$(LUOSHU_FORCE_REBUILD=1 MODDIR="$MODDIR" sh "$MIX_ENGINE" start "$_cjk" "$_latin" "$_digit" "$_cjk_axes" "$_latin_axes" "$_digit_axes" 2>&1)"
        _rc=$?
    else
        switch_task_ready || { rm -f "$MODDIR/config/font-payload-rebuild-pending.conf"; return 1; }
        _out="$(LUOSHU_FORCE_REBUILD=1 MODDIR="$MODDIR" sh "$FONT_SWITCH_TASK" start "$_active" 2>&1)"
        _rc=$?
    fi
    if [ "$_rc" -ne 0 ]; then
        rm -f "$MODDIR/config/font-payload-rebuild-pending.conf" 2>/dev/null || true
        printf '%s\n' "$_out"
        return "$_rc"
    fi
    printf '%s\n' "$_out"
}

coverage_verify() {
    [ -f "$LOAD_VERIFY" ] && MODDIR="$MODDIR" sh "$LOAD_VERIFY" verify >/dev/null 2>&1 || true
    slot_trace_json
}

coverage_export() {
    _out_dir="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}/reports"
    _out="$_out_dir/LuoShu-font-coverage.json"
    _tmp="${_out}.tmp.$$"
    mkdir -p "$_out_dir" 2>/dev/null || {
        printf '{"status":"error","message":"无法创建覆盖报告目录"}\n'
        return 1
    }
    slot_trace_json > "$_tmp" 2>/dev/null || {
        rm -f "$_tmp" 2>/dev/null || true
        printf '{"status":"error","message":"字体覆盖报告生成失败"}\n'
        return 1
    }
    grep -q '"schema":"device-font-slot-trace-v1"' "$_tmp" 2>/dev/null || {
        rm -f "$_tmp" 2>/dev/null || true
        printf '{"status":"error","message":"字体覆盖报告格式无效"}\n'
        return 1
    }
    mv -f "$_tmp" "$_out" 2>/dev/null || {
        rm -f "$_tmp" 2>/dev/null || true
        printf '{"status":"error","message":"字体覆盖报告保存失败"}\n'
        return 1
    }
    chmod 0644 "$_out" 2>/dev/null || true
    printf '{"status":"ok","data":{"path":"%s"}}\n' "$(json_escape "$_out")"
}

weight_axis_info() {
    _family="$1"
    _src="$(find_preview_source "$_family")"
    [ -f "$_src" ] || { printf '{"status":"error","message":"找不到字体轴来源"}\n'; return 1; }
    [ -f "$AXIS_INFO" ] && [ -x "$PYBIN" ] || { printf '{"status":"error","message":"字体轴分析器不可用"}\n'; return 1; }
    export PYTHONHOME="$PYROOT"
    export PYTHONPATH="$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages"
    export LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    "$PYBIN" "$AXIS_INFO" "$_src"
}

case "${1:-status}" in
    status) status_json ;;
    fonts)
        manager_ready || exit 1
        if [ "${2:-}" = refresh ]; then sh "$FONT_MANAGER" action list refresh
        else sh "$FONT_MANAGER" action list
        fi
        ;;
    import_file)
        if [ -f "$NATIVE_IMPORT" ]; then
            MODDIR="$MODDIR" sh "$NATIVE_IMPORT" "${2:-}" "${3:-}"
        else
            printf '{"status":"error","message":"原生导入组件不可用"}\n'
        fi
        ;;
    preview_source) preview_source_json "${2:-}" "${3:-400}" ;;
    preview_export) preview_export "${2:-}" "${3:-}" "${4:-400}" ;;
    weight_axis) weight_axis_info "${2:-}" ;;
    prewarm)
        if [ -f "$SAFE_SWITCH" ]; then
            MODDIR="$MODDIR" LUOSHU_PUBLIC_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}" \
                sh "$SAFE_SWITCH" action prewarm-start "${2:-}" >/dev/null 2>&1 || true
            printf '{"status":"ok","data":{"font":"%s","scheduled":true}}\n' "$(json_escape "${2:-}")"
        else
            printf '{"status":"error","message":"字体预热组件不可用"}\n'
        fi
        ;;
    validate)
        manager_ready || exit 1
        if [ -f "$SAFE_SWITCH" ] && [ -n "${2:-}" ] && [ "${2:-}" != default ]; then
            MODDIR="$MODDIR" LUOSHU_PUBLIC_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}" \
                sh "$SAFE_SWITCH" action prewarm-start "${2:-}" >/dev/null 2>&1 || true
        fi
        sh "$FONT_MANAGER" action validate "${2:-}"
        ;;
    stock_scan) manager_ready || exit 1; sh "$FONT_MANAGER" action stock_scan ;;
    slot_trace|coverage) slot_trace_json ;;
    coverage_verify) coverage_verify ;;
    coverage_reapply) coverage_reapply ;;
    coverage_export) coverage_export ;;
    switch_start) switch_task_ready || exit 1; MODDIR="$MODDIR" sh "$FONT_SWITCH_TASK" start "${2:-default}" ;;
    switch_status) switch_task_ready || exit 1; MODDIR="$MODDIR" sh "$FONT_SWITCH_TASK" status "${2:-}" ;;
    delete) manager_ready || exit 1; sh "$FONT_MANAGER" action delete "${2:-}" ;;
    mix_config) mix_ready || exit 1; sh "$MIX_ENGINE" config ;;
    mix_start) mix_ready || exit 1; sh "$MIX_ENGINE" start "${2:-}" "${3:-}" "${4:-}" "${5:-wght=400}" "${6:-wght=400}" "${7:-wght=400}" ;;
    mix_status) mix_ready || exit 1; sh "$MIX_ENGINE" status "${2:-}" ;;
    reboot) manager_ready || exit 1; sh "$FONT_MANAGER" action reboot_device ;;
    logs)
        _lines="${2:-160}"
        case "$_lines" in ''|*[!0-9]*) _lines=160 ;; esac
        [ "$_lines" -le 500 ] 2>/dev/null || _lines=500
        tail -n "$_lines" "$MODDIR/logs/fontswitch.log" 2>/dev/null
        ;;
    *) printf '{"status":"error","message":"未知 App 桥命令"}\n' ;;
esac
exit 0
