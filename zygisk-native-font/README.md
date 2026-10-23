# 洛书 Native 字体伴随模块（实验）

可选的 Zygisk 伴随模块，独立 ZIP（模块 ID `LuoShuNativeFont`），不进入主模块 ZIP，主模块保持零 Hook。

## 当前阶段（N1 骨架 + N2 判定库）

- **不安装任何 Hook。** 每个 App 进程在 `preAppSpecialize` 里只做：快速跳过（系统 uid、隔离进程、子 zygote、DenyList）→ 通过模块目录 fd 读 `runtime/config.bin` → 开关 / boot_id / 排除名单判定 → （开启详细日志时）写一行 logcat → 请求 Zygisk 卸载本库。进程状态与不装本模块时一致。
- `system_server` 不注入（`preServerSpecialize` 直接卸载）。
- 图标字体判定库 `src/sfnt_verdict.*` 已就绪并有单测，但 N1 不调用；N3/N4 接入 `Font$Builder.nBuild` 时才生效。

## 开关与名单

设置目录：`/data/adb/luoshu_native_font/`（模块更新不丢，卸载模块时清除）

| 文件 | 作用 |
| --- | --- |
| `enabled` | 存在即开启（默认不存在 = 关闭） |
| `verbose` | 存在即在 logcat 输出每个进程的判定（tag `LuoShuNativeFont`） |
| `exclude.list` | 用户排除名单，一行一个包名，`#` 后为注释；与内置 `defaults/exclude.list` 合并 |
| `force.list` | 预留给后续「强制生效」名单，当前只解析不生效 |

修改后重启生效：`post-fs-data.sh` 在 zygote 启动前用 `bin/<abi>/lsnf-config` 把开关与名单编译成 `runtime/config.bin`，写入本次 `boot_id`；主模块 `LuoShu` 不存在、被禁用或待删除时强制关闭。配置缺失、损坏或 boot_id 不符时模块一律跳过。

查看判定：`logcat -s LuoShuNativeFont`；查看配置：`/data/adb/modules/LuoShuNativeFont/bin/arm64-v8a/lsnf-config dump /data/adb/modules/LuoShuNativeFont/runtime/config.bin`。

## 图标字体判定（N2）

输入原始 sfnt 字节（零拷贝，单字体最多读 256 KB），输出 `keep / replace_latin / replace_cjk`：

1. 名字门：文件名/asset 名与 name 表（ID 1/2/4/6/16）命中保留词表 → 保留。词表由 `tools/gen_keep_words.py` 从 `common/font_import.sh` 与 `common/font_inventory.py` 生成，CI 校验同步。
2. 彩色表：COLR / CBDT / sbix / SVG → 保留。
3. cmap（优先 3,10 → 0,4/0,6 → 3,1 → 0,3；只有 3,0 symbol 表 → 保留）统计拉丁、数字、汉字、PUA：PUA 图标（≥256 且占比 ≥30%，或拉丁很少而 PUA 占多数）、纯数字、非正文（拉丁 <40 且汉字 <1000）→ 保留。
4. 等宽：`post.isFixedPitch` 或 OS/2 panose 等宽 → 保留。
5. 其余：汉字 ≥1000 → `replace_cjk`，否则 `replace_latin`。

解析失败、越界、WOFF/WOFF2、超出读取预算一律保留。结果按表目录哈希缓存在进程内存（512 项），不落盘。

## 构建与测试

```sh
# 主机单测（ASan/UBSan）与微基准
python3 tools/gen_keep_words.py --check
python3 tools/make_test_fonts.py build/corpus
cmake -S . -B build -DLSNF_HOST_TESTS=ON -DLSNF_SANITIZE=ON && cmake --build build && ctest --test-dir build -V
# Android（每个 ABI 一次）
cmake -S . -B out/arm64-v8a -DCMAKE_TOOLCHAIN_FILE=$ANDROID_NDK/build/cmake/android.toolchain.cmake \
      -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-26 -DANDROID_STL=c++_static -DCMAKE_BUILD_TYPE=Release
```

CI：`.github/workflows/zygisk-native-font.yml`（主机单测 + 4 ABI 构建 + 静态门禁 + 打包 ZIP）。

## 第三方

- `third_party/zygisk/zygisk.hpp`：Zygisk 公开 API 头文件，原样保留，许可见 `third_party/zygisk/LICENSE`。
