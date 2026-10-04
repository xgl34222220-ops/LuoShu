# Recheck a reviewed candidate and Root artifact

These read-only tools bind downloaded evidence to the reviewed source, package,
frozen files and actual App observations. They reuse the existing Root verdict
and mount/axis helpers. They do not install anything, access a device, start CI,
or replace actual Android execution with host results.

Run from a checkout containing the reviewed source commits. Use the SHA-256
from the selected GitHub artifact metadata, not a checksum generated from an
unverified local file.

```sh
python3 tests/reviewed-artifacts/verify_candidate.py \
  candidate.zip SOURCE_COMMIT CANDIDATE_RUN ARTIFACT_ID \
  EXPECTED_ARTIFACT_SHA256 candidate-proof.json

python3 tests/reviewed-artifacts/verify_root.py \
  root.zip EXPECTED_ARTIFACT_SHA256 root-proof.json candidate-proof.json \
  /path/to/pinned-harness/tests/android-root-gate
```

The optional harness directory must contain the harness version used by that
Root run. Export `tests/android-root-gate` and `scripts` from that exact commit
into a scratch directory. Omitting it uses the current checkout's verdict;
new mandatory gates may correctly reject an older artifact. A missing gate is
never greened by an optional parser: the selected verdict remains authoritative.

The candidate tool checks ZIP integrity, external hashes, build provenance,
inner/outer APK bytes, the 17-file 1.1.1 manifest, nine reviewed runtime files
against Git and the unchanged legacy engine. The Root tool checks the selected
verdict, actual stock CFF2 face compilation, kernel boot identities, canonical
mount provenance, native-crash task ownership, actual import/axis XML and cleanup.
It also independently checks preserved rooted-App-stage logs and XML for target
ANRs and unresolved dialogs, rather than trusting a reported `anr:false`.
Initial unrooted stock-App checks remain a separately reported scope.
For harness versions with inventory timings, all fourteen cold/warm samples
must also match their preserved App logs and include a completed, successfully
reaped live request with consistent worker/scope/outer numeric spans. Historical
harness versions do not acquire new measurements when their artifacts are replayed.

Exit 0 means this artifact passed these checks. Exit 1 with a FAIL JSON means
preserved evidence blocks acceptance. Invalid inputs or a mismatched digest
abort before writing a success report. Artifact replay is not a new Android run.

[AOSP ANR diagnosis](https://source.android.com/docs/core/tests/debug/read-bug-reports#find-stack-traces)
explains binding VM traces to ANR PID/time and the limits of a late thread snapshot.
The tools and fixtures are independently written; no upstream implementation or
font resources were copied.
