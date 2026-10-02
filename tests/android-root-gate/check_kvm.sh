#!/usr/bin/env bash
# Read-only diagnostic. No chmod, chown, udev, group, sudoers, or module changes.
set -uo pipefail
printf '=== runner identity ===\n'
id
groups
uname -m
printf '\n=== KVM device ===\n'
if [[ ! -e /dev/kvm ]]; then
  printf 'KVM_DEVICE_MISSING\n'
else
  ls -l /dev/kvm
  stat -c 'type=%F mode=%a uid=%u gid=%g owner=%U group=%G major_minor=%t:%T' /dev/kvm
  if command -v getfacl >/dev/null; then getfacl -p /dev/kvm; fi
fi
printf '\n=== CPU virtualization flags ===\n'
grep -m 1 -oE '\b(vmx|svm)\b' /proc/cpuinfo || true
printf '\n=== existing sudo policy (query only) ===\n'
if command -v sudo >/dev/null; then
  sudo -n -l 2>&1
  printf 'sudo_policy_query_exit=%s\n' "$?"
else
  printf 'sudo_command_missing\n'
fi
printf '\n=== runner access ===\n'
python3 - <<'PY'
import json, os, stat, sys
p='/dev/kvm'
r={'exists':os.path.exists(p),'readable':os.access(p,os.R_OK),'writable':os.access(p,os.W_OK)}
r['character_device']=r['exists'] and stat.S_ISCHR(os.stat(p).st_mode)
if not r['exists']: r['result']='BLOCKED_KVM_DEVICE_MISSING'
elif not r['character_device']: r['result']='BLOCKED_KVM_NOT_CHARACTER_DEVICE'
elif not (r['readable'] and r['writable']): r['result']='BLOCKED_RUNNER_KVM_PERMISSION'
else:
    try:
        fd=os.open(p,os.O_RDWR | os.O_CLOEXEC)
        os.close(fd)
        r['result']='KVM_ACCESS_PASS'
    except OSError as e:
        r.update(result='BLOCKED_KVM_OPEN',errno=e.errno,error=str(e))
print(json.dumps(r))
sys.exit(0 if r['result']=='KVM_ACCESS_PASS' else 1)
PY
