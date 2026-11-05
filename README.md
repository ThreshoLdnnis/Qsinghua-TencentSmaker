# 清华-腾讯S-Makers向善创客计划青少年心理平台\*翎语

**[在线体验翎语](https://qsinghua.lingozm.cn/)**

![翎语 · 心象宇宙封面](docs/assets/cover.png)

<p align="center">
  <img src="docs/assets/tsinghua-xlab-logo.png" alt="清华经管学院 · 清华 x-lab" width="420" />
  &nbsp;&nbsp;
  <img src="docs/assets/tencent-ssv-logo.png" alt="腾讯 SSV" width="330" />
</p>

> 这个世界从不缺少问题，缺少的是愿意用最好的工具去解决它们的优秀人才。

## 产品与演示范围

LoveStone 是面向个人的情绪支持 Agent。心象宇宙把一次支持对话做成可回看的经历：用户说出发生了什么，与角色「拾光」一起核对理解，选择接下来想怎么照顾自己，再决定要不要留下一张经历卡。AI 理解是可以纠正的假设，不是诊断。

## 运行前端演示

在仓库根目录执行（需要 Node.js 22 或以上，建议使用受支持的 LTS 版本）：

~~~powershell
cd frontend
npm ci
npm run dev
~~~

打开 [http://127.0.0.1:3000](http://127.0.0.1:3000)。默认演示不需要启动 Python 服务，也不需要 API Key。

1. 从心象宇宙首页选「开启心象旅程」，点「使用虚构示例」，再点输入框右侧箭头（生成理解草稿）。
2. 在对话页编辑事实、解释、情绪或需要，再点「确认当前理解」；也可去心象画布逐层回看。
3. 选择 Keep（留下）、Release（放下）或 Next（向前），主动「保存经历卡」；到成长档案检查结果。

个人状态页展示明确标注的模拟可穿戴趋势。CaseForge 是独立的内部研发评测视图。演示仅用虚构输入；不要录入真实敏感资料。真实聊天联调（可选）、数据边界、现有 API 和后续接口见[前端产品与联调说明](docs/frontend-product.md)。

首页和四个用户内页各有独立的电影感场景：暗色拾光对话、明亮心象画布、六段式身心状态、星空成长档案。背景视频在显示时静音自动循环，页面支持逐词渐显、滚动揭示、理解层切换、交互趋势与卡片展开。移动端使用折叠导航。系统减少动态效果时保留静态呈现。外部视频加载期间或失败时显示本地海报，演示逻辑可离线运行。

在 `frontend/` 运行 `npm run typecheck`、`npm test`、`npm run build` 验证前端。下文保留现有 Python 运行、测试与评测入口。

## Personal Emotional Agent 后端

Agent 运行框架，已支持 DeepSeek 多轮聊天、会话与运行状态、取消与去重、
通用草稿纠正、上下文来源、离线评测，以及可选本地保存恢复。

后端业务状态目前保持 INITIAL。心理理解、澄清策略、Mind Canvas、K/R/N 和专业安全规则仍待团队确认与接入。

## 首次运行（Windows PowerShell）

在克隆下来的项目文件夹打开终端。文件夹可以位于任意磁盘、使用任意名称，无需修改源码路径。
请先安装 Python；本项目最近验证环境为 Python 3.13。

~~~powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -B -m app.cli --demo
~~~

如果没有 py 启动器，可用对应 Python 解释器运行 python -m venv .venv。
依赖安装完成后，离线演示不需要 API Key。

## 配置真实聊天

仅当项目内还没有 .env 时，从模板创建配置（已有 .env 时跳过复制，避免覆盖 Key）：

~~~powershell
Copy-Item .env.example .env
~~~

在本地 .env 的 DEEPSEEK_API_KEY 后填写自己的 Key，或用交互输入：

~~~powershell
.\.venv\Scripts\python.exe -B -m app.cli --configure
.\.venv\Scripts\python.exe -B -m app.cli
~~~

Key 只保存在本地。配置不上传仓库，不把 Key 放进命令参数或共享文档。
--check 仅检查配置是否存在，不代表认证、额度或服务已验证。

## 常用命令

在项目根目录运行：

~~~powershell
.\.venv\Scripts\python.exe -B -m app.cli --offline
.\.venv\Scripts\python.exe -B -m app.cli --draft-demo
.\.venv\Scripts\python.exe -B -m app.cli --context-demo
.\.venv\Scripts\python.exe -B -m app.cli --archive-demo
.\.venv\Scripts\python.exe -B -m app.evaluation
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider
.\.venv\Scripts\python.exe -B -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
~~~

API 文档：http://127.0.0.1:8000/docs。已有服务时不用重复启动。
Windows 也可用 .\dev.ps1 -Mode demo / chat / api / test / eval / archive-demo / check / setup。
若 PowerShell 限制执行脚本，直接使用上面的 Python 命令。

macOS/Linux 对应使用 python3 创建虚拟环境，并将解释器路径替换成 .venv/bin/python。
本轮未在 macOS/Linux 上验证。

## 聊天中的操作

- /new、/sessions、/use 编号前缀：新建、查看与切换会话。
- /history、/status、/context、/events：查看历史与运行元数据。
- /demo、/confirm、/cancel：演示流程的等待、确认与取消。
- /draft-new 标题、/draft-edit 标题、/draft-confirm、/draft-reject：通用草稿操作。
- /save、/archives、/restore 编号前缀：主动保存、列出和恢复。
- /save 存档版本：更新快照；/archive-delete 编号前缀 存档版本：删除快照。
- /clear 清空当前内存，磁盘存档保留；/end 结束；/exit 退出。

完整命令见 /help。修改代码后需重新打开终端聊天。

## 路径与个人配置

| 内容 | 默认位置 |
|---|---|
| API Key 与模型配置 | 项目根目录 .env |
| 评测案例 | evaluation/cases/runtime_v1.json |
| 评测报告 | 项目根目录 reports/ |
| 主动保存的会话 | data/session-archives.sqlite3 |
| 团队说明 | docs/ |

以上位置随项目移动。会话默认内存，只有主动保存才写入数据库。
启动或只列出空存档不创建数据库。恢复不重放旧请求，不恢复旧确认凭据。
当前接口用于本机单用户开发，尚未实现多用户身份认证；本地存档为明文文件。

需要把报告放入自己的笔记目录时，复制 local.paths.example.json 为 local.paths.json，
设置 evaluation_output_dir 为个人路径。相对路径以项目根目录为基准。
local.paths.json 已被 Git 忽略，不会把个人路径带给队友。
harness_note 仅供本机开发者定位原始研究笔记，程序不执行其中内容。

报告路径优先级：命令 --output > local.paths.json > 项目 reports/。

~~~powershell
.\.venv\Scripts\python.exe -B -m app.evaluation --output ./reports
~~~

离线评测不读取 .env，不访问模型服务。仓库忽略 .env、.venv、个人路径文件、报告和本地数据库。
默认本机笔记配置不会随克隆传播。

## 项目说明

docs/ 是随代码共享的阅读快照；项目负责人的 Obsidian 原稿继续保留。
更新文档时同步相关共享文件，不默认发布个人笔记或本地评测产物。

- [运行契约](docs/runtime-contract.md)
- [Harness 迁移原则](docs/harness-transfer.md)
- [模块进度与开发步骤](docs/development.md)
- [草稿版本管理](docs/草稿版本管理.md)
- [上下文来源](docs/上下文组装与来源记录.md)
- [离线评测](docs/批量评测运行器.md)
- [会话保存恢复](docs/会话保存与恢复.md)
- [开发约定](AGENTS.md)
- [心理模块接口草案与 JSON 示例](docs/psychology-interface.md)
