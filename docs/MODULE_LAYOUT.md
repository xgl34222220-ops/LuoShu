# LuoShu module layout

The repository contains Android App sources, CI/tests and release automation, but the flashed module is intentionally smaller.

## Shipped module root

Only Root-manager entry points and user-facing metadata live at the ZIP root:

```text
LuoShu/
├── module.prop
├── customize.sh
├── post-fs-data.sh
├── post-mount.sh
├── service.sh
├── boot-completed.sh
├── action.sh
├── uninstall.sh
├── common/
├── .luoshu-runtime/
├── system/
├── config/
├── bundled/
├── fonts/
└── licenses/
```

Version-suffixed implementation files must not return to the root. The root scripts are stable routers only.

## Internal runtime

```text
.luoshu-runtime/
├── core/
│   ├── post-fs-data.sh
│   ├── post-mount.sh
│   └── service.sh
└── compat/
    └── v227/
        ├── customize.sh
        ├── post-fs-data.sh
        └── uninstall.sh
```

`core/` is the current internal boot/service implementation. `compat/` exists only for migration/cleanup contracts that still have installed-device compatibility value.

## Runtime configuration

The release manifest does **not** copy the repository `config/` directory wholesale. Only runtime defaults are shipped:

- `config/active_font.conf`
- `config/version_notes.conf`

Release-policy JSON, branch cleanup state and one-shot maintenance data belong to repository tooling, not the installed module.

## Font scanner

`common/font_inventory_scan.py` is the only stock-font scanner entry point. Scanner revision is stored in data (`SCANNER_REVISION`), not encoded in filenames. Do not recreate `font_inventory_scan_vN.py` wrappers.

## Compatibility code

`common/legacy_v14_4/` remains because the current composite/safe-switch compatibility path still uses it. It is not a dumping ground:

- exact copies of canonical helpers are forbidden;
- shared helpers must be referenced from `common/`;
- a legacy file may remain only when behavior intentionally differs from the canonical implementation.

## Release payload

`scripts/module_payload_manifest.txt` is an allowlist. Repository-only files must not be added merely because they exist.

`scripts/module_layout_test.sh` enforces the layout and is run from the main source checks.
