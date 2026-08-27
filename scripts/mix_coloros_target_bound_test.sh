#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

MODDIR="$ROOT" MODULE_DIR="$ROOT" sh -c '
    . "$1/common/font_boot_state.sh"
    files="$(get_all_coloros_files)"
    set -- $files
    count=$#
    [ "$count" -ge 70 ]
    [ "$count" -le 130 ] || {
        echo "ColorOS mix target inventory is unbounded: $count" >&2
        exit 1
    }
    for required in \
        SysSans-En-Regular.ttf \
        GoogleSansText-Regular.ttf \
        GoogleSansText-ExtraBold.ttf \
        GoogleSansDisplay-Regular.ttf \
        GoogleSans18pt-Regular.ttf \
        ProductSans-Regular.ttf \
        Roboto-Black.ttf \
        NotoSans-Regular.ttf; do
        case " $files " in
            *" $required "*) ;;
            *) echo "missing required Latin/digit target: $required" >&2; exit 1 ;;
        esac
    done
' font_mix.sh "$ROOT"

echo "ColorOS mix target bound regression: PASS"
