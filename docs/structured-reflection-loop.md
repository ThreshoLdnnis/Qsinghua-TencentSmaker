# 四字段理解与纠正闭环

此模块使用现有 PsychologyAdapter、模型调用调度、会话锁、取消与来源检查。结构正确不代表心理判断正确；心理路线与措辞仍为待专业审核的工程能力。测试全部使用虚构数据和注入模型，未调用真实供应商。

## 输入与模型结果

启用 `PSYCHOLOGY_ENABLED=true` 走原有结构化心理流程。产品配置另启用 `PSYCHOLOGY_REQUIRE_UNDERSTANDING=true`：普通支持 `routine_support` 必须返回完整 `understanding`，否则整轮失败，不保存半轮消息或画布。安全支持路线允许不生成画布，现实支持入口不依赖确认、设备或游戏。

模型结果新增：

```json
{
  "understanding": {
    "facts": "用户报告旅行后作息变化。",
    "interpretation": "可能与行程变化有关，需要你确认。",
    "emotions": "还不确定，需要你确认。",
    "needs": "也许希望整理自己的节奏，需要你确认。"
  }
}
```

四个键必须齐全，值为去除首尾空白后的字符串，每栏最多 1000 字；单栏可空，至少一栏有内容。`facts` 是用户所述，未声称独立核实；其余字段均是可修改、待确认假设。模型必须引用本轮输入，不能以助手历史、通用草稿或设备评分冒充个人事实。旧结果不含 `understanding` 时仍可在未启用严格产品配置的模式下运行。

提示版本为 `psychology.reflection.v2`。只进行一次有时限、字符预算和输出校验的结构化调用，不自动重试或伪造补全缺失字段。

正式模型建议配置 `LLM_MAX_TOKENS=1600` 或更高，以容纳路线、回复和四字段；供应商截断会触发失败回滚。没有配置模型凭据时不会宣称已完成真实模型联通。

## 生成、修改与确认

`POST /sessions/{id}/messages` 保留原请求契约。成功响应新增 `generated_understanding`：

```json
{
  "generated_understanding": {
    "understanding": {
      "understanding_id": "服务器生成的编号",
      "revision": 1,
      "status": "proposed",
      "interpretation": "可能与行程变化有关，需要你确认。",
      "fields": {"facts": "…", "interpretation": "…", "emotions": "…", "needs": "…"},
      "origin": "agent_hypothesis",
      "evidence_refs": [{"kind": "user_report", "source_id": "服务器生成的自述编号", "revision": 1}]
    },
    "confirmation_token": "仅对当前版本有效的凭据"
  }
}
```

示例省略对象时间字段。该对象、来源自述与本轮两条消息在完整校验后一次提交；失败、超时或取消不产生半张画布。长输入以每段最多 2000 字的完整自述片段保存，不截断原话。设备来源保留授权版本依赖，用户确认的当前解释保留理解版本依赖。普通生成不自动获得跨会话保存或案例库使用权限。

用户修改继续使用 `PUT /sessions/{id}/understandings/{understanding_id}`，在原来的 `interpretation`、`origin`、`evidence_refs`、`expected_revision`、`operation_id` 之外可传完整 `fields`。这会生成新修订、撤销旧确认并换发凭据；只改情绪或需求栏也属于有效纠正，可以中断正在使用旧理解的调用。

`POST /sessions/{id}/understandings/{understanding_id}/confirm` 仍提交 `expected_revision`、`confirmation_token`、`operation_id`。确认本身会递增版本；后续保存经历卡应使用确认响应中的新 `revision/confirmed_revision`。旧版本确认和修改明确拒绝。

每轮回复的来源依赖新增 `generated_understanding_refs`，包含自己产出的画布版本与继承的画布依赖。画布被修改、确认、拒绝或作废后，依赖旧版本的回复不再用于下一轮上下文，旧请求编号也不重放旧画布或旧凭据。已有存档格式可读取缺少这些新增可选字段的快照；新快照保留字段及依赖，恢复时重新签发待确认凭据。

来源用途由服务器在 UnderstandingEntry 的 `evidence_scope` 中记录：普通手动提出的理解默认 `local_analysis`，模型生成项为 `model_context`。编辑、确认及控制视图按该原用途校验；客户端不能把用途改写为授权。存档保留用途标签，但恢复仍不恢复任何设备权限。用户确认理解不等于允许把仅本地分析的数据发给模型。

## 显式跨会话参考

产品层可以在用户所属的 SessionService 上提供同步 `recall_loader() -> (epoch, cards)` 与 `recall_current(epoch) -> bool`。主体归属、卡片保存和撤回权限由产品层验证，本模块不接受模型授予权限。

- 只有 `remember_for_future=true` 的当前卡片可被读取，每轮最多三张。
- `record.recall_enabled=false` 时不调用加载器；本轮不读取经历卡。
- 模型只收到卡片的 `fields`、`keep_text`、`next_step`，不发送 `release_text`、标题、卡片编号或其他私有字段。
- 来源清单用 `experience_card_id`、`experience_card_revision`、`experience_card_title` 记录所参考的版本，供界面展示；标题缺省时取事实栏的前 256 字。
- 调用前后检查记忆 epoch 与本轮选择。编辑、删除、撤回授权或选择变化时，迟到结果拒绝提交。
- 产品层还需在记忆变化或从参考切换为不参考时清空相关旧会话，避免对话历史重新带入已经撤回的内容。

这个上下文仅用于本次支持，不是训练、自主执行或临床记录。卡片持久化、用户隔离、删除与公开账号 API 由产品层单独负责，原有本机全局存档接口不提供多用户隔离保证。

## 验收

`tests/test_reflection_loop.py` 验证四字段生成与原子提交、缺失/错误输出回滚、旧模式兼容、安全入口、来源约束、纠正与确认版本、旧回复和凭据失效、运行中纠正、记忆筛选与撤回、按轮不读取、存档以及长输入完整性。相关原有心理、理解、运行与业务存档测试同时回归。
