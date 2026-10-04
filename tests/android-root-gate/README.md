# Root Android delivery gate

`luoshu-root-android-probe.yml` now contains runtime qualification and separate
baseline/candidate module, cleanup, composite and App checks on one disposable
AOSP API35 x86_64/nativebridge AVD. Each component needs its own evidence; runtime
qualification alone cannot prove font activation or a complete delivery result.
The workflow pins the exact candidate build and module digest. A green scoped
AVD result is not physical ARM64/OEM qualification or permission to release.

The probe uses the SHA256-pinned official `refactor-v1.1.1` ZIP. It never replaces
the runtime with host Python or an x86 build. Executable-format errors, missing
root, permission errors, native bridge failures, and timeouts fail the job.
There is no `continue-on-error`, skip-to-green, SELinux disabling, host security-setting
modification, user font inventory, user logs, physical-device access, or release.
The separately authorized Magisk stage patches only a disposable guest ramdisk copy.
The generated minimal font consists of synthetic triangle outlines and is test
code under this repository's license. Only synthetic qualification logs upload.

## Run

Owner pushes these files to the authorized test branch; the path-filtered push
trigger starts the probe. Manual dispatch is also available once GitHub recognizes
the workflow. For an already running disposable AVD:

```
python3 tests/android-root-gate/probe.py --module-zip LuoShu-v1.1.1.zip --output root-gate-output
```

If `/dev/kvm` permissions are unavailable the job stops rather than silently
changing host security settings. If standalone ARM64 execution fails, report the
actual evidence. JNI ARM translation support is not evidence for standalone ELF.
Any proposed x86 Android test runtime needs a separate scope decision and results
must remain labeled x86; it cannot validate the original ARM64 delivery package.

## Required delivery evidence (recorded separately for each execution)

For BOTH exact official baseline and exact candidate package hashes on a qualified
Root Android target, run the following without editing frozen mount code:

1. Install through the supported module-manager path. Record Android/root-manager,
   SELinux mode, build fingerprint, kernel and ABI. `adb root` alone does not prove
   Magisk/KernelSU/APatch installation or module boot lifecycle.
2. Import only synthetic licensed fonts; switch A to B; assert active hashes,
   actual system-visible font mount targets and namespace visibility.
3. Force preparation and commit failures separately; assert prior active payload
   and mount state survives, rollback restores the original payload, and no temp
   payload remains active. Unsupported cases are BLOCKED, never PASS.
4. Success, failure, timeout and cancellation must each leave zero owned child
   processes (including setsid/double-fork and late forks). Record PID + starttime
   + boot ID and verify independent sentinel processes survive. Repeat checks
   after the cleanup deadline; matching a process name is insufficient evidence.
5. Reboot at least once after a successful switch. Record changed kernel boot ID,
   boot completion, module lifecycle outcome, active payload and actual mounts.
   A runtime probe surviving reboot is not font-mount persistence.
6. Measure App cold start to first usable font library and warm library reopening
   with identical synthetic inventories on baseline/candidate. Report repetitions,
   per-sample values, median and p95. `am start -W` launch time alone does not prove
   the library is usable. Reserve an instrumentation hook that signals library
   data loaded AND visible; owner/App worker supplies this hook.
7. Bind results to candidate commit, module ZIP/APK SHA256 and device identity.
   Any missing, skipped, unsupported or failed requirement blocks delivery.

Do not give a downloadable candidate to the user as "tested" until all applicable
requirements are evidenced. The runtime-only `qualification.json` deliberately
reports `delivery_gate: NOT_RUN`, including when `qualification: PASS`; the
separate module delivery report records the full gate's actual result.

The candidate additionally runs the 32 composite-handoff/UTF-8 message cases
from `scripts/mix_handoff_contract_test.py` using its installed original ARM64
Python and Android shell in the Enforcing Magisk guest. Host results, duplicate
or missing cases, wrong module/shell or changed boot identity cannot pass.
The installed axis helper must read the pinned actual CFF2 collection's axis
name, 400/400/900 weight range and non-hidden flag.

The installed preview source selector additionally runs all 18 cases from
`scripts/preview_source_contract_test.py` under that original ARM64 Python and
Android shell. Selection-only files cover variable-source priority, nearest/tied
static weights, format ordering, literal and Chinese names, rejected directories,
missing sources and a 1000-file inventory. They are not rendering-font fixtures.
The report binds the exact module, shell, unchanged boot and Enforcing context;
host results, missing/duplicated/failed cases cannot satisfy this gate. This
contract does not replace actual App timings, font rendering or mount evidence.

The current installed `font_mix.sh` error function separately runs all 15 cases
from `scripts/composite_error_contract_test.py`, using that original ARM64 Python
and Android shell. The harness extracts the real installed function to avoid
executing the entry's dispatcher. It proves UTF-8/escaped/pretty/nested JSON
handling, bounded JSON log tails, old return-code priority and plain-text/helper
failure fallback. Exact boot, Enforcing context and complete named cases are
required. This is error-function evidence, separate from complete CLI generation;
the frozen legacy engine stays byte-for-byte intact.

`app_axis_gate.py` inspects an original generated variable TTF with `wdth`,
named custom `XTRA` and hidden `HIDN`, without applying it. The fixture enters
through the existing native importer's trusted `.stabletest` cache intake;
the importer must accept it as new CJK-capable font and preserve its SHA256.
No font-index cache or variable-font configuration is fabricated by the gate.
The real App must show the variable-font capability and the custom axis name,
retain the established Chinese label for width, and omit the hidden axis from
ordinary controls. Actual UI XML through the next font slot, a real screenshot,
live App PID, absent target fatal/ANR and unchanged system-font hashes are all
required. Cleanup removes only this new fixture, its importer-generated config
and its owned intake files. Selecting a font is UI evidence; it does not prove
App composite generation, native ARM64 phone rendering or OEM behavior.
The composition summary repeats slot titles: selectors must bind the actual
detailed CJK heading/explanation and ignore clickable summary ancestors. Only
the following detailed card can terminate the full-card scan. The recorded
`fixtures/axis-navigation-37160499707.xml` is a selector regression fixture;
replaying it is not a new Android run or evidence of successful axis display.

The legacy CLI composite component also requires the generated CJK collection's
sidecar and finalization report. They must match this request, source-composite
digest, original system TTC digest, ordered indexes and exact next-payload bytes.
Structural-only evidence cannot pass this component. Its activation still needs
a completed boot with a changed kernel ID, matching mounts/state, then a second
completed boot restoring the original font hashes. This does not exercise the
App's composite UI or every OEM partition/variable-font configuration.

## Architecture references

- Android's official acceleration requirements require matching x86 host/images
  or ARM64 host/images: https://developer.android.com/studio/run/emulator-acceleration
- GitHub-hosted runner limitations: https://docs.github.com/en/actions/reference/runners/github-hosted-runners
- API35 ARM app compatibility is a hypothesis to probe, not a standalone-ELF
  guarantee: https://github.com/ReactiveCircus/android-emulator-runner/issues/458

## Candidate task cleanup harness

After ARM64 qualification succeeds, push `common/task_scope.py` and
`tests/android-root-gate/task_scope_device.py` to the disposable AVD test directory.
Run the harness with the original embedded Python environment, `--helper` pointing
to the candidate helper and `--output` to a synthetic JSON report path. It rejects
host Linux and physical devices. It covers success/failure/timeout/cancel,
double-fork + setsid + TERM-ignoring descendants, delayed cleanup, and unrelated
sentinel preservation. This tests the candidate helper, not the unchanged baseline
(which has no such helper) or the entire module's integration.

App worker's proposed debug-only measurement contract uses tag `LuoShuStartup`,
events `app_start`, `library_open`, `font_index_visible`, `font_index_verified`,
`library_frame`, monotonic `elapsed_ms`, inventory `count` and `verified` boolean.
The usable endpoint is `library_frame verified=true` after the visible frame,
not cached data visibility. Baseline needs the same isolated measurement-only hook
or an equivalent UI readiness observation, disclosed with results.

## Existing-sudo CI execution

The second diagnostic run confirmed `/dev/kvm` exists as root:kvm 0660 with CPU
virtualization, but the hosted runner user is not in kvm. The runner already grants
NOPASSWD sudo. With authorization for a single privileged emulator lifecycle,
`run_emulator.py` starts only the official SDK emulator under an owned supervisor.
It neither changes permissions/groups/udev/sudoers nor disables SELinux. A private
throwaway HOME/AVD is used; SDK installation does not auto-accept new licenses.
Cancellation forwards to a supervisor that terminates and reaps its direct child.
Cleanup evidence and before/after KVM metadata must agree or the job fails.

This host privilege does not grant Android App `su` access or install a root
manager. App-to-su and real module-manager boot hooks remain separate required
gates before claiming font-library Root loading or module reboot persistence.


## Authorized Magisk guest and complete module testing

The official Magisk 30.7 APK is pinned to SHA256
`e0d32d2123532860f97123d927b1bb86c4e08e6fd8a48bfc6b5bee0afae9ebd5`.
Its official `v30.7/scripts/host_patch.sh` is pinned to
`1720669a684f75fe90a7318868dd4528f2e736a5ad5363f92a3c51c848d79703`.
The source SDK ramdisk is read and hashed, copied into the disposable guest,
patched using the official script with KEEPVERITY/KEEPFORCEENCRYPT, then booted
via a separate `-ramdisk` path after confirming the original emulator is reaped.
SELinux must remain Enforcing. This is an authorized guest security change;
no host KVM/group/udev/sudo policy is altered. Live Magisk setup is not used.

`module_gate.py` and `app_library_gate.py` are the next-stage harness. They use
real Magisk module installation, real boot hooks, synthetic A/B font changes,
invalid-selection preservation, default rollback byte checks and actual App UI
library/apply actions. The baseline module is CLI/mount reference only: the
original App receives no root grant and is not represented by the new App.
The sole permitted App root grant is an exact, non-shared user-0 `.stabletest`
UID, bounded to one hour and revoked on completion. A grant alone is not proof:
App evidence requires actual verified library frames for 100/1000 synthetic
fonts and a new matching switch task following a real UI apply click.
Pending, unsupported or failed stages must remain blocked.


## Legacy composite commit regression gate

The full candidate module cycle now additionally invokes the installed
`common/font_mix_controller.sh start` with two original geometric fixtures and
fixed 400-weight selections. `synthetic_fonts.py` gives each ASCII codepoint an
independent glyph, so the unchanged v14.4 engine performs actual Latin/digit
replacement instead of rejecting a one-glyph cmap fixture. Both baseline and
candidate single-font cycles continue to use the same fixtures.

`composite_gate.py` requires all of the following before delivery can pass:

- A real `axes_task` bound to its nested `mix_task`, successful generation and a
  matching request/digest manifest in `.luoshu-payload-next`.
- Background monitor success with its exact child-task log message. The gate
  only reads state during generation; it never calls a manual finalizer to rescue
  a broken monitor. A success-state write is not enough: the exact child-task
  committed marker must arrive within the task deadline. Public status must
  subsequently report terminal success.
- Unchanged currently visible font hashes before reboot, stage removal and
  cleared worker sidecars before the first manual finalizer replay (plus a
  delayed observation), all checked before reboot.
- Three actual concurrent finalizer replays, all successful and byte/state
  preserving. Separate Android lock ownership checks prove exclusion while the
  caller still holds the critical section open.
- A changed kernel boot ID, exact activated generation identity, actual mounted
  composite payload provenance, then default restoration and exact stock bytes.

`commit_lock_device.py` uses the shipped ARM64 runtime and Android `/system/bin/sh`
inside the existing Enforcing disposable Magisk AVD. Each invocation uses a
new UUID output path and must exit successfully; a previous PASS or a report
left by a failed/crashed invocation cannot satisfy the gate. Failure output is
retained only as diagnostics. Its unexported-fd control
records `fstat` and `flock` errno 9 (`EBADF`). The candidate helper must instead
retain the calling shell's lock after Python exits, produce errno 11 (`EAGAIN`)
for real contention, release a blocked waiter only after caller release and
preserve the persistent lock-file inode. Lock files are isolated test fixtures;
no shell, runtime, frozen core, mount code or security policy is patched.

`legacy_composite` is mandatory in the structured delivery verdict. These checks
remain distinct from the existing actual-App single-font apply test. They are
AOSP API35 x86_64/nativebridge evidence only, never ColorOS, physical-device,
native-ARM64 or App-composite-UI validation. Host schema/fixture tests alone cannot
satisfy this Android gate.
