# AGENT.md

## Purpose
This agent provides an example pattern for model download and offline-ready
setup for a new repo.

Do not customize this example directory for each project. Instead, copy its
logic into the target repository and create or update that repository's files.

## Responsibilities
- Provide a `download_models.py` that:
  - Downloads required model repos/files.
  - Writes a `model_paths.env` with all needed exports.
- Provide an `install.sh` that:
  - Creates/activates the conda environment.
  - Installs PyTorch + repo requirements.
  - Installs PyTorch3D from source when required (same pattern as sam-3d-objects).
  - Runs model downloads unless explicitly skipped.
- Update `README.md` with an **HPC Cluster Environment** section.

These outputs belong in the target repository, not in `model-download-agent/`.

## File Layout (Important)
For this example template, these files are kept in the same directory:
- `AGENT.md`
- `README.md`
- `install.sh`
- `download_models.py`
- `requirements.txt`

`install.sh` assumes `download_models.py` and `requirements.txt` are next to it and
resolves paths via:
- `PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"`
- `python "${PROJECT_ROOT}/download_models.py" ...`
- `python -m pip install -r "${PROJECT_ROOT}/requirements.txt"`

When copying this pattern to a new repo, keep the same co-located layout unless
you also update all path logic in `install.sh`.

## Workflow (High-Level)
1) Configure env names/versions at the top of `install.sh`.
2) Run `install.sh` on a login node (with internet) for base env + models.
3) Source `model_paths.env` before running jobs.
4) For PyTorch3D source builds, run `INSTALL_PYTORCH3D=1 ./install.sh` on a
   CUDA-capable machine with `nvcc` available (or load a CUDA module).
5) On compute nodes, optionally re-run `download_models.py` if network is available.

## How to Use This Agent for a New Repo
When you need model download support for a different repo, use this directory as
the reference template and implement the resulting files in the target repo.

### Required Updates (Always)
- **download_models.py**
  - Create this file in the target repository.
  - Replace `REQUIRED_REPOS` with the target repo's actual model repos.
  - Replace `DIRECT_DOWNLOADS` with any non-HF weights listed in the README.
  - Ensure `model_paths.env` exports match the target repo's expected variables.
  - Keep this file beside `install.sh` unless you also change `PROJECT_ROOT` usage.
- **install.sh**
  - Create this file in the target repository.
  - Match Python/PyTorch/CUDA versions from the target README.
  - Install all Python dependencies listed in the README.
  - If PyTorch3D is required, keep source-build flow and CUDA checks.
  - Keep this file beside `download_models.py` and `requirements.txt`.
- **README.md**
  - Update the target repository README, not this example README.
  - Keep the **HPC Cluster Environment** section, but change paths/examples to
    the target repo name.
  - Document whether compute nodes may re-download models or must be offline.

### PyTorch3D Step (Expanded Guidance)
When `INSTALL_PYTORCH3D=1`:
- `install.sh` installs PyTorch3D from Git source (`pytorch3d.git`), not from a
  prebuilt wheel.
- It compiles extensions locally on the current machine, so CUDA toolchain must
  be available there.
- If `nvcc` is missing and module system is available, it tries modules listed in
  `CUDA_MODULES_CANDIDATES`.
- If no `nvcc` is found after that, installation fails fast with guidance.

Recommended usage on HPC:
1) Login node: run `./install.sh` for env + base dependencies.
2) GPU compute node: run `INSTALL_PYTORCH3D=1 SKIP_DOWNLOADS=1 ./install.sh`.

Optional knobs:
- `PYTORCH3D_REF` to pin branch/tag/commit.
- `TORCH_CUDA_ARCH_LIST` for your target GPU architecture.
- `CUDA_MODULES_CANDIDATES` to override module names for your cluster.

### Optional Updates
- Add extra cache envs (e.g., `TORCH_HOME`, `OPENCLIP_CACHE_DIR`) if the target
  repo expects them.
- Add symlink steps if the target code assumes fixed checkpoint locations.
  Use the target README as the source of truth.

### Definition of Done
- `download_models.py` runs end-to-end and writes `model_paths.env`.
- `install.sh` in the target repo finishes without manual steps on a login node.
- If enabled, PyTorch3D builds from source on a CUDA-capable node.
- The target repo README still reads correctly with the new HPC section added.

## Notes
- Keep `model_paths.env` as the single source of truth for model locations.
- If a model is gated on HF, require `HF_TOKEN`/`HUGGINGFACE_HUB_TOKEN`.
