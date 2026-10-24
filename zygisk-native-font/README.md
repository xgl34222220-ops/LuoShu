# 洛书全局字体增强（Zygisk，主模块内置）

本目录是主模块内置 Zygisk 库的源码。`scripts/build.sh` 通过 `scripts/build_zygisk.sh` 为 arm64-v8a、armeabi-v7a、x86、x86_64 构建，并打包进主模块 ZIP：

| 主模块 ZIP 内路径 | 内容 |
| --- | --- |
| `zygisk/<abi>.so` | Zygisk 库（唯一入口；同时提供 root companion） |
| `zygisk/bin/<abi>/lsnf-config` | 配置编译工具 |
| `zygisk/defaults/exclude.list` | 内置排除名单 |
| `common/native_font.sh` | 配置层：`prepare` / `status` / `set` |
| `licenses/zygisk.hpp.txt` | zygisk.hpp 许可 |

不再有独立伴随模块 ZIP。字体替换本身不依赖 Hook；**Hook 仅在开关开启时由 Zygisk 库安装，默认关闭**。没有 Zygisk 时该库不会被加载，对系统完全没有影响。

## 行为

- **Java 层替换（Feature 1）：** Android 12–17（API 31–37）上通过 Zygisk `hookJniNativeMethods` 替换 `android.graphics.fonts.Font$Builder.nBuild`：App 自带的正文字体改用洛书当前已挂载生效的正文字体构建；图标 / 等宽 / 彩色 / 判定失败的字体一律放行。API 低于 31 或高于 37（未开 `allow_newer_api`）、签名不匹配、`faces.bin` 缺失时不安装，进程保持原状。
- **每次开机准备：** `system_server` 或第一个 App 进程发现本次开机还没有配置时，向 root companion 请求一次 `common/native_font.sh prepare`（不等待，进程启动不被拖慢；准备完成前启动的进程直接跳过）；配置已就绪但没有可用字体时，后续 App 进程会再请求刷新，companion 每 20 秒最多重跑一次、每次开机最多 30 次。prepare 把开关、名单和已对系统可见的洛书正文字体编译成 `zygisk/runtime/config.bin`、`faces.bin`，写入本次 `boot_id`；配置缺失、损坏或 boot_id 不符时一律跳过。
- **让出：** 洛书模块被禁用 / 待删除时整体关闭；洛书字体未就绪（当前为默认字体、待重启、payload 待重建、`LuoShu-<weight>` 未挂载到系统——`/system/fonts` 下同名文件或同一字体的 ROM 槽位文件大小不一致——或上一次加载验证明确 failed）时不写 `faces.bin`，替换不安装，原因写入 `runtime/state.conf` 的 `reason=` 并显示在 App；不依赖本次开机尚未完成的加载验证；进程里已有其它全局字体方案（`System.getProperty("luoshu.gfh.active")`）时让出。
- **跳过：** 系统 uid、隔离进程、子 zygote、DenyList、内置与用户排除名单；`system_server` 不注入。未安装 Hook 的进程会请求 Zygisk 卸载本库。

## 开关与名单

App：**设置 → 安全与维护 → 全局字体增强（Zygisk）**，修改后重启生效。配置在主模块 config 目录（模块更新保留）：

| 文件 | 作用 |
| --- | --- |
| `/data/adb/modules/LuoShu/config/native-font.conf` | `enabled`（默认 0）、`verbose`、`java_font`（默认 1）、`allow_newer_api`（默认 0） |
| `/data/adb/modules/LuoShu/config/native-font-exclude.list` | 用户排除名单，一行一个包名，`#` 后为注释；与内置名单合并 |
| `/data/adb/modules/LuoShu/config/native-font-force.list` | 预留，当前只解析不生效 |

兼容：`native-font.conf` 不存在时只读旧路径 `/data/adb/luoshu_native_font/`（`enabled`、`verbose`、`java_font.off`、`allow_newer_api`、`exclude.list`、`force.list`）；App 第一次保存时迁入新配置。

查看判定：`verbose=1` 后重启，`logcat -s LuoShuNativeFont`；本次开机状态：`zygisk/runtime/state.conf`；查看配置：`zygisk/bin/arm64-v8a/lsnf-config dump zygisk/runtime/config.bin`。

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

CI：`.github/workflows/zygisk-native-font.yml`（主机单测 + 4 ABI 构建 + 静态门禁 + 配置层测试 `scripts/native_font_test.sh`）；主模块 ZIP 由 `scripts/build.sh` 打包并校验四个 ABI。

## 第三方

- `third_party/zygisk/zygisk.hpp`：Zygisk 公开 API 头文件，原样保留，许可见 `third_party/zygisk/LICENSE`。
