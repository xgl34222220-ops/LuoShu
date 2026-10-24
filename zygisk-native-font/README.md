# 洛书 Native 字体伴随模块（实验）

可选的 Zygisk 伴随模块，独立 ZIP（模块 ID `LuoShuNativeFont`），不进入主模块 ZIP，主模块保持零 Hook。

## 当前阶段（N3：Java 层 Font$Builder.nBuild 替换）

- **N3 已包含 Feature 1：Java 层替换。** 在 Android 12–17（API 31–37）上通过 `RegisterNatives` 替换 `android.graphics.fonts.Font$Builder.nBuild`：App 自带的正文字体改用洛书当前已验证生效的正文字体构建；图标 / 等宽 / 彩色 / 判定失败的字体一律保留原样。API 低于 31 或高于 37（未开 `allow_newer_api`）、签名不匹配、`faces.bin` 缺失时不安装，进程保持原状。
- **默认关闭。** 开启：`touch /data/adb/luoshu_native_font/enabled` 后重启；总开关开启后 Java 层替换随之开启，`touch /data/adb/luoshu_native_font/java_font.off` 可单独关闭。
- **让出：** 洛书主模块不存在 / 被禁用 / 字体未验证生效（`device-font-load-verification` 非 verified、待重启、payload 待重建）时不写 `faces.bin`，Feature 1 不安装。
- **日志：** `touch /data/adb/luoshu_native_font/verbose` 后重启，`logcat -s LuoShuNativeFont` 查看每个进程的判定与替换。

N1/N2 基础行为： 每个 App 进程在 `preAppSpecialize` 里只做：快速跳过（系统 uid、隔离进程、子 zygote、DenyList）→ 通过模块目录 fd 读 `runtime/config.bin` → 开关 / boot_id / 排除名单判定 → （开启详细日志时）写一行 logcat → 请求 Zygisk 卸载本库。进程状态与不装本模块时一致。
- `system_server` 不注入（`preServerSpecialize` 直接卸载）。
- 图标字体判定库 `src/sfnt_verdict.*` 由 N3 的 `Font$Builder.nBuild` 替换调用。

## 开关与名单

设置目录：`/data/adb/luoshu_native_font/`（模块更新不丢，卸载模块时清除）

| 文件 | 作用 |
| --- | --- |
| `enabled` | 存在即开启（默认不存在 = 关闭） |
| `verbose` | 存在即在 logcat 输出每个进程的判定（tag `LuoShuNativeFont`） |
| `java_font.off` | 存在即单独关闭 N3 Java 层 `Font$Builder.nBuild` 替换（默认随总开关开启） |
| `allow_newer_api` | 存在即允许在高于 API 37 的系统上尝试安装（默认不允许） |
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
