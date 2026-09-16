# provisioning

**English** | [中文](#provisioning中文)

Stage external assets — model weights, datasets, compiled artifacts — into COS so the bucket can be mounted as a model cache (xpark `MODEL_CACHE_EXTRA_DIRS` style).

## Files

| File | Purpose |
|---|---|
| `stage_models.py` | Download a manifest of model repos and upload them under a COS prefix. |
| `manifest.json` | Default manifest: auto-downloadable `models` + not-fetchable `manual` assets. |
| `example.env` | COS credential template — copy to `.env` and fill in; never commit real secrets. |

## Usage

Download order is ModelScope first (preferred inside CN networks), Hugging Face as fallback; gated repos need `HF_TOKEN` and `--include-gated`.

```bash
cp example.env .env   # fill in your credentials
python stage_models.py --env-file .env --dry-run                    # plan only
python stage_models.py --env-file .env                              # default manifest.json
python stage_models.py --env-file .env --manifest my.json --prefix team/models
python stage_models.py --env-file .env --only Ultralytics_YOLO11    # subset
```

Key options: `--manifest` (default: `manifest.json` next to the script), `--prefix` (COS prefix, default `models`), `--workdir` (local scratch, default `~/.cache/xpark-toolkit/staging`), `--include-gated`, `--skip-upload`, `--dry-run`.

Manifest format (only `repo_id` is required; `cache_name` defaults to the repo id with "/" -> "_"):

```json
{"models": [{"repo_id": "...", "files": ["..."], "gated": false, "ms_repo_id": "", "note": "..."}],
 "manual":  [{"name": "...", "note": "..."}]}
```

## Full staging

Stage in batches (approximate sizes for the default manifest) to keep each run bounded:

```bash
python stage_models.py --env-file .env --only Ultralytics            # ~100 MB (yolo11n/s/m)
python stage_models.py --env-file .env --only WiLoR                  # ~1 GB
python stage_models.py --env-file .env --only Video-Depth-Anything   # ~2 GB
python stage_models.py --env-file .env --include-gated --only sam3   # needs HF_TOKEN
```

## Manual assets

`manual` entries cannot be fetched automatically. Obtain them per the table below, then upload to `<prefix>/` with [coscli](https://www.tencentcloud.com/zh/document/product/436/43249) (Tencent Cloud COS CLI — download & install) or any other COS tool.

| Asset | How to obtain | Target |
|---|---|---|
| `MANO_RIGHT.pkl` | Register at <https://mano.is.tue.mpg.com> (non-commercial, no redistribution). | `models/MANO_RIGHT.pkl` (cache root) |
| `SMPLX_NEUTRAL.pkl` | Register at <https://smpl-x.is.tue.mpg.com>. | `models/SMPLX_NEUTRAL.pkl` (cache root) |
| DeepCalib `weights_10_0.02.h5` | From the authors (no license declaration, no HF release). | `models/alexvbogdan_DeepCalib/` |
| VINS-Adapter | Community adapter (GPL-3.0): `https://github.com/xpark-community/vins-adapter/releases/download/v0.1.0/vins_adapter-linux-x86_64.tar.gz` | `models/vins_adapter/` (extracted) + the tarball |
| CREStereo `crestereo.pth` | <https://github.com/megvii-research/CREStereo> pretrained (no HF release). | `models/crestereo.pth` |
| RAFT-Stereo `.pth` | <https://github.com/princeton-vl/RAFT-Stereo> releases (per-scene). | `models/raft_stereo_<scene>.pth` |
| URDF robot descriptions | Per-robot asset; pass directly to the operator (local path or `cos://`/`s3://` URI), no staging needed. | — |

```bash
coscli upload MANO_RIGHT.pkl cos://<bucket>/models/
wget https://github.com/xpark-community/vins-adapter/releases/download/v0.1.0/vins_adapter-linux-x86_64.tar.gz
coscli upload vins_adapter-linux-x86_64.tar.gz cos://<bucket>/models/
```

## Conventions

- Credentials from environment variables only — never hard-coded.
- CI/baseline buckets hold read-only reference data; tools refuse to write to them.
- Anything that mutates remote state offers `--dry-run`.

---

# provisioning(中文)

[English](#provisioning) | **中文**

置备外部资产(模型权重、数据集、编译产物)到 COS,使桶可作为模型缓存挂载(xpark `MODEL_CACHE_EXTRA_DIRS` 方式)。

## 文件

| 文件 | 用途 |
|---|---|
| `stage_models.py` | 按清单下载模型并上传到 COS 前缀下。 |
| `manifest.json` | 默认清单:可自动下载的 `models` + 不可自动获取的 `manual` 资产。 |
| `example.env` | COS 凭证模板——复制为 `.env` 填写,切勿提交真实密钥。 |

## 用法

下载顺序:ModelScope 优先(国内网络),Hugging Face 兜底;gated 仓库需 `HF_TOKEN` 且加 `--include-gated`。

```bash
cp example.env .env   # 填入凭证
python stage_models.py --env-file .env --dry-run                    # 只看计划
python stage_models.py --env-file .env                              # 默认 manifest.json
python stage_models.py --env-file .env --manifest my.json --prefix team/models
python stage_models.py --env-file .env --only Ultralytics_YOLO11    # 子集
```

主要参数:`--manifest`(默认同目录 `manifest.json`)、`--prefix`(COS 前缀,默认 `models`)、`--workdir`(本地暂存,默认 `~/.cache/xpark-toolkit/staging`)、`--include-gated`、`--skip-upload`、`--dry-run`。

清单格式(仅 `repo_id` 必填;`cache_name` 缺省为 repo id 的 `/`→`_`):

```json
{"models": [{"repo_id": "...", "files": ["..."], "gated": false, "ms_repo_id": "", "note": "..."}],
 "manual":  [{"name": "...", "note": "..."}]}
```

## 全量置备

建议分批置备(括号内为默认清单的体量参考),避免单次传输过大:

```bash
python stage_models.py --env-file .env --only Ultralytics            # 约 100 MB(yolo11n/s/m)
python stage_models.py --env-file .env --only WiLoR                  # 约 1 GB
python stage_models.py --env-file .env --only Video-Depth-Anything   # 约 2 GB
python stage_models.py --env-file .env --include-gated --only sam3   # 需 HF_TOKEN
```

## 不可自动获取资产的制备

`manual` 条目无法自动下载,按下表获取后用 [coscli](https://www.tencentcloud.com/zh/document/product/436/43249)(腾讯云 COS 命令行工具,下载与安装见此文档)或任意 COS 工具上传到 `<prefix>/` 下。

| 资产 | 获取方式 | 落点 |
|---|---|---|
| `MANO_RIGHT.pkl` | <https://mano.is.tue.mpg.com> 注册下载(非商业、禁再分发)。 | `models/MANO_RIGHT.pkl`(缓存根) |
| `SMPLX_NEUTRAL.pkl` | <https://smpl-x.is.tue.mpg.com> 注册下载。 | `models/SMPLX_NEUTRAL.pkl`(缓存根) |
| DeepCalib `weights_10_0.02.h5` | 从作者处获取(无许可声明、无 HF 发布)。 | `models/alexvbogdan_DeepCalib/` |
| VINS-Adapter | 官方 release(GPL-3.0):`https://github.com/xpark-community/vins-adapter/releases/download/v0.1.0/vins_adapter-linux-x86_64.tar.gz` | `models/vins_adapter/`(解包)+ tarball |
| CREStereo `crestereo.pth` | <https://github.com/megvii-research/CREStereo> pretrained(无 HF 发布)。 | `models/crestereo.pth` |
| RAFT-Stereo `.pth` | <https://github.com/princeton-vl/RAFT-Stereo> releases 按场景下载。 | `models/raft_stereo_<scene>.pth` |
| URDF 机器人描述 | 按机器人获取;直接传算子路径(本地路径或 `cos://`/`s3://` URI),无需置备。 | — |

```bash
coscli upload MANO_RIGHT.pkl cos://<bucket>/models/
wget https://github.com/xpark-community/vins-adapter/releases/download/v0.1.0/vins_adapter-linux-x86_64.tar.gz
coscli upload vins_adapter-linux-x86_64.tar.gz cos://<bucket>/models/
```

## 约定

- 凭证仅从环境变量读取,绝不硬编码。
- CI/基准桶为只读参照数据,工具拒绝写入。
- 改动远端状态的操作提供 `--dry-run`。
