# 翎语产品闭环与运行说明

## 当前状态

2026-11-08：产品 API、前端接入、账号隔离、经历卡与显式跨会话参考的代码已实现。用户目前没有运行本项目的后端服务器，模型 Key 尚未配置；没有完成真实供应商联调。[官网](https://qsinghua.lingozm.cn/) 当前是 EdgeOne 静态演示。更新静态页面只能交付界面，不能启动 Python、SQLite 或真实模型调用。

当前主产品是 2C Personal Emotional Agent。心象宇宙与角色「拾光」承载表达、核对、支持选择与回看；四字段 AI 理解始终为可修改、待确认假设，不做诊断。可穿戴数据显著标注模拟；CaseForge 为内部研发评测视图。案例知识层仅接受另行授权、公开合法或受控合成的材料，不自动收集私人对话；B2B 为未来路线。

## 两个运行入口

| 入口 | 用途与边界 |
|---|---|
| `app.product.main:create_app --factory` | 产品账号、用户所属旅程和卡片 API；只运行一个 worker |
| `app.main:app` | 原本机工程、CLI、语音和全局存档联调；仅绑定 `127.0.0.1`，不代理到公网 |

生产不能用原工程入口替代产品入口。产品旅程仍为进程内状态，多 worker 或多副本会造成会话分散；横向扩容前需实现共享状态和跨进程一致性。

## 本地启动

需要 Python 3.12+、Node.js 22+。从仓库根目录运行；已有 `.venv` 时跳过创建，已有 `.env` 时不要覆盖。模型凭据填写在根目录 `.env` 的 `DEEPSEEK_API_KEY`，只留在服务端。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:PRODUCT_ORIGIN = 'http://127.0.0.1:3070'
$env:PRODUCT_COOKIE_SECURE = 'false'
$env:LLM_MAX_TOKENS = '1800'
.\.venv\Scripts\python.exe -B -m uvicorn app.product.main:create_app --factory --host 127.0.0.1 --port 8070 --workers 1
```

另一个终端：

```powershell
cd frontend
npm ci
$env:LOVESTONE_PRODUCT_API_URL = 'http://127.0.0.1:8070'
npm run dev -- --port 3070
```

访问 [本地产品页面](http://127.0.0.1:3070)。浏览器、`PRODUCT_ORIGIN` 和前端地址统一使用 `127.0.0.1`，不要混用 `localhost`。`LOVESTONE_PRODUCT_API_URL` 是 Next 服务端变量，不使用 `NEXT_PUBLIC_` 前缀。正式 HTTPS 部署必须启用 `PRODUCT_COOKIE_SECURE=true`，本地 HTTP 的关闭配置不能直接用于公网。

缺少 Key 时产品 API 返回配置缺失错误，不自动伪造真实回复。独立演示仍可使用虚构样本；固定脚本只用于明确标注的工程演示与测试。产品入口固定关闭脚本模式。

本机配置 Key 后，可用 `python -m scripts.verify_live_product --live` 对虚构材料执行两次真实供应商调用，核对生成、纠正、确认、保存和下次提供记忆。脚本使用临时数据库，不操作现有账号记录；未配置 Key 时明确返回 `not_run`，不冒充联调通过。

## 一次支持流程

1. 注册或登录。用户名为 3–32 位字母、数字、下划线或连字符；密码为 10–128 个字符。当前没有邮箱或密码找回。
2. 新建个人旅程，输入经历；本轮同意调用模型后，才发送当前内容、所选有效上下文与已授权的设备摘要。模型发送不是本地离线推理。
3. 真实模型适配器返回支持回复及事实、解释、情绪、需要四栏。四键必须齐全，每栏最多 1000 字；单栏可空，至少一栏非空。信息不足应保留未知，而不是补造经历。
4. 用户修改理解，再确认当前版本。编辑撤销旧确认；确认会递增版本，后续保存必须提交确认响应的新版本。旧请求或旧凭据不能恢复过期画布。
5. 选择 Keep、Release、Next 并自主决定是否保存经历卡。卡片只从当前已确认的四字段生成，不能由客户端冒充已确认状态。Release 文本不写入卡片；主动保存的其他卡片字段仍会保留。
6. 成长档案可查看自己的卡片，改变未来参考授权或删除。另一次对话只有在当轮开启参考时，才读取最多三张已授权的当前卡片。

支持路线与措辞仍为 `unreviewed`。即时现实支持入口不要求先确认画布、完成角色故事或导入设备；故障也不会被伪装成普通支持成功。尚未完成专业效果评测或专业安全审核。

## API 契约

所有路径均属于产品入口；前端使用同源 `/api/*`。用户归属从服务端登录会话确定，请求不能自报 `owner_id`。

| 方法与路径 | 输入与结果 |
|---|---|
| `POST /api/account/register`、`POST /api/account/login` | `{username,password,consent:true}`；返回用户、CSRF 凭据，并设置登录 Cookie |
| `GET /api/account/me` | 当前用户与 CSRF 凭据；未登录返回 `user:null` |
| `POST /api/account/logout`、`DELETE /api/account/me` | 退出或删除账号；删除同时移除该用户卡片和账号数据 |
| `POST /api/support/sessions` | 新建当前用户的进程内旅程 |
| `POST /api/support/sessions/{id}/messages` | `{content,request_id,model_consent:true,use_memories:false}`；返回回复、`generated_understanding`、来源清单和 `memory_refs` |
| `PUT /api/support/sessions/{id}/understandings/{understanding_id}` | 完整 `fields`、兼容解释文本、来源、操作编号及预期版本；返回新版本与新确认凭据 |
| `POST /api/support/sessions/{id}/understandings/{understanding_id}/confirm` | `expected_revision`、`confirmation_token`、`operation_id`；返回已确认的新版本 |
| `POST /api/product/cards` | `operation_id`、所属会话/理解编号、确认后的 `expected_revision`、`choice`、Keep/Release/Next 文本与 `remember_for_future`；主动保存卡片，Release 内容丢弃 |
| `GET /api/product/cards` | 仅列出当前用户的卡片 |
| `PATCH /api/product/cards/{id}` | `{expected_revision,remember_for_future}`；按版本改变未来参考授权 |
| `DELETE /api/product/cards/{id}?expected_revision=N` | 按版本删除当前用户的卡片 |

修改请求除注册/登录外需 `X-CSRF-Token`；所有修改请求的 `Origin` 必须与 `PRODUCT_ORIGIN` 完全一致。健康检查为 `GET /api/support/health`，其中 `key_configured` 仅说明有配置，不证明供应商认证、额度或调用已通过。理解细则见 [四字段契约](structured-reflection-loop.md)。

## 数据与隐私边界

账号凭据、登录会话元数据与用户主动保存的卡片位于 `PRODUCT_DATA_DIR`，默认 `data/product`。密码使用带随机盐的 scrypt 派生，数据库不保存原始登录 token；登录使用 HttpOnly、SameSite Cookie，正式 HTTPS 下启用 Secure，有效期七天。Origin/CSRF 检查、用户命名空间、基本请求限额与版本检查已实现。

这些措施不等于端到端加密。SQLite 中经历卡内容为明文，具有主机或备份权限的人可以读取；备份、访问权限和删除运维仍需部署负责人管理。没有邮箱恢复、成熟的未成年人隐私/监护流程、完整生产运维或专业审核，不应据此宣称已具备面向真实青少年的正式服务保障。

对话、当前理解、模拟设备记录与用途授权只留在进程内，不随普通聊天自动写入卡片库；服务重启后不会恢复。原工程入口的可选会话存档是另一套本机功能，没有通过产品公网入口开放。注册登录会持久化必要账号数据，即使尚未保存经历卡。

模型调用同意、主动保存卡片、`remember_for_future` 和当轮 `use_memories` 分开控制。卡片只向模型提供四字段、Keep 与 Next，不提供 Release。撤回参考、删除卡片或从参考改为不参考时会清空相关当前对话，防止旧助手历史重新引用已撤回内容；这不会删除用户另行保存的其他卡片。删除账号会移除本服务所属的账号和卡片数据，不代表可以撤销已经完成的供应商处理。

## 目录与验证

```text
app/product/                    产品边界、账号与卡片存储
app/agent/reflection.py          四字段候选构建与原子提交辅助
app/psychology/                  结构化适配、来源校验与版本化提示
frontend/src/app/api/            Next 同源账号/产品桥接
frontend/src/lib/product-*.ts    产品客户端与桥接契约
deploy/                         单机部署配置
tests/test_product_*.py          产品账号、隔离与闭环测试
tests/test_reflection_loop.py    四字段、纠正、授权与来源回归
```

仓库根目录执行 `.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider tests`；在 `frontend` 执行 `npm test`、`npm run typecheck`、`npm run build`。自动检查使用注入模型和虚构数据；真实供应商调用、实际服务器、HTTPS 和跨浏览器线上验收需要部署后另行记录，不能由单元测试结果替代。
