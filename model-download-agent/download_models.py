#!/usr/bin/env python3
"""
Example model downloader for offline-friendly runs.

Run on a node with internet access. It writes model_paths.env with the
resulting paths so the compute node can run offline.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Optional
from urllib.request import urlretrieve

from huggingface_hub import snapshot_download


REQUIRED_REPOS = [
    "black-forest-labs/FLUX.1-dev",
    "openai/clip-vit-base-patch16",
]

DIRECT_DOWNLOADS = [
    {
        "name": "example_weights",
        "url": "https://download.pytorch.org/models/alexnet-owt-7be5be79.pth",
        "relative_path": Path("direct") / "alexnet-owt-7be5be79.pth",
    },
]


def _snapshot(repo_id: str, dest: Path, token: Optional[str]) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    print(f"downloading: {repo_id} -> {dest}")
    snapshot_download(
        repo_id=repo_id,
        local_dir=str(dest),
        local_dir_use_symlinks=False,
        token=token,
        resume_download=True,
    )


def _download_file(url: str, target: Path, force: bool) -> None:
    if target.exists() and not force:
        print(f"exists: {target}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading: {url} -> {target}")
    urlretrieve(url, target)


def _write_env(env_path: Path, models_dir: Path, cache_dir: Path) -> None:
    lines = [
        f"export PROJECT_MODELS_DIR={models_dir}",
        f"export HF_HOME={cache_dir}",
        f"export TRANSFORMERS_CACHE={cache_dir}",
    ]
    for repo_id in REQUIRED_REPOS:
        name = repo_id.split("/")[-1].upper().replace("-", "_").replace(".", "_")
        lines.append(f"export MODEL_{name}_DIR={models_dir / repo_id.split('/')[-1]}")
    for item in DIRECT_DOWNLOADS:
        lines.append(f"export {item['name'].upper()}_PATH={models_dir / item['relative_path']}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote: {env_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download example models and write model_paths.env")
    parser.add_argument("--models-dir", default="models", help="Directory for model repos/files")
    parser.add_argument("--cache-dir", default="cache/hf", help="HF cache directory")
    parser.add_argument("--force", action="store_true", help="Re-download direct files even if present")
    parser.add_argument("--skip-downloads", action="store_true", help="Only write model_paths.env")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    models_dir = (root / args.models_dir).resolve()
    cache_dir = (root / args.cache_dir).resolve()
    models_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")

    if not args.skip_downloads:
        for repo_id in REQUIRED_REPOS:
            dest = models_dir / repo_id.split("/")[-1]
            _snapshot(repo_id, dest, token)
        for item in DIRECT_DOWNLOADS:
            target = models_dir / item["relative_path"]
            _download_file(item["url"], target, args.force)

    env_path = root / "model_paths.env"
    _write_env(env_path, models_dir, cache_dir)


if __name__ == "__main__":
    main()
