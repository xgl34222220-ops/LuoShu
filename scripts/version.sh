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

LUOSHU_RELEASE_TAG=$(python3 "${ROOT:-${GITHUB_WORKSPACE:-$(pwd)}}/scripts/release_version_policy.py" --module "${ROOT:-${GITHUB_WORKSPACE:-$(pwd)}}/module.prop" --field tag --check) || return 1
LUOSHU_RELEASE_NOTES="RELEASE_NOTES_${LUOSHU_RELEASE_TAG}.md"
LUOSHU_RELEASE_TITLE=$(python3 "${ROOT:-${GITHUB_WORKSPACE:-$(pwd)}}/scripts/release_version_policy.py" --module "${ROOT:-${GITHUB_WORKSPACE:-$(pwd)}}/module.prop" --field title) || return 1

export LUOSHU_VERSION LUOSHU_VERSION_CODE LUOSHU_ARTIFACT_VERSION LUOSHU_APP_VERSION_CODE
export LUOSHU_RELEASE_TAG LUOSHU_RELEASE_NOTES LUOSHU_RELEASE_TITLE
