# Stable runtime rebuild candidate

## Baseline and mounting boundary

This branch starts at the immutable `refactor-v1.1.1` tag, commit
`be39f598bfb921526851c5c4a2e92905dacf4ea7`, rather than the later universal engine.
The official `LuoShu-v1.1.1.zip` hashes to
`c5c8fa86af4ac196107ba05c5ee8cc1944140ae033cc9e763cec8c76f40c848a`.
All 163 release files with a source-tree counterpart matched byte-for-byte.
The bundled APK and assembled CPython/FontTools runtime are build outputs.

`scripts/stable_mount_sha256.json` pins 17 mounting/commit files, including root
hooks, private payload views, mount backends, and the safe next-boot font switch.
`scripts/stable_mount_boundary_test.py` rejects changes to these files. The
service's task scheduling and retired global-weight settings are deliberately
outside that byte fence. This does not prove any particular phone works: Android
mount namespaces, reboot persistence, and OEM mappings still require execution.
No system fonts.xml replacement, Hook, universal mount transaction, or new mount
namespace is introduced by task supervision.

## Actual call/process map

- Root-manager hooks enter `.luoshu-runtime/core`, with v227 install/boot/uninstall
  compatibility where the stable release calls it.
- App `app_bridge.sh switch_start` starts `font_switch_task.sh`; its manager routes
  to `legacy_v14_4/font_switch_safe.sh` and prepares a next-boot payload.
- App mixing routes through `legacy_v14_4/mix_router.sh`, its v142/v143 controllers,
  the font builder, and the completion/commit monitor. These are active dependencies,
  not obsolete copies that can be deleted because their names contain versions.
- Detached tasks use one finite subreaper scope. PID identity includes boot ID,
  start time and a random scope token. Child adoption covers double-fork/setsid
  descendants without a mount namespace change. The scope owns its workspace.
- The boot provider previously defaulted to an infinite observer plus repeated
  discovery. It now defaults to one apply and zero observer cycles, with no consumer
  restart. Existing mounts do not need a resident process to stay mounted. Fonts
  downloaded by providers later in the boot are not automatically continuously
  repaired; explicit operations or the next boot repair them.
- App detail/validation/import no longer schedules speculative font prewarming.
  Visible task progress and foreground library reconciliation remain bounded by
  the active task or visible App screen.

## Directory policy

| Path | Role and retention |
| --- | --- |
| `common`, `.luoshu-runtime/core`, `.luoshu-runtime/compat/v227` | Shipped code required by the verified stable route |
| `common/legacy_v14_4` | Active physical font switch/composition dependencies |
| `cache/tasks/<random-token>` | One task's temporary workspace; exact ownership marker required for cleanup |
| `config/*.pid` and task identity sidecars | Volatile; never migrate into the next installation |
| `config/device_font_inventory.json` and persistent scan/config records | Preserve across upgrades |
| `config/recovery` | Preserve reversible retirement/recovery records |
| `config/metrics_cache`, `font-config-source`, `safe-switch-validation` | Preserve reusable source/validation results |
| Schema-compatible font/device caches | Preserve under existing stable compatibility and size policy |
| `.luoshu-payload`, `.luoshu-payload-next`, retired/transaction stages | Mount/rollback-owned; not generic task garbage |
| Partition views, including OEM partitions | Preserve: these are inputs to the stable mount view |
| `/sdcard/LuoShu/fonts`, imports and user reports | User data; never a generic cleanup target |

The source tree had no exact duplicate non-Python-runtime helper files at baseline.
Deleting all version-named folders would remove the code the App actually runs.
Cleanup therefore targets proven task ownership and volatile state, while the
allowlisted release payload continues to exclude development directories.

## Global thickness removal

App UI and backend actions no longer offer or apply global thickness. Font-file
weights, variable axes and per-role composition weights remain available. Boot
never replays a saved global adjustment. A one-time retirement restores the
recorded original only if the current system value still equals LuoShu's saved
adjustment; a later user/system change is preserved. Both old files are copied and
verified in recovery before active configuration files are removed. Missing or
invalid original data is not replaced by a guessed zero. No system font service
restart or broad configuration broadcast is used.

## Library loading

The App can read the saved module index through `fonts cached` before Root status
or a full scan. It treats that as an unverified saved list, then reconciles.
Fresh indexes include the fingerprint used to build them, so a concurrent change
cannot be silently blessed with a newer fingerprint. Metadata fingerprinting
uses one `stat` invocation for the library instead of three subprocesses per file;
mode, inode and ctime detect permission changes and same-size replacements.
An inaccessible directory is an error, not an empty successful index.

## Validation status

Host process-tree, rollback, source-contract and JVM tests are separate from
Android execution. Timing measured on a Linux host is not a phone cold-start
claim. Root Android emulator eligibility, actual ARM64 runtime execution,
mount/rollback and reboot checks must be reported individually. Unsupported ELF
execution is a blocker, never a pass or permission to substitute a different
runtime without labeling it.

### Host-only metadata timing

One local Linux run with synthetic metadata fixtures (not a phone/UI benchmark):
100 files: stable 0.4543 s, refactor 0.0152 s; 1,000 files: stable 3.7300 s,
refactor 0.2227 s. Empty-library overhead stayed approximately 0.012 s.
Android cold/warm first-list timing remains a separate gate.

## Candidate App identity

The debug candidate uses `io.github.xgl34222220.luoshu.stabletest`, labeled
“洛书·稳定重构测试”. It is separate from official, `.debug`, and `.audit` installs.
The module marks this App `installPolicy=manual-only`; neither boot, installation,
nor the module action automatically installs/replaces it. Existing App data is
not migrated or deleted. Install the matching test APK separately when explicitly
testing the candidate. Local/CI debug signatures may differ; no update compatibility
is promised between builds signed by different environments.
