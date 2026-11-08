# 腾讯云产品服务部署准备

## 当前状态与资源建议

目前没有运行本项目后端的服务器，也没有配置模型 Key；[qsinghua.lingozm.cn](https://qsinghua.lingozm.cn/) 仍是 EdgeOne 静态演示。仓库交付了部署文件，尚未完成实际服务器部署或真实供应商联调。本机没有 Docker，不能据此声称容器已构建或运行成功。

小规模试用可考虑腾讯云香港地域轻量应用服务器 Lighthouse，Ubuntu 24.04、2 CPU / 4 GB 内存，运行单机 Next + Python + Caddy。这里是起步资源建议，未核算报价，也没有购买授权；容量应按实际模型等待时间、并发和监控结果调整。产品与可用地域信息以 [腾讯云 Lighthouse 官方页面](https://intl.cloud.tencent.com/zh/products/lighthouse?lang=zh) 为准。域名注册在 Gname，服务器和域名不必在同一服务商。

## 部署文件与链路

| 文件 | 作用 |
|---|---|
| `deploy/compose.yaml` | API、Next 与 Caddy 三个服务及持久化卷 |
| `deploy/Dockerfile.api` | Python 3.12，产品 API，一个 worker，非 root 运行 |
| `deploy/Dockerfile.web` | Node.js 22，Next standalone 生产构建，非 root 运行 |
| `deploy/Caddyfile` | 同域 HTTPS、`/api/*` 转发与前端转发 |
| `deploy/.env.server.example` | 服务端模型配置模板，不含凭据 |

浏览器经 Caddy 访问同一个 HTTPS 域名：`/api/*` 走产品 API，其他页面走 Next。只有 Caddy 映射公网 80/443，Python 与 Next 不单独映射公网端口。不要把原 `app.main:app` 挂到这个代理上。Next 部署模式见 [Next.js 官方文档](https://nextjs.org/docs/app/getting-started/deploying)，Caddy 反代与自动 HTTPS 模式见 [Caddy 官方文档](https://caddyserver.com/docs/caddyfile/patterns)。

## 准备服务器

先准备已获授权的服务器、固定公网 IPv4 和 SSH 登录方式，安装 Docker Engine 与 Compose 插件。安全组和主机防火墙允许公网 80/443；SSH 仅允许管理来源。此处不创建实例、不购买套餐，也不变更当前 DNS。

将仓库放在服务器的专用目录，例如 `/opt/lingyv`。在仓库根目录执行下列准备命令；已有私有配置时不要覆盖。

```bash
cp deploy/.env.server.example deploy/.env.server
chmod 600 deploy/.env.server
```

通过服务器上的编辑器填写 `DEEPSEEK_API_KEY`。私有文件不提交 GitHub，也不要把 Key 放在命令参数、前端变量或截图中。模板保留 `LLM_MAX_TOKENS=1800`，以容纳支持回复和四字段；存在 Key 不等于供应商已验证。

Compose 设定 `PRODUCT_COOKIE_SECURE=true`、正式 HTTPS `PRODUCT_ORIGIN`、`PRODUCT_DATA_DIR=/data` 和单 worker。不要增加 API worker 或多副本：当前旅程与设备状态仍为进程内数据。

## 先验证，再切换正式域名

建议先用另行获准的临时测试子域名指向新服务器，以完成完整 HTTPS 验证，同时保留当前正式站。下方的 `preview.example.com` 是占位符，执行前替换为实际可控测试域名。

```bash
PUBLIC_DOMAIN=preview.example.com docker compose -f deploy/compose.yaml config --quiet
PUBLIC_DOMAIN=preview.example.com docker compose -f deploy/compose.yaml up -d --build
PUBLIC_DOMAIN=preview.example.com docker compose -f deploy/compose.yaml ps
```

`PUBLIC_DOMAIN` 同时决定 Caddy 域名、Cookie 对应的正式来源和同源 API 地址。域名解析、80/443 可达及证书签发成功后，再验证：

1. HTTPS 页面与 `/api/support/health` 可用；API/Next 内部端口没有映射到公网。
2. 用虚构数据注册登录，确认会话 Cookie 和跨用户隔离；原工程全局列表/存档接口没有暴露。
3. 使用已配置的真实 Key，显式同意一次模型发送，完成四字段生成 → 用户纠正 → 当前版本确认 → Keep/Release/Next → 主动保存经历卡。
4. 登录后回看卡片，验证未来参考和当轮参考分别生效；撤回或删除后旧对话不再引用该卡片，Release 文本不被保留。
5. 重启服务后账号及主动保存卡片仍可读取，对话/设备状态按设计消失；检查恢复、删除及备份流程。

没有真实 Key 时，第 3 项仍是待完成，不能用注入模型测试标记通过。临时域名验证也不能替代正式域名切换后的 HTTPS 复验。

完成上述准备后，才在 Gname 修改正式子域名：主机记录 `qsinghua`、类型 `A`、值为新服务器公网 IPv4。当前同名 CNAME 与 A 记录不能并存，变更前记录原 CNAME 值与 TTL，保留回退信息；主域名 `lingozm.cn` 不需要随之改动。新服务器以 `PUBLIC_DOMAIN=qsinghua.lingozm.cn` 启动，确认解析传播、Caddy 证书、登录和完整产品流程。此步骤会切换现有官网，必须在服务器就绪后实施。

```bash
PUBLIC_DOMAIN=qsinghua.lingozm.cn docker compose -f deploy/compose.yaml up -d --build
```

若切换验证失败，按先前记录恢复 CNAME 并排查服务器；DNS 回退受缓存影响，不保证立即恢复。不要删除旧静态站，直到新服务完成验收。

## 数据与运维边界

`product-data` 卷保存账号与主动经历卡，`caddy-data` 保存证书状态。常规更新保留卷；`docker compose down -v` 会删除卷，不是日常更新命令。备份应在数据库一致状态下完成，并限制主机与备份访问权限；SQLite 卡片为明文，不是端到端加密。

退出、删卡、删账号与重启的数据行为见 [产品闭环说明](product-loop.md)。上线前还需完成实际日志审查、备份恢复、告警、容量测试和未成年人隐私/专业审核；目前没有邮箱恢复及成熟的正式运维保障。以上部署步骤为交付方案，执行结果应在实际环境单独记录。
