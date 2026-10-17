# CI/CD 与生产部署

## 流程

- PR 和 `main` / `develop` 推送会检查三个后端服务、前端构建及三个容器镜像。
- `main` 的 CI 成功后会发布带提交 SHA 的 app、parser、knowledge 镜像。
- 生产 CD 不提供绕过 CI 的手动触发入口；需要重试时应重新运行原 CD 作业。
- 生产部署先备份 PostgreSQL，再执行 `alembic upgrade head`，最后启动同一 SHA 的三个服务并进行健康检查。
- 生产服务器需要保留 `/opt/resume-assistant/.env`；每次成功部署使用的镜像版本记录在同目录的 `.deploy.env`。

## GitHub production Environment

CD 的部署作业绑定 `production` Environment。请在仓库的
Settings → Environments → production 中完成以下设置：

1. 将允许部署的分支限制为 `main`。
2. 配置 Required reviewers，并关闭发起人自行批准。
3. 配置或确认 `DEPLOY_HOST`、`DEPLOY_USER`、`DEPLOY_SSH_KEY` 三个 Secrets。

Environment 审批完成前，部署作业不能读取生产密钥或连接生产服务器。

## 数据库迁移与回滚

- 表结构统一由 Alembic 管理，部署时执行 `alembic upgrade head`。
- 每次迁移前都会在服务器的 `/opt/resume-assistant/backups/` 下生成 PostgreSQL 压缩备份。
- 健康检查失败时，CD 自动切回上一个镜像 SHA；数据库不自动降级，破坏性迁移必须拆成兼容的多阶段发布。
