# xpark-toolkit

**English** | [中文](#xpark-toolkit中文)

Operational tooling for xpark data pipelines: provisioning, diagnostics and maintenance for clusters, model caches and object storage.

Each directory is a functional area with its own README covering usage details.

| Directory | Purpose |
|---|---|
| [`provisioning/`](provisioning/README.md) | Stage external assets — model weights, datasets, compiled artifacts — into object storage / shared mounts. |
| [`diagnostics/`](diagnostics/README.md) | Inspect and verify environments: cache reconciliation, mount health, coverage reports. |
| [`maintenance/`](maintenance/README.md) | Housekeeping: cache cleanup, artifact migration, bucket inventory. |

---

# xpark-toolkit(中文)

[English](#xpark-toolkit) | **中文**

围绕 xpark 数据管线的运维工具集:面向集群、模型缓存与对象存储的置备、诊断与维护。

每个目录是一个功能域,具体工具的使用细节见各自的 README。

| 目录 | 功能定位 |
|---|---|
| [`provisioning/`](provisioning/README.md) | 置备外部资产(模型权重、数据集、编译产物)到对象存储 / 共享挂载。 |
| [`diagnostics/`](diagnostics/README.md) | 检查与校验环境:缓存对账、挂载健康、覆盖报告。 |
| [`maintenance/`](maintenance/README.md) | 日常维护:缓存清理、产物迁移、桶清单。 |
