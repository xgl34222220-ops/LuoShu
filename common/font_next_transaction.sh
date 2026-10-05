#!/system/bin/sh
# Publish next payload, next-state and selection as one recoverable transaction.
# Callers hold the font switch lock; mounted immutable generations stay separate.
set +e

_lnt_files() {
    printf '%s\n' font-payload-next.conf active_font.conf text_reboot_required.conf \
        font_runtime_legacy_v14_4.conf font-payload-schema.conf \
        device-font-engine.conf device-font-installed.conf device-font-dynamic-mount.conf \
        device-font-load-verification.json device-font-load-verification.conf \
        font-payload-rebuild-pending.conf font-payload-reapply-notified.conf device-font-cache-pending.conf \
        mix-commit.conf
}

_lnt_setup() {
    _lnt_module=$(CDPATH= cd -P -- "$1" 2>/dev/null && pwd) || return 1
    [ "$_lnt_module" != / ] && [ ! -e "$_lnt_module/.git" ] || return 1
    _lnt_config="$_lnt_module/.luoshu-state/config"
    _lnt_backup="$_lnt_module/.luoshu-state/backup"
    _lnt_dir="$_lnt_backup/next-transaction"
    _lnt_next="$_lnt_module/.luoshu-payload-next"
    for _lnt_safe in "$_lnt_module/.luoshu-state" "$_lnt_config" "$_lnt_backup" "$_lnt_dir" "$_lnt_next"; do
        [ ! -L "$_lnt_safe" ] || return 1
        [ ! -e "$_lnt_safe" ] || [ -d "$_lnt_safe" ] || return 1
    done
    [ -d "$_lnt_config" ] && [ -d "$_lnt_backup" ] || return 1
    for _lnt_name in $(_lnt_files); do
        [ ! -L "$_lnt_config/$_lnt_name" ] || return 1
        [ ! -e "$_lnt_config/$_lnt_name" ] || [ -f "$_lnt_config/$_lnt_name" ] || return 1
    done
    _lnt_journal="$_lnt_dir/journal.conf"
}

_lnt_file_value() {
    [ -f "$1" ] && [ ! -L "$1" ] || return 1
    sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1
}

_lnt_value() { _lnt_file_value "$_lnt_journal" "$1"; }

_lnt_start() {
    _lnt_stat=$(cat "/proc/$1/stat" 2>/dev/null) || return 1
    _lnt_tail=${_lnt_stat##*) }
    set -- $_lnt_tail
    [ "$#" -ge 20 ] && [ "$1" != Z ] || return 1
    shift 19
    printf '%s\n' "$1"
}

_lnt_write_journal() {
    _lnt_phase="$1"; _lnt_tmp="$_lnt_journal.tmp.$$"
    {
        printf 'schema=luoshu-next-transaction-v1\nstate=%s\n' "$_lnt_phase"
        printf 'pid=%s\nstart=%s\nboot=%s\npayloadPresent=%s\nfont=%s\nrequestId=%s\n' \
            "$_lnt_pid" "$_lnt_identity" "$_lnt_boot" "$_lnt_payload_present" "$_lnt_font" "$_lnt_request"
    } > "$_lnt_tmp" && mv -f "$_lnt_tmp" "$_lnt_journal"
}

_lnt_read_journal() {
    [ "$(_lnt_value schema)" = luoshu-next-transaction-v1 ] || return 1
    _lnt_state=$(_lnt_value state)
    case "$_lnt_state" in preparing|publishing|committed|rolled-back) ;; *) return 1 ;; esac
    _lnt_pid=$(_lnt_value pid); _lnt_identity=$(_lnt_value start); _lnt_boot=$(_lnt_value boot)
    _lnt_payload_present=$(_lnt_value payloadPresent)
    _lnt_font=$(_lnt_value font); _lnt_request=$(_lnt_value requestId)
    for _lnt_number in "$_lnt_pid" "$_lnt_identity"; do
        case "$_lnt_number" in ''|*[!0-9]*) return 1 ;; esac
    done
    case "$_lnt_payload_present" in true|false) ;; *) return 1 ;; esac
    [ -n "$_lnt_boot" ] && [ -n "$_lnt_font" ] && [ -n "$_lnt_request" ]
}

_lnt_owner_live() {
    [ "$_lnt_boot" = "$(cat /proc/sys/kernel/random/boot_id 2>/dev/null)" ] && \
        [ "$_lnt_identity" = "$(_lnt_start "$_lnt_pid")" ]
}

_lnt_owner_is_self() {
    # A builtin read identifies this shell even when /proc exposes outer PIDs.
    IFS= read -r _lnt_self_stat < /proc/self/stat || return 1
    [ "$_lnt_pid" = "${_lnt_self_stat%% *}" ]
}

_lnt_validate_snapshot() {
    [ -d "$_lnt_dir/files" ] && [ ! -L "$_lnt_dir/files" ] || return 1
    [ -f "$_lnt_dir/presence.conf" ] && [ ! -L "$_lnt_dir/presence.conf" ] || return 1
    _lnt_expected=0
    for _lnt_name in $(_lnt_files); do
        _lnt_present=$(sed -n "s/^${_lnt_name}=//p" "$_lnt_dir/presence.conf")
        case "$_lnt_present" in
            true) [ -f "$_lnt_dir/files/$_lnt_name" ] && [ ! -L "$_lnt_dir/files/$_lnt_name" ] || return 1 ;;
            false) ;;
            *) return 1 ;;
        esac
        _lnt_expected=$((_lnt_expected + 1))
    done
    [ "$(wc -l < "$_lnt_dir/presence.conf" | tr -d ' ')" = "$_lnt_expected" ]
}

_lnt_discard() {
    _lnt_discard_phase=$(_lnt_value state)
    # Preserve the journal if deletion of any larger backup partially fails.
    rm -rf "$_lnt_dir/payload" "$_lnt_dir/files" || return 1
    rm -f "$_lnt_dir/presence.conf" "$_lnt_dir/restore-state.conf" "$_lnt_dir/new-state.conf" \
        "$_lnt_dir"/*.tmp.* || return 1
    rm -f "$_lnt_journal" || return 1
    if ! rmdir "$_lnt_dir"; then
        _lnt_write_journal "$_lnt_discard_phase" || return 1
        return 1
    fi
    return 0
}

_lnt_rollback() {
    case "$_lnt_state" in
        preparing|rolled-back) _lnt_discard; return $? ;;
        committed) return 1 ;;
    esac
    _lnt_validate_snapshot || return 1
    [ ! -L "$_lnt_dir/payload" ] || return 1
    if [ -d "$_lnt_dir/payload" ]; then
        rm -rf "$_lnt_next" || return 1
        mv "$_lnt_dir/payload" "$_lnt_next" || return 1
    elif [ "$_lnt_payload_present" = false ]; then
        rm -rf "$_lnt_next" || return 1
    else
        # The original rename never ran, or a rollback retry already restored it.
        [ -d "$_lnt_next" ] || return 1
    fi
    for _lnt_name in $(_lnt_files); do
        _lnt_present=$(sed -n "s/^${_lnt_name}=//p" "$_lnt_dir/presence.conf")
        if [ "$_lnt_present" = true ]; then
            _lnt_restore="$_lnt_dir/restore-state.conf"
            cp -p "$_lnt_dir/files/$_lnt_name" "$_lnt_restore" && \
                mv -f "$_lnt_restore" "$_lnt_config/$_lnt_name" || return 1
        else
            rm -f "$_lnt_config/$_lnt_name" || return 1
        fi
    done
    _lnt_write_journal rolled-back || return 1
    _lnt_discard
}

_lnt_boot_adopted() {
    _lnt_adopt_font="$1"; _lnt_adopt_request="$2"
    [ -n "$_lnt_adopt_font" ] && [ -n "$_lnt_adopt_request" ] || return 1
    [ ! -e "$_lnt_next" ] || return 1
    [ "$(head -n1 "$_lnt_config/active_font.conf" 2>/dev/null)" = "$_lnt_adopt_font" ] || return 1
    if [ "$_lnt_adopt_font" = default ]; then
        # Stable boot deletes the activation record for default; its payload
        # marker still identifies exactly which prepared selection was consumed.
        _lnt_marker="$_lnt_module/.luoshu-payload/.luoshu-next-transaction.conf"
        [ ! -L "$_lnt_module/.luoshu-payload" ] && \
            [ "$(_lnt_file_value "$_lnt_marker" schema)" = luoshu-next-payload-v1 ] && \
            [ "$(_lnt_file_value "$_lnt_marker" font)" = default ] && \
            [ "$(_lnt_file_value "$_lnt_marker" requestId)" = "$_lnt_adopt_request" ] && \
            [ ! -e "$_lnt_config/font_runtime_legacy_v14_4.conf" ]
    else
        _lnt_activated="$_lnt_config/font-payload-activated.conf"
        [ "$(_lnt_file_value "$_lnt_activated" font)" = "$_lnt_adopt_font" ] && \
            [ "$(_lnt_file_value "$_lnt_activated" requestId)" = "$_lnt_adopt_request" ] && \
            [ "$(_lnt_file_value "$_lnt_activated" bootId)" = "$_lnt_now_boot" ]
    fi
}

luoshu_next_transaction_recover() {
    _lnt_setup "$1" || return 1
    [ -d "$_lnt_dir" ] || return 0
    _lnt_read_journal || return 1
    if _lnt_owner_live && ! _lnt_owner_is_self; then return 2; fi
    _lnt_now_boot=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null) || return 1
    if [ "$_lnt_state" = publishing ] && [ "$_lnt_boot" != "$_lnt_now_boot" ]; then
        if _lnt_boot_adopted "$_lnt_font" "$_lnt_request"; then
            # Do not restore stale B metadata over C adopted by early boot.
            _lnt_write_journal committed || return 1
            _lnt_discard; return $?
        fi
        _lnt_validate_snapshot || return 1
        _lnt_prior_state="$_lnt_dir/files/font-payload-next.conf"
        if [ "$_lnt_payload_present" = true ] && [ ! -d "$_lnt_dir/payload" ] && \
           _lnt_boot_adopted "$(_lnt_file_value "$_lnt_prior_state" font)" \
                "$(_lnt_file_value "$_lnt_prior_state" requestId)"; then
            _lnt_write_journal committed || return 1
            _lnt_discard; return $?
        fi
    fi
    case "$_lnt_state" in committed) _lnt_discard ;; *) _lnt_rollback ;; esac
}

luoshu_next_transaction_begin() {
    _lnt_begin_module="$1"; _lnt_stage="$2"; _lnt_new_state="$3"
    luoshu_next_transaction_recover "$_lnt_begin_module" || return $?
    for _lnt_input in "$_lnt_stage" "$_lnt_new_state"; do
        [ ! -L "$_lnt_input" ] || return 1
        case "${_lnt_input##*/}" in ''|.|..) return 1 ;; esac
        _lnt_parent=$(CDPATH= cd -P -- "${_lnt_input%/*}" 2>/dev/null && pwd) || return 1
        case "$_lnt_parent/" in "$_lnt_module/.luoshu-state/tmp/"*) ;; *) return 1 ;; esac
    done
    [ -d "$_lnt_stage" ] && [ -f "$_lnt_new_state" ] || return 1
    _lnt_font=$(_lnt_file_value "$_lnt_new_state" font)
    _lnt_request=$(_lnt_file_value "$_lnt_new_state" requestId)
    [ -n "$_lnt_font" ] && [ -n "$_lnt_request" ] || return 1
    _lnt_marker="$_lnt_stage/.luoshu-next-transaction.conf"
    [ ! -L "$_lnt_marker" ] || return 1
    # Staging metadata may be hardlinked from a previous immutable payload.
    # Replace its directory entry atomically; never truncate the old inode.
    {
        printf 'schema=luoshu-next-payload-v1\nfont=%s\nrequestId=%s\n' "$_lnt_font" "$_lnt_request"
    } > "$_lnt_marker.tmp.$$" && chmod 0600 "$_lnt_marker.tmp.$$" && \
        mv -f "$_lnt_marker.tmp.$$" "$_lnt_marker" || return 1
    IFS= read -r _lnt_self_stat < /proc/self/stat || return 1
    _lnt_pid=${_lnt_self_stat%% *}; _lnt_identity=$(_lnt_start "$_lnt_pid") || return 1
    _lnt_boot=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null) || return 1
    _lnt_payload_present=false; [ ! -d "$_lnt_next" ] || _lnt_payload_present=true
    # Publish the first journal together with its directory. A killed mkdir /
    # journal writer must leave only task-owned temporary, never a canonical
    # journal-less reservation which would block every subsequent switch.
    _lnt_canonical_dir="$_lnt_dir"
    _lnt_init_root="${LUOSHU_TASK_SCOPE_TMPDIR:-${_lnt_stage%/*}}"
    [ ! -L "$_lnt_init_root" ] || return 1
    _lnt_init_parent=$(CDPATH= cd -P -- "$_lnt_init_root" 2>/dev/null && pwd) || return 1
    case "$_lnt_init_parent/" in "$_lnt_module/.luoshu-state/tmp/"*) ;; *) return 1 ;; esac
    _lnt_init_dir=$(mktemp -d "$_lnt_init_parent/next-transaction-init.XXXXXX") || return 1
    _lnt_dir="$_lnt_init_dir"; _lnt_journal="$_lnt_dir/journal.conf"
    if ! _lnt_write_journal preparing || ! mv "$_lnt_init_dir" "$_lnt_canonical_dir"; then
        rm -rf "$_lnt_init_dir" 2>/dev/null || true
        _lnt_dir="$_lnt_canonical_dir"; _lnt_journal="$_lnt_dir/journal.conf"
        return 1
    fi
    _lnt_dir="$_lnt_canonical_dir"; _lnt_journal="$_lnt_dir/journal.conf"
    mkdir -m 0700 "$_lnt_dir/files" || return 1
    _lnt_presence="$_lnt_dir/presence.conf.tmp.$$"; : > "$_lnt_presence" || return 1
    for _lnt_name in $(_lnt_files); do
        _lnt_present=false
        if [ -f "$_lnt_config/$_lnt_name" ]; then
            cp -p "$_lnt_config/$_lnt_name" "$_lnt_dir/files/$_lnt_name" || return 1
            _lnt_present=true
        fi
        printf '%s=%s\n' "$_lnt_name" "$_lnt_present" >> "$_lnt_presence" || return 1
    done
    mv "$_lnt_presence" "$_lnt_dir/presence.conf" || return 1
    _lnt_write_journal publishing || return 1
    if [ "$_lnt_payload_present" = true ]; then
        mv "$_lnt_next" "$_lnt_dir/payload" || { _lnt_state=publishing; _lnt_rollback; return 1; }
    fi
    if ! mv "$_lnt_stage" "$_lnt_next" || ! cp -p "$_lnt_new_state" "$_lnt_dir/new-state.conf" || \
       ! mv -f "$_lnt_dir/new-state.conf" "$_lnt_config/font-payload-next.conf"; then
        _lnt_state=publishing; _lnt_rollback; return 1
    fi
    return 0
}

luoshu_next_transaction_commit() {
    _lnt_setup "$1" && _lnt_read_journal || return 1
    _lnt_owner_is_self && [ "$_lnt_state" = publishing ] && _lnt_owner_live || return 1
    _lnt_write_journal committed || return 1
    if ! _lnt_discard; then
        printf '%s\n' '[NEXT-TRANSACTION] selection committed; backup cleanup deferred to next recovery' >&2
    fi
    return 0
}

luoshu_next_transaction_mix_receipt() {
    _lnt_setup "$1" && _lnt_read_journal || return 1
    _lnt_owner_is_self && [ "$_lnt_state" = publishing ] && _lnt_owner_live || return 1
    [ "$_lnt_font" = mix ] || return 0
    _lnt_published_state="$_lnt_config/font-payload-next.conf"
    [ "$(_lnt_file_value "$_lnt_published_state" font)" = mix ] && \
        [ "$(_lnt_file_value "$_lnt_published_state" requestId)" = "$_lnt_request" ] || return 1
    _lnt_receipt_root="${LUOSHU_TASK_SCOPE_TMPDIR:-$_lnt_module/.luoshu-state/tmp}"
    [ ! -L "$_lnt_receipt_root" ] || return 1
    _lnt_receipt_parent=$(CDPATH= cd -P -- "$_lnt_receipt_root" 2>/dev/null && pwd) || return 1
    case "$_lnt_receipt_parent/" in "$_lnt_module/.luoshu-state/tmp/"*) ;; *) return 1 ;; esac
    _lnt_receipt_tmp=$(mktemp "$_lnt_receipt_parent/mix-commit-receipt.XXXXXX") || return 1
    # The receipt participates in the same rollback snapshot as NEXT and the
    # selected font. Readers use it only after the journal has been resolved.
    if ! {
        printf 'font=mix\nrequestId=%s\nbootId=%s\n' "$_lnt_request" "$_lnt_boot"
        for _lnt_role in cjk latin digit; do
            printf '%s=%s\n' "$_lnt_role" "$(_lnt_file_value "$_lnt_published_state" "$_lnt_role")"
        done
    } > "$_lnt_receipt_tmp" || ! mv -f "$_lnt_receipt_tmp" "$_lnt_config/mix-commit.conf"; then
        rm -f "$_lnt_receipt_tmp" 2>/dev/null || true
        return 1
    fi
    return 0
}

luoshu_next_transaction_rollback() {
    _lnt_setup "$1" || return 1
    [ -d "$_lnt_dir" ] || return 0
    _lnt_read_journal || return 1
    # EXIT traps also run for optional prewarm requests that never published.
    # They must not recover another publisher without holding its font lock.
    _lnt_owner_is_self && _lnt_owner_live || return 2
    _lnt_rollback
}
