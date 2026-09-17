#!/usr/bin/env python3
"""Stage model weights onto COS.

Downloads a manifest of model repos from ModelScope (preferred inside CN
networks) with Hugging Face as fallback, then uploads them under a COS prefix
so the bucket can be mounted as a model cache (xpark ``MODEL_CACHE_EXTRA_DIRS``
style). Credentials come from the standard COS_* environment variables (see
example.env next to this script):

    COS_SECRET_ID / COS_SECRET_KEY / COS_BUCKET / COS_REGION [/ COS_ENDPOINT]

Key conventions:

- The manifest is a json file with a ``models`` list (auto-downloadable
  entries; only ``repo_id`` is required) and an optional ``manual`` list
  (assets that cannot be fetched automatically — printed, never fetched).
  The ``manifest.json`` next to this script is the default; pass
  ``--manifest other.json`` to stage a different list.
- The on-COS directory of an entry defaults to the model id with "/" -> "_"
  (the xpark model-cache naming convention).
- Gated repos (e.g. facebook/sam3) are Hugging Face only and need ``HF_TOKEN``;
  they are skipped unless ``--include-gated`` is given.

Usage:
    cp example.env .env  # fill in your COS credentials, then:
    python stage_models.py --env-file .env                              # default manifest.json
    python stage_models.py --env-file .env --dry-run                    # plan only
    python stage_models.py --env-file .env --manifest my.json --prefix team/models
    python stage_models.py --env-file .env --only Ultralytics_YOLO11    # subset
    python stage_models.py --env-file .env --include-gated              # needs HF_TOKEN

Dependencies: pip install "modelscope" "huggingface_hub" "cos-python-sdk-v5"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

#: Refuse buckets that look like shared CI/baseline data: staging into them
#: would poison the read-only reference data.
FORBIDDEN_BUCKET_MARKERS = ("xpark-cache", "xpark_cache")

#: Default local scratch dir (override with --workdir).
DEFAULT_WORKDIR = Path.home() / ".cache" / "xpark-toolkit" / "staging"

#: Default manifest: the json shipped next to this script.
DEFAULT_MANIFEST_PATH = Path(__file__).resolve().parent / "manifest.json"


@dataclass(frozen=True)
class ManifestEntry:
    """One auto-downloadable model."""

    cache_name: str  # on-COS directory; convention: model id with "/" -> "_"
    repo_id: str  # Hugging Face repo id
    files: tuple[str, ...] | None  # None = whole snapshot
    gated: bool
    note: str
    #: ModelScope repo tried first: "" = same id as repo_id, None = HF only
    #: (gated repos have no ModelScope mirror).
    ms_repo_id: str | None = ""

    @classmethod
    def from_dict(cls, data: dict) -> "ManifestEntry":
        """Build an entry from a manifest-json item.

        ``cache_name`` and ``ms_repo_id`` are optional; the former defaults to
        the model id with "/" -> "_", the latter to "" (try ModelScope with the
        same id, then fall back to Hugging Face).
        """
        repo_id = data["repo_id"]
        files = data.get("files")
        return cls(
            cache_name=data.get("cache_name") or repo_id.replace("/", "_"),
            repo_id=repo_id,
            files=tuple(files) if files else None,
            gated=bool(data.get("gated", False)),
            note=data.get("note", ""),
            ms_repo_id=data.get("ms_repo_id", ""),
        )


def load_env_file(path: Path) -> list[str]:
    """Load KEY=VALUE lines into os.environ (existing env wins, like dotenv).

    Returns the keys that were applied.
    """
    applied: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value
            applied.append(key)
    return applied


def load_manifest(path: Path) -> tuple[list[ManifestEntry], list[tuple[str, str]]]:
    """Load a manifest json file.

    Accepted shape::

        {"models": [ {"repo_id": ...}, ... ],
         "manual": [ {"name": ..., "note": ...}, ... ]}   # optional

    Returns ``(entries, manual_notes)``; the manual part holds assets that
    cannot be fetched automatically (printed, never downloaded).
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
        raise ValueError("manifest must be an object with a 'models' list")
    entries = [ManifestEntry.from_dict(item) for item in data["models"]]
    if not entries:
        raise ValueError("manifest has an empty 'models' list")
    manual = [(item["name"], item.get("note", "")) for item in data.get("manual", [])]
    return entries, manual


def select_entries(
    manifest, only: list[str] | None, include_gated: bool
) -> list[ManifestEntry]:
    selected = []
    for entry in manifest:
        if entry.gated and not include_gated:
            continue
        if only and not any(
            pattern in entry.cache_name or pattern in entry.repo_id for pattern in only
        ):
            continue
        selected.append(entry)
    return selected


def _download_modelscope(
    repo_id: str, files: tuple[str, ...] | None, local: Path
) -> None:
    """Download via ModelScope (preferred inside CN networks)."""
    from modelscope import snapshot_download as ms_snapshot_download

    print(f"  modelscope snapshot_download {repo_id} -> {local}")
    ms_snapshot_download(
        repo_id,
        local_dir=str(local),
        allow_patterns=list(files) if files else None,
    )


def _download_huggingface(
    repo_id: str, files: tuple[str, ...] | None, local: Path
) -> None:
    """Download via Hugging Face Hub."""
    from huggingface_hub import hf_hub_download, snapshot_download

    if files:
        for filename in files:
            print(f"  hf_hub_download {repo_id}/{filename} -> {local}")
            hf_hub_download(repo_id=repo_id, filename=filename, local_dir=str(local))
    else:
        print(f"  hf snapshot_download {repo_id} -> {local}")
        snapshot_download(repo_id=repo_id, local_dir=str(local))


def download_entry(entry: ManifestEntry, workdir: Path) -> tuple[Path, str]:
    """Download one manifest entry into ``workdir/<cache_name>``.

    Order: ModelScope first (when eligible), falling back to Hugging Face when
    the ModelScope repo is missing or unreachable. Returns ``(local_dir,
    source)``.
    """
    local = workdir / entry.cache_name
    local.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    if entry.ms_repo_id is not None:
        ms_repo = entry.ms_repo_id or entry.repo_id
        try:
            _download_modelscope(ms_repo, entry.files, local)
            return local, "modelscope"
        except Exception as exc:  # noqa: BLE001 - fall through to Hugging Face
            errors.append(f"modelscope({ms_repo}): {exc}")
            print(f"  modelscope unavailable, falling back to huggingface: {exc}")

    try:
        _download_huggingface(entry.repo_id, entry.files, local)
        return local, "huggingface"
    except Exception as exc:  # noqa: BLE001 - reported to the caller
        errors.append(f"huggingface({entry.repo_id}): {exc}")
        raise RuntimeError("; ".join(errors)) from exc


def cos_endpoint() -> str | None:
    """Normalized COS endpoint.

    ``CosConfig(Endpoint=...)`` wants a host, not a URL: it builds
    ``<bucket>.<endpoint>`` internally, so a full ``https://...`` value yields a
    broken host like ``bucket.https``. Accept both and strip the scheme/path.
    """
    raw = os.environ.get("COS_ENDPOINT", "").strip()
    if not raw:
        return None
    host = urlparse(raw if "//" in raw else f"//{raw}").hostname
    return host or None


def build_cos_client():
    from qcloud_cos import CosConfig, CosS3Client

    config = CosConfig(
        Region=os.environ["COS_REGION"],
        SecretId=os.environ["COS_SECRET_ID"],
        SecretKey=os.environ["COS_SECRET_KEY"],
        Endpoint=cos_endpoint(),
    )
    return CosS3Client(config)


def upload_dir(client, bucket: str, prefix: str, name: str, local: Path) -> int:
    """Recursively upload ``local`` under ``<prefix>/<name>/``; returns file count."""
    count = 0
    for file in sorted(p for p in local.rglob("*") if p.is_file()):
        key = f"{prefix}/{name}/{file.relative_to(local).as_posix()}"
        print(f"  cos upload s3://{bucket}/{key} ({file.stat().st_size / 1e6:.1f} MB)")
        client.upload_file(Bucket=bucket, Key=key, LocalFilePath=str(file))
        count += 1
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="env file with COS_* variables (see example.env); defaults to the ambient environment",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help=f"manifest json (default: {DEFAULT_MANIFEST_PATH.name} next to this script)",
    )
    parser.add_argument(
        "--prefix",
        default="models",
        help="COS prefix to stage under (default: %(default)s)",
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        default=DEFAULT_WORKDIR,
        help="local download scratch dir (default: %(default)s)",
    )
    parser.add_argument(
        "--only", nargs="*", help="substring filters on cache_name / repo_id"
    )
    parser.add_argument(
        "--include-gated",
        action="store_true",
        help="also fetch gated repos (needs HF_TOKEN)",
    )
    parser.add_argument(
        "--skip-upload", action="store_true", help="download only, do not touch COS"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print the plan and exit"
    )
    args = parser.parse_args(argv)

    if args.env_file is not None:
        if not args.env_file.is_file():
            print(
                f"error: env file {args.env_file} not found (copy example.env and fill it in)",
                file=sys.stderr,
            )
            return 2
        applied = load_env_file(args.env_file)
        print(
            f"loaded env from {args.env_file}: {', '.join(applied) or '(all already set)'}"
        )
    else:
        print("no --env-file given, relying on the ambient environment")

    manifest_path = args.manifest or DEFAULT_MANIFEST_PATH
    if not manifest_path.is_file():
        print(
            f"error: manifest {manifest_path} not found; pass --manifest <file> or provide {DEFAULT_MANIFEST_PATH.name} "
            "next to this script",
            file=sys.stderr,
        )
        return 2
    try:
        manifest, manual_notes = load_manifest(manifest_path)
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: invalid manifest {manifest_path}: {exc}", file=sys.stderr)
        return 2
    print(
        f"loaded manifest {manifest_path}: {len(manifest)} entries, {len(manual_notes)} manual"
    )

    required = ("COS_SECRET_ID", "COS_SECRET_KEY", "COS_BUCKET", "COS_REGION")
    if not args.skip_upload and not args.dry_run:
        missing = [k for k in required if not os.environ.get(k)]
        if missing:
            print(f"error: missing COS env: {', '.join(missing)}", file=sys.stderr)
            return 2

    bucket = os.environ.get("COS_BUCKET", "") or "<unset>"
    if any(marker in bucket for marker in FORBIDDEN_BUCKET_MARKERS):
        print(
            f"error: refusing to stage into the CI/baseline bucket {bucket!r}; "
            "set COS_BUCKET to the models bucket instead.",
            file=sys.stderr,
        )
        return 2

    selected = select_entries(manifest, args.only, args.include_gated)
    print(
        f"\nplan: {len(selected)} auto-downloadable entr{'y' if len(selected) == 1 else 'ies'}"
    )
    for entry in selected:
        scope = "files=" + ",".join(entry.files) if entry.files else "full snapshot"
        source = (
            "modelscope -> huggingface"
            if entry.ms_repo_id is not None
            else "huggingface only"
        )
        print(
            f"  - {entry.repo_id} ({scope}, {source}) -> s3://{bucket}/{args.prefix}/{entry.cache_name}/ [{entry.note}]"
        )

    if manual_notes:
        print(f"\nmanual (not auto-downloadable): {len(manual_notes)}")
        for name, note in manual_notes:
            print(f"  - {name}: {note}")

    if args.dry_run:
        print("\n(dry run: nothing downloaded or uploaded)")
        return 0

    uploaded = 0
    for entry in selected:
        print(f"\n== {entry.repo_id} ==")
        try:
            local, source = download_entry(entry, args.workdir)
            print(f"  downloaded via {source}")
        except Exception as exc:  # noqa: BLE001 - keep the batch alive, report at exit
            print(f"  download FAILED: {exc}", file=sys.stderr)
            continue
        if not args.skip_upload:
            uploaded += upload_dir(
                build_cos_client(), bucket, args.prefix, entry.cache_name, local
            )

    print(
        f"\ndone: staged uploads this run = {uploaded} files under s3://{bucket}/{args.prefix}/"
    )
    if manual_notes and not args.skip_upload:
        print("reminder: manual entries above still need one-off staging by hand.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
