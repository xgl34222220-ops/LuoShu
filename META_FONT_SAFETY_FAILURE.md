# Meta font safety validation failure v3

Exit code: 1

```text
+ python3 scripts/finish_meta_font_safety_refactor_v3.py
+ chmod 0755 common/font_safety.sh common/mount_compat.sh scripts/font_safety_test.sh scripts/meta_module_sync_test.sh
+ chmod 0644 common/font_config_targets.py scripts/font_config_targets_test.py
+ python3 -m py_compile common/font_config_overlay.py common/font_config_targets.py scripts/font_config_targets_test.py
+ sh -n common/font_config_runtime.sh
+ sh -n common/font_config_partitions.sh
+ sh -n common/font_safety.sh
+ sh -n common/mount_compat.sh
+ sh -n post-fs-data.sh
+ sh -n service.sh
+ sh -n common/font_manager.sh
+ sh -n common/font_mix.sh
+ python3 scripts/font_config_overlay_test.py
Traceback (most recent call last):
  File "/home/runner/work/LuoShu/LuoShu/scripts/font_config_overlay_test.py", line 65, in <module>
    raise SystemExit(main())
                     ^^^^^^
  File "/home/runner/work/LuoShu/LuoShu/scripts/font_config_overlay_test.py", line 39, in main
    assert report["changed_fonts"] == 3, report
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: {'changed': True, 'changed_fonts': 1, 'changed_families': ['sys-sans-en']}
```
