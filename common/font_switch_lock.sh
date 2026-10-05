#!/system/bin/sh
# LuoShu font-switch lock helpers.
# This file is intentionally independent from the font generation/mapping engine so
# the v14.4 compatibility backend can retain current concurrency safety without
# importing the v4 payload/template pipeline.
set +e

luoshu_process_starttime() {
    _lps_pid="$1"
    case "$_lps_pid" in ''|*[!0-9]*) return 1 ;; esac
    _lps_stat_path="/proc/$_lps_pid/stat"
    if [ "$_lps_pid" = "$$" ] && [ ! -r "$_lps_stat_path" ]; then
        if [ -n "${PPID:-}" ] && [ -r "/proc/$PPID/stat" ]; then
            _lps_stat_path="/proc/$PPID/stat"
        else
            _lps_stat_path=/proc/self/stat
        fi
    fi
    [ -r "$_lps_stat_path" ] || return 1
    IFS= read -r _lps_stat < "$_lps_stat_path" 2>/dev/null || return 1
    _lps_tail="${_lps_stat##*) }"
    [ "$_lps_tail" != "$_lps_stat" ] || return 1
    set -- $_lps_tail
    [ "$#" -ge 20 ] || return 1
    shift 19
    case "$1" in ''|*[!0-9]*) return 1 ;; esac
    printf '%s\n' "$1"
}

luoshu_current_boot_id() {
    _lcbi_value="$(cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n')"
    [ -n "$_lcbi_value" ] || return 1
    printf '%s\n' "$_lcbi_value"
}

luoshu_font_lock_pid() {
    _lflp_path="${1:-$MODULE_DIR/.font_switch.lock}"
    if [ -d "$_lflp_path" ]; then
        sed -n '1p' "$_lflp_path/pid" 2>/dev/null
    elif [ -f "$_lflp_path" ]; then
        sed -n '1p' "$_lflp_path" 2>/dev/null
    fi
}

luoshu_font_lock_starttime() {
    _lfls_path="${1:-$MODULE_DIR/.font_switch.lock}"
    if [ -d "$_lfls_path" ]; then
        sed -n 's/^starttime=//p' "$_lfls_path/pid" 2>/dev/null | sed -n '1p'
    elif [ -f "$_lfls_path" ]; then
        sed -n 's/^starttime=//p' "$_lfls_path" 2>/dev/null | sed -n '1p'
    fi
}

luoshu_font_lock_boot_id() {
    _lflb_path="${1:-$MODULE_DIR/.font_switch.lock}"
    if [ -d "$_lflb_path" ]; then
        sed -n 's/^boot_id=//p' "$_lflb_path/pid" 2>/dev/null | sed -n '1p'
    elif [ -f "$_lflb_path" ]; then
        sed -n 's/^boot_id=//p' "$_lflb_path" 2>/dev/null | sed -n '1p'
    fi
}

luoshu_font_lock_token() {
    _lflt_path="${1:-$MODULE_DIR/.font_switch.lock}"
    if [ -d "$_lflt_path" ]; then
        sed -n 's/^token=//p' "$_lflt_path/pid" 2>/dev/null | sed -n '1p'
    elif [ -f "$_lflt_path" ]; then
        sed -n 's/^token=//p' "$_lflt_path" 2>/dev/null | sed -n '1p'
    fi
}

luoshu_font_lock_created() {
    _lflc_path="${1:-$MODULE_DIR/.font_switch.lock}"
    if [ -d "$_lflc_path" ]; then
        sed -n 's/^created=//p' "$_lflc_path/pid" 2>/dev/null | sed -n '1p'
    elif [ -f "$_lflc_path" ]; then
        sed -n 's/^created=//p' "$_lflc_path" 2>/dev/null | sed -n '1p'
    fi
}

# A canonical owner PID can be hidden by a Root/PID namespace. Capture the
# independently verified supervisor identity while the command is still alive,
# then accept only its final descendant-cleanup proof when that owner disappears.
# Python is needed only for acquisition inside a scope or a dead scoped owner;
# the normal live-owner check and unassociated legacy locks stay shell-only.
luoshu_font_lock_scope_recorded() {
    _lflsr_path="$1"
    [ ! -d "$_lflsr_path" ] || _lflsr_path="$_lflsr_path/pid"
    grep -q '^scope_' "$_lflsr_path" 2>/dev/null
}

luoshu_font_lock_scope_identity() (
    _lflsi_action="$1"
    _lflsi_module="${LUOSHU_REAL_MODDIR:-${MODULE_DIR:-${MODDIR:-}}}"
    [ -n "$_lflsi_module" ] || return 1
    _lflsi_python="${LUOSHU_TASK_SCOPE_PYTHON:-$_lflsi_module/common/python/bin/luoshu-python}"
    command -v "$_lflsi_python" >/dev/null 2>&1 || return 1
    if [ -z "${LUOSHU_TASK_SCOPE_PYTHON:-}" ]; then
        PYTHONHOME="$_lflsi_module/common/python"
        PYTHONPATH="$PYTHONHOME/lib/python3.14:$PYTHONHOME/lib/python3.14/site-packages"
        LD_LIBRARY_PATH="$PYTHONHOME/lib:$PYTHONHOME/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
        export PYTHONHOME PYTHONPATH LD_LIBRARY_PATH
    fi
    "$_lflsi_python" - "$_lflsi_action" "$_lflsi_module" "${2:-}" "${3:-}" <<'PY' 2>/dev/null
import fcntl
import json
import os
from pathlib import Path
import re
import sys

try:
    action, module_text, lock_text, expected_text = sys.argv[1:]
    module = Path(module_text).resolve(strict=True)
    state = module / '.luoshu-state'
    assert not state.is_symlink()
    allowed = (state / 'tasks', state / 'config')
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    namespace = os.readlink('/proc/self/ns/pid')

    def owned_path(value):
        path = Path(value)
        assert path.is_absolute() and not any(c in value for c in '\n\r|')
        assert not path.is_symlink()
        path = path.resolve()
        assert path.name.endswith('.pid') and path.parent in allowed
        assert not path.parent.is_symlink()
        assert all(str(root.resolve()) == str(root) for root in allowed if root.exists())
        return path

    def load(path):
        assert not path.is_symlink() and path.stat().st_size <= 65536
        value = json.loads(path.read_text())
        assert isinstance(value, dict)
        return value

    def fields(record):
        assert type(record['pid']) is int and record['pid'] > 1
        assert isinstance(record['start'], str) and record['start'].isdigit()
        assert re.fullmatch(r'[A-Za-z0-9_.-]{1,160}', record['task'])
        assert record['boot'] == boot
        return (record['task'], str(record['pid']), record['start'], record['boot'])

    if action == 'capture':
        path = owned_path(os.environ['LUOSHU_TASK_SCOPE_PIDFILE'])
        owner = load(Path(str(path) + '.owner.json'))
        task, pid, start, saved_boot = fields(owner)
        assert os.environ['LUOSHU_TASK_SCOPE_TASK'] == task
        assert os.environ['LUOSHU_TASK_SCOPE_PID'] == pid
        assert owned_path(owner['pidfile']) == path
        assert owner['namespace'] == namespace
        for suffix, expected in (('', pid), ('.task', task), ('.start', start), ('.boot', saved_boot)):
            sidecar = Path(str(path) + suffix)
            assert not sidecar.is_symlink() and sidecar.read_text().strip() == expected
        proc_pid = owner['procPid']
        assert type(proc_pid) is int and proc_pid > 1
        proc_root = Path('/proc') / str(proc_pid)
        stat = (proc_root / 'stat').read_text().rsplit(') ', 1)[1].split()
        assert stat[0] != 'Z' and stat[19] == start
        assert os.readlink(proc_root / 'ns/pid') == namespace
        local_pid = str(proc_pid)
        for line in (proc_root / 'status').read_text().splitlines():
            if line.startswith('NSpid:'):
                local_pid = line.split()[-1]
        assert local_pid == pid
        # The shell invoking this reader must actually descend from the saved
        # supervisor, rather than borrowing another live task's environment.
        ancestor = int(os.readlink('/proc/self'))
        visited = set()
        while ancestor != proc_pid:
            assert ancestor > 1 and ancestor not in visited and len(visited) < 1024
            visited.add(ancestor)
            tail = (Path('/proc') / str(ancestor) / 'stat').read_text().rsplit(') ', 1)[1].split()
            ancestor = int(tail[1])
        for key, value in (('pidfile', str(path)), ('task', task), ('pid', pid),
                           ('start', start), ('boot', saved_boot), ('namespace', namespace)):
            print('scope_' + key + '=' + value)
    elif action == 'cleaned':
        lock = Path(lock_text)
        record_path = lock / 'pid' if lock.is_dir() else lock
        lines = record_path.read_text().splitlines()[1:]
        values = {}
        for line in lines:
            if '=' in line:
                key, value = line.split('=', 1)
                assert key not in values
                values[key] = value
        path = owned_path(values['scope_pidfile'])
        expected = (values['scope_task'], values['scope_pid'], values['scope_start'], values['scope_boot'])
        proof = load(Path(str(path) + '.cleanup.json'))
        assert proof.get('schema') == 'task-cleanup-v2' and fields(proof) == expected
        assert values['scope_namespace'] == namespace and proof.get('namespace') == namespace
        assert proof.get('cleaned') is True
        assert all(proof.get(key) == [] for key in ('leftoverPids', 'cleanupErrors', 'handoffTasks', 'handoffOwners'))
        # A replacement registration or a supervisor that has not yet cleared
        # its ownership must never be retired using a preceding proof.
        assert not any(Path(str(path) + suffix).exists() or Path(str(path) + suffix).is_symlink()
                       for suffix in ('', '.owner.json', '.task', '.start', '.boot', '.ready'))
    elif action == 'reap':
        lock = Path(lock_text)
        assert not lock.is_symlink()
        lock = lock.parent.resolve(strict=True) / lock.name
        assert lock == module / '.font_switch.lock'
        tasks = allowed[0]
        assert tasks.is_dir() and not tasks.is_symlink() and tasks.resolve() == tasks
        # One stable kernel-lock inode serializes stale removers. It stays in
        # the centralized tasks tree; process exit/SIGKILL releases the lock.
        guard = tasks / 'font-switch-reap.lock'
        descriptor = os.open(guard, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            record_path = lock / 'pid'
            assert not record_path.is_symlink()
            assert record_path.read_text().rstrip('\n') == expected_text
            record_path.unlink()
            (lock / '.init-observed').unlink(missing_ok=True)
            lock.rmdir()
        finally:
            os.close(descriptor)
    else:
        raise ValueError('unknown scope action')
except (AssertionError, OSError, ValueError, KeyError, TypeError, IndexError):
    sys.exit(1)
PY
)

luoshu_font_lock_recent_token() {
    _lfrt_path="$1"
    if luoshu_font_lock_scope_recorded "$_lfrt_path"; then
        # A failed/unknown cleanup is not made safe by the passage of 480 s.
        # The original namespace lease remains unchanged for legacy records.
        luoshu_font_lock_scope_identity cleaned "$_lfrt_path" && return 1
        return 0
    fi
    _lfrt_token="$(luoshu_font_lock_token "$_lfrt_path")"
    [ -n "$_lfrt_token" ] || return 1
    _lfrt_created="$(luoshu_font_lock_created "$_lfrt_path")"
    _lfrt_now="$(date +%s 2>/dev/null)"
    case "$_lfrt_created:$_lfrt_now" in *[!0-9:]*) return 1 ;; esac
    _lfrt_age=$((_lfrt_now - _lfrt_created))
    _lfrt_lease="${LUOSHU_FONT_LOCK_LEASE_SECONDS:-480}"
    case "$_lfrt_lease" in ''|*[!0-9]*) _lfrt_lease=480 ;; esac
    [ "$_lfrt_age" -ge 0 ] && [ "$_lfrt_age" -le "$_lfrt_lease" ]
}

luoshu_font_lock_owned_record() {
    _lfor_path="$1"
    _lfor_pid="$2"
    printf '%s\n' "${LUOSHU_FONT_LOCK_OWNERS:-}" | awk -F '|' -v p="$_lfor_path" -v i="$_lfor_pid" '
        $1 == p && $2 == i { print; exit }
    '
}

luoshu_font_lock_forget_owned() {
    _lffo_path="$1"
    _lffo_pid="$2"
    LUOSHU_FONT_LOCK_OWNERS="$(printf '%s\n' "${LUOSHU_FONT_LOCK_OWNERS:-}" | awk -F '|' -v p="$_lffo_path" -v i="$_lffo_pid" '
        !($1 == p && $2 == i) && NF { print }
    ')"
}

luoshu_font_lock_active() {
    _lfla_path="${1:-$MODULE_DIR/.font_switch.lock}"
    _lfla_pid="$(luoshu_font_lock_pid "$_lfla_path")"
    case "$_lfla_pid" in ''|*[!0-9]*) return 1 ;; esac
    _lfla_saved_boot="$(luoshu_font_lock_boot_id "$_lfla_path")"
    if [ -n "$_lfla_saved_boot" ]; then
        _lfla_live_boot="$(luoshu_current_boot_id)" || \
            { luoshu_font_lock_recent_token "$_lfla_path" && return 0; return 1; }
        [ "$_lfla_saved_boot" = "$_lfla_live_boot" ] || return 1
    fi
    _lfla_saved_start="$(luoshu_font_lock_starttime "$_lfla_path")"
    if [ -n "$_lfla_saved_start" ]; then
        case "$_lfla_saved_start" in *[!0-9]*) return 1 ;; esac
        if _lfla_live_start="$(luoshu_process_starttime "$_lfla_pid")"; then
            if [ "$_lfla_saved_start" != "$_lfla_live_start" ]; then
                luoshu_font_lock_recent_token "$_lfla_path" && return 0
                return 1
            fi
            return 0
        fi
        luoshu_font_lock_recent_token "$_lfla_path" && return 0
        return 1
    fi
    kill -0 "$_lfla_pid" 2>/dev/null && return 0
    luoshu_font_lock_recent_token "$_lfla_path"
}

luoshu_font_lock_reap_stale() {
    _lfls_path="${1:-$MODULE_DIR/.font_switch.lock}"
    [ -e "$_lfls_path" ] || return 0
    _lfls_record_path="$_lfls_path"
    [ ! -d "$_lfls_path" ] || _lfls_record_path="$_lfls_path/pid"
    _lfls_original_record="$(cat "$_lfls_record_path" 2>/dev/null)"
    luoshu_font_lock_active "$_lfls_path" && return 1
    if [ -d "$_lfls_path" ] && [ ! -s "$_lfls_path/pid" ]; then
        _lfls_observed="$_lfls_path/.init-observed"
        if [ ! -e "$_lfls_observed" ]; then
            : > "$_lfls_observed" 2>/dev/null || true
            return 1
        fi
        _lfls_grace="${LUOSHU_FONT_LOCK_INIT_GRACE_SECONDS:-1}"
        case "$_lfls_grace" in ''|*[!0-9.]*|*.*.*) _lfls_grace=1 ;; esac
        sleep "$_lfls_grace" 2>/dev/null || sleep 1
        [ -e "$_lfls_path" ] || return 0
        luoshu_font_lock_active "$_lfls_path" && return 1
    fi
    # Another contender may have retired the old directory and acquired a new
    # token while identity/proof inspection ran. Do not remove its new record.
    [ "$(cat "$_lfls_record_path" 2>/dev/null)" = "$_lfls_original_record" ] || return 1
    case "$_lfls_original_record" in
        *scope_pidfile=*)
            # A second stale observer must recheck under the same kernel lock,
            # rather than deleting a new acquisition at this pathname.
            luoshu_font_lock_scope_identity reap "$_lfls_path" "$_lfls_original_record"
            return $?
            ;;
    esac
    if [ -d "$_lfls_path" ]; then
        rm -f "$_lfls_path/pid" "$_lfls_path/.init-observed" 2>/dev/null || true
        rmdir "$_lfls_path" 2>/dev/null
    else
        rm -f "$_lfls_path" 2>/dev/null
    fi
}

luoshu_font_lock_acquire() {
    _lfla_path="${1:-$MODULE_DIR/.font_switch.lock}"
    _lfla_owner="${2:-$$}"
    case "$_lfla_owner" in ''|*[!0-9]*) return 1 ;; esac
    _lfla_start="$(luoshu_process_starttime "$_lfla_owner" 2>/dev/null)"
    _lfla_boot="$(luoshu_current_boot_id 2>/dev/null)"
    _lfla_created="$(date +%s 2>/dev/null)"
    case "$_lfla_created" in ''|*[!0-9]*) _lfla_created=0 ;; esac
    _lfla_scope=''
    if [ -n "${LUOSHU_TASK_SCOPE_PIDFILE:-}${LUOSHU_TASK_SCOPE_TASK:-}${LUOSHU_TASK_SCOPE_PID:-}" ]; then
        [ -n "${LUOSHU_TASK_SCOPE_PIDFILE:-}" ] && [ -n "${LUOSHU_TASK_SCOPE_TASK:-}" ] && \
            [ -n "${LUOSHU_TASK_SCOPE_PID:-}" ] || return 1
        # A scoped task cannot silently downgrade an unverified association to
        # the legacy namespace lease. Only genuinely unscoped callers use it.
        _lfla_scope="$(luoshu_font_lock_scope_identity capture 2>/dev/null)" || return 1
    fi
    _lfla_attempt=0
    while [ "$_lfla_attempt" -lt 6 ]; do
        _lfla_tmp="$(mktemp "${_lfla_path}.owner.XXXXXX" 2>/dev/null)" || return 1
        _lfla_token="${_lfla_tmp##*.owner.}"
        {
            printf '%s\n' "$_lfla_owner"
            [ -n "$_lfla_start" ] && printf 'starttime=%s\n' "$_lfla_start"
            [ -n "$_lfla_boot" ] && printf 'boot_id=%s\n' "$_lfla_boot"
            printf 'token=%s\n' "$_lfla_token"
            printf 'created=%s\n' "$_lfla_created"
            [ -z "$_lfla_scope" ] || printf '%s\n' "$_lfla_scope"
        } > "$_lfla_tmp" 2>/dev/null || { rm -f "$_lfla_tmp" 2>/dev/null || true; return 1; }
        chmod 0600 "$_lfla_tmp" 2>/dev/null || true
        if mkdir "$_lfla_path" 2>/dev/null; then
            if mv -f "$_lfla_tmp" "$_lfla_path/pid" 2>/dev/null; then
                LUOSHU_FONT_LOCK_OWNERS="${LUOSHU_FONT_LOCK_OWNERS:+$LUOSHU_FONT_LOCK_OWNERS
}${_lfla_path}|${_lfla_owner}|${_lfla_start}|${_lfla_boot}|${_lfla_token}|${_lfla_created}"
                return 0
            fi
            rm -f "$_lfla_tmp" "$_lfla_path/pid" 2>/dev/null || true
            rmdir "$_lfla_path" 2>/dev/null || true
            return 1
        fi
        rm -f "$_lfla_tmp" 2>/dev/null || true
        [ -e "$_lfla_path" ] || { _lfla_attempt=$((_lfla_attempt + 1)); continue; }
        luoshu_font_lock_active "$_lfla_path" && return 2
        luoshu_font_lock_reap_stale "$_lfla_path" >/dev/null 2>&1 || true
        _lfla_attempt=$((_lfla_attempt + 1))
        sleep 0.02 2>/dev/null || true
    done
    return 2
}

luoshu_font_lock_release() {
    _lflr_path="${1:-$MODULE_DIR/.font_switch.lock}"
    _lflr_owner="${2:-$$}"
    [ -e "$_lflr_path" ] || return 0
    _lflr_pid="$(luoshu_font_lock_pid "$_lflr_path")"
    [ "$_lflr_pid" = "$_lflr_owner" ] || return 1
    _lflr_saved_start="$(luoshu_font_lock_starttime "$_lflr_path")"
    _lflr_saved_boot="$(luoshu_font_lock_boot_id "$_lflr_path")"
    _lflr_saved_token="$(luoshu_font_lock_token "$_lflr_path")"
    _lflr_owned="$(luoshu_font_lock_owned_record "$_lflr_path" "$_lflr_owner")"
    if [ -n "$_lflr_saved_token" ] && [ -n "$_lflr_owned" ]; then
        _lflr_owned_start="$(printf '%s\n' "$_lflr_owned" | awk -F '|' '{print $3; exit}')"
        _lflr_owned_boot="$(printf '%s\n' "$_lflr_owned" | awk -F '|' '{print $4; exit}')"
        _lflr_owned_token="$(printf '%s\n' "$_lflr_owned" | awk -F '|' '{print $5; exit}')"
        [ "$_lflr_saved_token" = "$_lflr_owned_token" ] || return 1
        [ "$_lflr_saved_start" = "$_lflr_owned_start" ] || return 1
        [ "$_lflr_saved_boot" = "$_lflr_owned_boot" ] || return 1
    else
        if [ -n "$_lflr_saved_start" ]; then
            _lflr_live_start="$(luoshu_process_starttime "$_lflr_owner")" || return 1
            [ "$_lflr_saved_start" = "$_lflr_live_start" ] || return 1
        fi
        if [ -n "$_lflr_saved_boot" ]; then
            _lflr_live_boot="$(luoshu_current_boot_id)" || return 1
            [ "$_lflr_saved_boot" = "$_lflr_live_boot" ] || return 1
        fi
    fi
    if [ -d "$_lflr_path" ]; then
        rm -f "$_lflr_path/pid" "$_lflr_path/.init-observed" 2>/dev/null || return 1
        rmdir "$_lflr_path" 2>/dev/null || return 1
    else
        rm -f "$_lflr_path" 2>/dev/null || return 1
    fi
    luoshu_font_lock_forget_owned "$_lflr_path" "$_lflr_owner"
    return 0
}

luoshu_font_lock_force_clear() {
    _lflfc_path="${1:-$MODULE_DIR/.font_switch.lock}"
    rm -f "$_lflfc_path/pid" "$_lflfc_path/.init-observed" 2>/dev/null || true
    rmdir "$_lflfc_path" 2>/dev/null || true
    rm -f "$_lflfc_path" 2>/dev/null || true
    for _lflfc_tmp in "$_lflfc_path".owner.*; do
        [ -e "$_lflfc_tmp" ] || continue
        rm -f "$_lflfc_tmp" 2>/dev/null || true
    done
    _lflfc_pid="${2:-$$}"
    luoshu_font_lock_forget_owned "$_lflfc_path" "$_lflfc_pid" >/dev/null 2>&1 || true
    [ ! -e "$_lflfc_path" ]
}
