#!/system/bin/sh
# The pinned compatibility core still contains the retired global-weight writes.
# Refuse that one operation in LuoShu's shell; keep all other settings calls intact.
# Re-sourcing replaces this same function, and command bypasses it without recursion.
settings() {
    if [ "${1:-}" = --user ]; then
        if [ "${3:-}" = put ] && [ "${4:-}" = secure ] && \
           [ "${5:-}" = font_weight_adjustment ]; then
            return 1
        fi
    elif [ "${1:-}" = put ] && [ "${2:-}" = secure ] && \
         [ "${3:-}" = font_weight_adjustment ]; then
        return 1
    fi
    command settings "$@"
}
