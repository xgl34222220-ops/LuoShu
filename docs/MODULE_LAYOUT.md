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

### KernelSU 软重启（emulated-soft-reboot 阶段）

KernelSU 的 `ksud soft-reboot` 不重启内核：它切到 PID 1 的挂载命名空间，把 `sys.boot_completed` 置 0，在限定时间内运行各模块的 `emulated-soft-reboot.sh`，然后 `stop` 框架，再依次重放 post-fs-data（含 post-mount）、`start`、service 与 boot-completed。由于 `/proc/sys/kernel/random/boot_id` 保持不变，洛书按 boot_id 记录的自挂载日志会被误认为“本次启动已挂载”，因此需要在这一阶段主动收尾。

- 根目录 `emulated-soft-reboot.sh` 只做路由：`KSU` 不是 `true` 时直接退出（Magisk、APatch 等不会调用此阶段，行为不变），否则执行 `.luoshu-runtime/core/emulated-soft-reboot.sh`。
- 只处理本次启动的日志：`self-mount/boot-id` 与当前 boot_id 不一致时不做任何卸载，旧日志绝不重放。
- 卸载范围仅限洛书自己登记的挂载：先 `self-mount/mounts.list`，再 `private-payload/module-view.mounts`（只接受模块目录内的目标），各自按登记的逆序（最新优先）卸载；普通卸载失败时退回 `umount -l`；已不存在的挂载点视为已释放。
- 卸载前检查 mountinfo 中该路径最上层的挂载：位于洛书状态目录内，或其 root / 来源 / 选项指向洛书状态目录或本模块目录，才视为洛书所有；叠在上面的其他模块挂载一律不动。
- 全部释放后重置本次启动决策：清空 `mounts.list` 与 `lower/`、`work/`，删除 `self-mount/boot-id` 和 `config/self-mount-required.conf`，`config/self-mount.conf` 写为 `state=idle`、`reason=ksu-soft-reboot`，重放的 post-mount 因此执行一次全新的自挂载事务。
- 有任何目标未释放时保守处理：日志里只保留未释放的条目，boot-id 与挂载状态不动，交由 post-mount 现有的同 boot 回滚路径。
- 结果写入 `config/ksu-soft-reboot.conf`（`state=ready|failed`、`reason`、`released`、`remaining`、`bootId`），过程日志在 `logs/soft-reboot.log`。回归测试为 `scripts/ksu_soft_reboot_test.sh`（已接入 `scripts/check.sh`）。

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
