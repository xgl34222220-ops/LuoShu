# 洛书 v14.3 Alpha1.7

## 双皮肤架构第一阶段

- 原生 App 新增 `UiStyle.MATERIAL / UiStyle.MIUIX` 两档界面风格，设置后通过 DataStore 持久化，切换时整个主题和导航层立即重组，无需重启 App。
- 外观状态由独立 `AppearanceRepository + AppearanceViewModel` 管理，通过全局 CompositionLocal 提供只读设置；字体数据、Root 桥接和业务 ViewModel 不复制、不分叉。
- 首页概览已拆分为完整的 `HomeScreenMaterial()` 与 `HomeScreenMiuix()` 两份实现，两者只共用 `HomeUiState / HomeActions`。
- 界面设置页也分别提供 Material 与 Miuix 排版，作为后续字体库、字体组合和日志双实现的模板。

## Material 3 Glass

- 采用 MaterialKolor 根据同一种子色生成完整 Material 3 色板，提供柔和、鲜艳、中性三种算法风格。
- 支持跟随系统、浅色、深色三态，以及纯黑 AMOLED 模式。
- 首页主状态卡使用 primary → tertiary 渐变并叠加白色高光，悬浮底栏支持 Haze 玻璃模糊、半透明和关闭模糊后的实色模式。
- Material 页面使用标准 Material 3 shape scale、Card、ListItem、Slider 与 Switch。

## Miuix / HyperOS

- 延续白泽验证过的手写 Miuix 适配层，不直接把页面绑定到实验性上游组件 API。
- 使用更饱满的超椭圆卡片、大号粗体状态、紧凑的“图标 + 标题 + 描述 + 右侧操作”列表，以及液态滑动底栏。
- 设置页提供胶囊色块滑动的 Miuix SuperSwitch 风格。
- Miuix 与 Material 共用 Monet、种子色、MaterialKolor 算法风格和深色模式设置，但组件形状、字重、信息密度与悬浮层表现独立。

## 当前迁移范围

- 首页概览：已完成独立 Material 与 Miuix 两份实现。
- 界面设置：已完成独立 Material 与 Miuix 两份实现。
- 字体库、字体组合、运行日志：本阶段继续复用同一业务层和可响应当前风格的过渡 UI，后续按首页模板逐页拆为两份实现。
- 原有真实多轴预览、静态多字重、同字体直应用、系统全局粗细微调、字形覆盖诊断和安全导入全部保留，底层执行逻辑未改动。

本版本为双皮肤架构真机测试版，PR 继续保持 Draft，不合并、不发布。
