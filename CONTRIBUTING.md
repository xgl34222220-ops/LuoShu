# 贡献指南

感谢参与洛书开发。

## 提交前

- 基于最新 `main` 创建分支。
- 一个 PR 尽量只处理一类问题。
- Shell 脚本必须兼容 Android `/system/bin/sh`，不要依赖设备未必具备的 GNU 参数。
- WebUI 应保持离线可用，不引入外部 CDN、遥测或账号依赖。
- 不提交商业字体、ROM 提取字体、用户日志、设备备份或其他无授权文件。
- 不把 Emoji、图标字体或符号字体替换重新加入项目。
- 不覆盖 `fonts.xml`、`font_fallback.xml` 等完整系统字体配置。
- 不在刷写、`post-fs-data` 或开机关键阶段执行大型字体生成任务。
- 新增 Root 命令时必须考虑参数引用、路径校验和事务回滚。

## 本地检查

```sh
sh -n customize.sh
sh -n post-fs-data.sh
sh -n service.sh
find common -maxdepth 1 -type f -name '*.sh' -exec sh -n {} \;
python3 -m py_compile common/composite_font.py
sh ./scripts/check.sh
sh ./scripts/build.sh
```

修改 WebUI 时，建议将 ES module 临时复制为 `.mjs` 后运行：

```sh
cp webroot/v14.js /tmp/v14.mjs
node --check /tmp/v14.mjs
```

## 字体相关测试

至少覆盖：

- TrueType `glyf` 中文基底；
- CFF/CFF2 中文基底；
- TTC 多字体面；
- 可变英文或数字字体；
- 缓存命中；
- 内存不足或生成失败；
- 事务提交中断；
- ColorOS 与 HyperOS 字体槽；
- Mountify 启用与未启用状态。

任何新生成路径都必须先在暂存目录完成并验证，再替换活动负载。

## 文档与许可证

新增第三方代码或二进制时，必须：

- 说明来源和版本；
- 确认许可证兼容；
- 在 `THIRD_PARTY_NOTICES.md` 中登记；
- 将完整许可证放入 `licenses/`；
- 更新构建脚本，保证发布包携带许可证。

## PR 描述

请写明：

- 改动目的；
- 主要实现；
- 风险点；
- 已测试环境；
- 回滚方式；
- 是否改变模块路径、缓存或版本号。
