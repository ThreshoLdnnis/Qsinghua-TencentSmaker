# 分支与交付基线评估（2026-11-16）

## 结论

当前最终产品基线应继续使用 `feat/personal-support-product` / `delivery/main`，而不是把 `origin/main` 整体合并回来。产品基线已经包含账号隔离、四字段理解、用户纠正确认、Keep / Release / Next、经历卡和显式跨会话参考；`origin/main` 虽然更新，但它把这些产品边界退回到单用户本机工程入口。

## 各分支内容

| 分支 | 主要内容 | 处理决定 |
|---|---|---|
| `origin/main`（4af677c） | 回退后的 Runtime、模块 1—8、LifeSnaps 回放；仍是全局 `app.main` 会话，README 明确身份归属待实现 | 不整体合并，会覆盖产品账号与经历卡边界 |
| `origin/codex/lifesnaps-agent-context` | LifeSnaps 四案例/21 天/七指标回放、上下文摘要和 Web 回放入口 | 保留为后续可选模块；只移植到产品 API 后才能进入公网 |
| `origin/sync/lovestone-delivery`（0854014） | 早期 LoveStone 页面、Runtime、语音和调用调度 | 只作为视觉和历史参考 |
| 本地 `feat/lovestone-web` | 旧视觉、循环背景、hydration 修复 | 视觉资源已择取，不能作为后端基线 |
| `feat/personal-support-product` | 产品 API、账号、卡片、四字段反思、部署配置、前端闭环和完整测试 | 当前主线 |
| `delivery/main`（83cb8c3，随后同步本轮提交） | 面向个人 GitHub 的可交付仓库 | 对外发布基线 |

## 为什么暂不直接合并 LifeSnaps

LifeSnaps 的数据回放本身有价值，但原实现的 `/sessions/{id}/wearables/replay` 依赖旧的全局会话和 `app.main`。直接 cherry-pick 会冲突 `settings`、`orchestrator`、`psychology/inputs`、可穿戴服务、前端 journey/client/types 以及测试，并可能重新暴露无账号归属的接口。它适合作为下一阶段的“授权可穿戴回放”模块：先把回放样本绑定到产品账号与当前旅程，再通过产品 API 提供，且继续明确标注为开发/模拟数据。

## 完工优先级

1. **当前必须完成**：保留产品基线，发布首页核心闭环叙事和 README；静态官网只做演示，不宣称真实模型或云端账号。
2. **上线真实产品前必须完成**：准备腾讯云单机后端、配置模型 Key、用虚构材料执行真实供应商双调用、再切换正式域名/API。
3. **后续增强**：将 LifeSnaps 做成账号绑定的授权数据回放模块；接入真实设备前继续保留来源、用途授权和模拟标记。

评估原则是先保证 2C Personal Emotional Agent 的核心体验完整，再扩展数据和评测能力；B2B 平台与案例知识层不应重新进入本次用户主流程。
