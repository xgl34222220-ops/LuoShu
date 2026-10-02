# Root Android delivery gate

`luoshu-root-android-probe.yml` is an environment qualification check, **not a
release check**. PASS proves the unmodified baseline ARM64 ELF can execute its
Python/FontTools/native extensions and launch children on that specific AVD,
before and after a verified kernel reboot. It does not prove module installation,
font activation, rollback, child cleanup, or persistent font mounts.

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

## Required delivery evidence (all pending until actually executed)

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
requirements are evidenced. This probe deliberately reports `delivery_gate:
NOT_RUN`, including when `qualification: PASS`.

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
