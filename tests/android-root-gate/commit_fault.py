"""A single test-process PATH fault, never a module/core or system-file edit."""
import shlex


def mv_wrapper(module, marker, real_mv='/system/bin/mv'):
    """Fail only the first exact stage→next rename and persist the hit evidence."""
    return '''#!/system/bin/sh
last=''; source=''
for arg in "$@"; do
    case "$arg" in -*) ;; *) source="$last"; last="$arg" ;; esac
done
if [ "$last" = TARGET ] && [ ! -e MARKER ]; then
    case "$source" in
        STAGE*)
            printf '%s\\n' "$source -> $last" > MARKER || exit 98
            exit 73
            ;;
    esac
fi
exec REAL "$@"
'''.replace('TARGET', shlex.quote(module + '/.luoshu-payload-next')).replace('STAGE', shlex.quote(module + '/.luoshu-payload-stage.')).replace('MARKER', shlex.quote(marker)).replace('REAL', shlex.quote(real_mv))
