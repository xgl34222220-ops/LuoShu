#!/bin/sh
# Shared build-time version helpers. module.prop is the single source of truth.

version_prop_get() {
    _vp_key="$1"
    _vp_root="${ROOT:-${GITHUB_WORKSPACE:-$(pwd)}}"
    [ -f "$_vp_root/module.prop" ] || {
        echo "module.prop not found under $_vp_root" >&2
        return 1
    }
    sed -n "s/^${_vp_key}=//p" "$_vp_root/module.prop" | head -n1
}

LUOSHU_VERSION=$(version_prop_get version)
LUOSHU_VERSION_CODE=$(version_prop_get versionCode)
LUOSHU_ARTIFACT_VERSION=$(printf '%s' "$LUOSHU_VERSION" | sed 's#[ /]#-#g')
LUOSHU_APP_VERSION_CODE=$((LUOSHU_VERSION_CODE * 100 + 1))

export LUOSHU_VERSION LUOSHU_VERSION_CODE LUOSHU_ARTIFACT_VERSION LUOSHU_APP_VERSION_CODE
