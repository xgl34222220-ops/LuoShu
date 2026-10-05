#!/system/bin/sh
# One module-owned writable tree. Public fonts and mounted payloads stay separate.

_luoshu_runtime_merge() (
    _lrpm_source="$1"
    _lrpm_target="$2"
    _lrpm_saved="$3"
    # Never traverse a symbolic link while merging an interrupted migration.
    if [ -d "$_lrpm_source" ] && [ ! -L "$_lrpm_source" ] && \
       [ -d "$_lrpm_target" ] && [ ! -L "$_lrpm_target" ]; then
        for _lrpm_item in "$_lrpm_source"/* "$_lrpm_source"/.[!.]* "$_lrpm_source"/..?*; do
            [ -e "$_lrpm_item" ] || [ -L "$_lrpm_item" ] || continue
            _lrpm_name=${_lrpm_item##*/}
            _luoshu_runtime_merge "$_lrpm_item" "$_lrpm_target/$_lrpm_name" \
                "$_lrpm_saved/$_lrpm_name" || return 1
        done
        rmdir "$_lrpm_source" 2>/dev/null || return 1
    elif [ -e "$_lrpm_target" ] || [ -L "$_lrpm_target" ]; then
        # The centralized copy remains authoritative; retain every conflicting
        # old file for recovery instead of replacing either version.
        mkdir -p "${_lrpm_saved%/*}" 2>/dev/null || return 1
        [ ! -e "$_lrpm_saved" ] && [ ! -L "$_lrpm_saved" ] || return 1
        mv "$_lrpm_source" "$_lrpm_saved" 2>/dev/null || return 1
    else
        mkdir -p "${_lrpm_target%/*}" 2>/dev/null || return 1
        mv "$_lrpm_source" "$_lrpm_target" 2>/dev/null || return 1
    fi
)

_luoshu_runtime_compat_safe() (
    _lrpcs_module="$1"
    _lrpcs_name="$2"
    _lrpcs_path="$_lrpcs_module/$_lrpcs_name"
    if [ -L "$_lrpcs_path" ]; then
        _lrpcs_link=$(readlink "$_lrpcs_path" 2>/dev/null) || return 1
        case "$_lrpcs_link" in
            ".luoshu-state/$_lrpcs_name"|"$_lrpcs_module/.luoshu-state/$_lrpcs_name") return 0 ;;
            *) return 1 ;;
        esac
    fi
    [ ! -e "$_lrpcs_path" ] || [ -d "$_lrpcs_path" ]
)

_luoshu_runtime_validate() (
    _lrpp_module="$1"
    _lrpp_state="$_lrpp_module/.luoshu-state"
    [ ! -e "$_lrpp_module/.git" ] && [ ! -L "$_lrpp_module/.git" ] || return 1
    [ ! -L "$_lrpp_state" ] || return 1
    [ ! -e "$_lrpp_state" ] || [ -d "$_lrpp_state" ] || return 1
    # Validate the complete allowlist before moving any legacy directory.
    for _lrpp_name in config logs cache backup reports; do
        _luoshu_runtime_compat_safe "$_lrpp_module" "$_lrpp_name" || return 1
    done
    for _lrpp_name in config logs cache tasks tmp backup reports migration-conflicts; do
        [ ! -L "$_lrpp_state/$_lrpp_name" ] || return 1
        [ ! -e "$_lrpp_state/$_lrpp_name" ] || [ -d "$_lrpp_state/$_lrpp_name" ] || return 1
    done
)

_luoshu_runtime_prepare() (
    _lrpp_module="$1"
    _lrpp_state="$_lrpp_module/.luoshu-state"
    _luoshu_runtime_validate "$_lrpp_module" || return 1
    _lrpp_ready=true
    [ "$(cat "$_lrpp_state/paths-v1.conf" 2>/dev/null)" = 'schema=luoshu-runtime-paths-v1' ] || _lrpp_ready=false
    for _lrpp_name in config logs cache backup reports; do
        [ -L "$_lrpp_module/$_lrpp_name" ] && [ -d "$_lrpp_state/$_lrpp_name" ] || _lrpp_ready=false
    done
    [ -d "$_lrpp_state/tasks" ] && [ -d "$_lrpp_state/tmp" ] || _lrpp_ready=false
    [ "$_lrpp_ready" != true ] || return 0
    _lrpp_program="$_lrpp_module/common/runtime_paths_lock.py"
    [ -f "$_lrpp_program" ] || return 1
    if [ -n "${LUOSHU_RUNTIME_PATHS_PYTHON:-}" ]; then
        "$LUOSHU_RUNTIME_PATHS_PYTHON" "$_lrpp_program" "$_lrpp_module"
    else
        _lrpp_pyroot="$_lrpp_module/common/python"
        _lrpp_python="$_lrpp_pyroot/bin/luoshu-python"
        [ -x "$_lrpp_python" ] || return 1
        PYTHONHOME="$_lrpp_pyroot" \
        PYTHONPATH="$_lrpp_pyroot/lib/python3.14:$_lrpp_pyroot/lib/python3.14/site-packages" \
        LD_LIBRARY_PATH="$_lrpp_pyroot/lib:$_lrpp_pyroot/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
            "$_lrpp_python" "$_lrpp_program" "$_lrpp_module"
    fi
)

# Only the short-lived kernel-lock holder calls this function, in its own shell.
# It runs in that same process so SIGKILL releases the migration lock immediately.
_luoshu_runtime_prepare_locked() {
    _lrpp_module="$1"
    _lrpp_state="$_lrpp_module/.luoshu-state"
    _luoshu_runtime_validate "$_lrpp_module" || return 1
    umask 077
    trap '[ -z "${_lrpp_conflicts:-}" ] || rmdir "$_lrpp_conflicts" 2>/dev/null || true' EXIT
    trap 'exit 129' HUP
    trap 'exit 130' INT
    trap 'exit 143' TERM
    mkdir -p "$_lrpp_state/migration-conflicts" 2>/dev/null || return 1
    _lrpp_conflicts=$(mktemp -d "$_lrpp_state/migration-conflicts/recovery.XXXXXX") || return 1
    for _lrpp_name in config logs cache backup reports; do
        _luoshu_runtime_compat_safe "$_lrpp_module" "$_lrpp_name" || return 1
        _lrpp_old="$_lrpp_module/$_lrpp_name"
        _lrpp_new="$_lrpp_state/$_lrpp_name"
        [ ! -L "$_lrpp_new" ] || return 1
        if [ -d "$_lrpp_old" ] && [ ! -L "$_lrpp_old" ]; then
            _luoshu_runtime_merge "$_lrpp_old" "$_lrpp_new" "$_lrpp_conflicts/$_lrpp_name" || return 1
        fi
        mkdir -p "$_lrpp_new" 2>/dev/null || return 1
        if [ ! -L "$_lrpp_old" ]; then
            ln -s ".luoshu-state/$_lrpp_name" "$_lrpp_old" 2>/dev/null || return 1
        fi
    done
    mkdir -p "$_lrpp_state/tasks" "$_lrpp_state/tmp" 2>/dev/null || return 1
    _lrpp_record="$_lrpp_state/paths-v1.conf.tmp.$$"
    printf 'schema=luoshu-runtime-paths-v1\n' > "$_lrpp_record" || return 1
    mv -f "$_lrpp_record" "$_lrpp_state/paths-v1.conf" || return 1
}

luoshu_runtime_paths_init() {
    _lrpi_module="${1:-${MODULE_DIR:-${MODDIR:-}}}"
    [ -n "$_lrpi_module" ] && [ -d "$_lrpi_module" ] || return 1
    _lrpi_module=$(CDPATH= cd -P -- "$_lrpi_module" 2>/dev/null && pwd) || return 1
    [ "$_lrpi_module" != / ] || return 1
    # Source checkouts are inputs to builds/tests, never installed modules. A
    # linked worktree uses a .git file; neither shape may be migrated in place.
    [ ! -e "$_lrpi_module/.git" ] && [ ! -L "$_lrpi_module/.git" ] || return 1
    # The state location is a contract, not a caller-controlled deletion target.
    case "${LUOSHU_STATE_DIR:-}" in
        ''|"$_lrpi_module/.luoshu-state") ;;
        *)
            # Installer/test callers can initialize two module generations in
            # one shell; only a previous value issued by this helper may reset.
            [ -n "${LUOSHU_RUNTIME_PATHS_MODULE:-}" ] && \
                [ "$LUOSHU_STATE_DIR" = "$LUOSHU_RUNTIME_PATHS_MODULE/.luoshu-state" ] || return 1
            ;;
    esac
    _luoshu_runtime_prepare "$_lrpi_module" || return $?
    LUOSHU_STATE_DIR="$_lrpi_module/.luoshu-state"
    LUOSHU_CONFIG_DIR="$LUOSHU_STATE_DIR/config"
    LUOSHU_LOG_DIR="$LUOSHU_STATE_DIR/logs"
    LUOSHU_CACHE_DIR="$LUOSHU_STATE_DIR/cache"
    LUOSHU_TASKS_DIR="$LUOSHU_STATE_DIR/tasks"
    LUOSHU_TMP_DIR="$LUOSHU_STATE_DIR/tmp"
    LUOSHU_BACKUP_DIR="$LUOSHU_STATE_DIR/backup"
    LUOSHU_REPORTS_DIR="$LUOSHU_STATE_DIR/reports"
    LUOSHU_RUNTIME_PATHS_MODULE="$_lrpi_module"
    CONFIG_DIR="$LUOSHU_CONFIG_DIR"
    LOG_DIR="$LUOSHU_LOG_DIR"
    TMPDIR="$LUOSHU_TMP_DIR"
    export LUOSHU_STATE_DIR LUOSHU_CONFIG_DIR LUOSHU_LOG_DIR LUOSHU_CACHE_DIR
    export LUOSHU_TASKS_DIR LUOSHU_TMP_DIR LUOSHU_BACKUP_DIR LUOSHU_REPORTS_DIR CONFIG_DIR LOG_DIR TMPDIR
    export LUOSHU_RUNTIME_PATHS_MODULE
}
