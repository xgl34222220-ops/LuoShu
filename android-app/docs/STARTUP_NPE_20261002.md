# 冷启动初始化 NPE：2026-10-02

## 原始实测证据

- 候选源提交：`7d417af`
- 构建 run：`37010744032`；实测 run：`37013321974`
- 实测 APK SHA-256：`ce0be8445b14493f22c265fbf72d2b96b17a267e56d0f832889dec6adb99038b`
- 原始崩溃 map ID：`8122d05ac2a8834b36ad95f6ed49f54a43fb3995f433443c6b8417608550565a`
- 进程：`io.github.xgl34222220.luoshu.stabletest`
- NPE：`Attempt to invoke virtual method 'java.lang.Object ns0.t(ss)' on a null object reference`
- 栈顶：`e31.o:75`，构造入口：`j31.<init>:241`

该 CI 产物没有保存同版 mapping。不能用不同 map ID 的本地 mapping 冒充精确 retrace。

改为直接从上述 SHA 对应的真实 APK 提取 `classes.dex`，用 SDK `dexdump -d` 核对崩溃位置：

```text
e31.o:
  0x0046: iget-object v1, v13, Lj31;.H:Lk32;
  0x004a: invoke-virtual {v1, v0}, Lns0;.t:(Lss;)Ljava/lang/Object;
  position 0x004a = line 75

j31.<init>:
  0x00f0: invoke-static {v1, v5, v3, v2}, Lxe;.K:(Lzt;Lqt;Lbi0;I)Lk32;
  0x00f3: move-result-object v1
  0x00f4: iput-object v1, v0, Lj31;.H:Lk32;
  position 0x00f0 = line 241
  position 0x00f4 = line 245
```

实际调用链仍在 `launch` 中时，回调已经读取尚未赋值的 Job 字段。源码中对应 `cacheLoadJob = viewModelScope.launch { ... refreshFonts() }`，而 `refreshFonts()` 开始即调用 `cacheLoadJob.join()`。`Main.immediate` 和快速/空缓存不能被假定为一定先挂起再返回；字段初始化期间存在重入窗口。

## 最小修复

- `createFontCacheRestore()` 只创建 `CoroutineStart.LAZY` Job，不立即执行回调。
- Job 字段完成赋值后，在独立 `init` 中显式 `start()`，然后发起字体库刷新。
- 缓存恢复块不再回调 `refreshFonts()`，避免初始化过程中的自引用。
- 不靠 `delay()`、吞异常或允许空 Job 来掩盖错误。

## 验证边界

`FontCacheStartupTest` 覆盖立即完成的空缓存、字段发布前不执行回调、慢缓存等待顺序、取消的 owner 不启动恢复，共 4 项。这些测试保证所使用的启动原语及顺序，不替代 Android 冷启动验收。

修复后的候选必须在原实际 Android 路径重新执行强停后冷启动，并验证没有 `FATAL EXCEPTION`、字体库界面可见、缓存首显与 `verified=true` 日志。只有完成该复测，才能判定原实测崩溃已解决。
