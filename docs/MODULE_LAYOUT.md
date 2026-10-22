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
├── late-load.sh        # KernelSU late-load 入口（仅 KSU_LATE_LOAD=1 时运行）
├── emulated-soft-reboot.sh  # KernelSU 软重启阶段入口（仅 KSU=true 时运行）
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
│   ├── service.sh
│   └── emulated-soft-reboot.sh
└── compat/
    └── v227/
        ├── customize.sh
        ├── post-fs-data.sh
        └── uninstall.sh
```

`core/` is the current internal boot/service implementation. `compat/` exists only for migration/cleanup contracts that still have installed-device compatibility value.

### KernelSU 软重启阶段（emulated-soft-reboot）

`ksud soft-reboot` 在 PID 1 挂载命名空间里先运行各模块的 `emulated-soft-reboot.sh`（最多等待 5 秒），随后 `stop`，再重新执行 post-fs-data / post-mount / service / boot-completed，**内核 boot_id 不变**。根目录 `emulated-soft-reboot.sh` 只是路由，实现在 `.luoshu-runtime/core/emulated-soft-reboot.sh`：

- 仅在 `KSU=true` 时运行；其他 Root 管理器从不调用此阶段，行为保持不变。
- 只处理洛书自己登记的挂载：`/data/adb/luoshu/self-mount/mounts.list` 与 `/data/adb/luoshu/private-payload/module-view.mounts`，逆序（最新优先）卸载；忙碌目标退回 `umount -l`。
- 只有当 mountinfo 中该路径**最上层**的挂载带有洛书标记（模块目录或 self-mount 状态目录）时才卸载，叠在洛书之上的其他模块挂载永不弹出；module-view 列表只接受模块目录内的目标；旧 boot_id 的日志不重放。
- 全部释放后清空同 boot 日志、删除 `self-mount/boot-id` 与 `config/self-mount-required.conf`，`config/self-mount.conf` 写为 `state=idle reason=ksu-soft-reboot`，随后的 post-mount 执行全新的自挂载事务。
- 任一目标无法释放时，未释放的条目保留在日志里、boot-id 不动，post-mount 沿用原有的同 boot 回滚路径。结果写入 `config/ksu-soft-reboot.conf`（`state=ready|failed`、`reason`、`released`、`remaining`），日志在 `logs/soft-reboot.log`。

## Runtime configuration

The release manifest does **not** copy the repository `config/` directory wholesale. Only runtime defaults are shipped:

- `config/active_font.conf`
- `config/version_notes.conf`

Release-policy JSON, branch cleanup state and one-shot maintenance data belong to repository tooling, not the installed module.

## Font scanner

`common/font_inventory_scan.py` is the only stock-font scanner entry point. Scanner revision is stored in data (`SCANNER_REVISION`), not encoded in filenames. Do not recreate `font_inventory_scan_vN.py` wrappers.

## HyperOS filename policy

`common/hyperos_physical_policy.py` is the only source of HyperOS physical font targets (core
prefixes, optional slot groups, Mono / MiSansL3 kept stock). The shell mappers
(`legacy_v14_4/hyperos_clock_compat.sh`, `legacy_v14_4/hyperos_full_coverage.sh`,
`hyperos_global.sh`) carry a block generated from it; edit the Python policy and run
`python3 common/hyperos_physical_policy.py --write`. `--check` runs in `scripts/check.sh` and
the HyperOS policy workflow, so a hand-edited shell copy fails CI. Optional groups are read from
`config/hyperos_slot_groups.conf` (`miui_ex`, `misans_ext` default on; `lockscreen_styles` default
off), which the App writes through `common/hyperos_coverage_bridge.sh`.

## Compatibility code

`common/legacy_v14_4/` remains because the current composite/safe-switch compatibility path still uses it. It is not a dumping ground:

- exact copies of canonical helpers are forbidden;
- shared helpers must be referenced from `common/`;
- a legacy file may remain only when behavior intentionally differs from the canonical implementation.

## Release payload

`scripts/module_payload_manifest.txt` is an allowlist. Repository-only files must not be added merely because they exist.

`scripts/module_layout_test.sh` enforces the layout and is run from the main source checks.
