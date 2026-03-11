#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Configurable environment
ENV_NAME="${ENV_NAME:-model-download-agent}"
PYTHON_VERSION="${PYTHON_VERSION:-3.11}"
CREATE_ENV="${CREATE_ENV:-1}"

# CUDA + PyTorch
CUDA_TOOLKIT_LABEL="${CUDA_TOOLKIT_LABEL:-cuda-12.1.0}"
INSTALL_CONDA_CUDA_TOOLKIT="${INSTALL_CONDA_CUDA_TOOLKIT:-1}"
TORCH_VERSION="${TORCH_VERSION:-2.5.1}"
TORCHVISION_VERSION="${TORCHVISION_VERSION:-0.20.1}"
TORCHAUDIO_VERSION="${TORCHAUDIO_VERSION:-2.5.1}"
TORCH_CUDA_TAG="${TORCH_CUDA_TAG:-cu121}"
SKIP_PYTORCH_INSTALL="${SKIP_PYTORCH_INSTALL:-0}"

# Optional PyTorch3D
INSTALL_PYTORCH3D="${INSTALL_PYTORCH3D:-0}"
TORCH_CUDA_ARCH_LIST="${TORCH_CUDA_ARCH_LIST:-8.0}"
PYTORCH3D_REF="${PYTORCH3D_REF:-stable}"
CUDA_MODULES_CANDIDATES="${CUDA_MODULES_CANDIDATES:-cuda/${CUDA_TOOLKIT_LABEL%%.*} ${CUDA_TOOLKIT_LABEL}}"

# Downloads
SKIP_DOWNLOADS="${SKIP_DOWNLOADS:-0}"
MODELS_DIR="${MODELS_DIR:-$PROJECT_ROOT/models}"
CACHE_DIR="${CACHE_DIR:-$PROJECT_ROOT/cache/hf}"

if command -v mamba >/dev/null 2>&1; then
  CONDA_CMD="mamba"
elif command -v conda >/dev/null 2>&1; then
  CONDA_CMD="conda"
else
  echo "conda or mamba not found. Load your conda module first." >&2
  exit 1
fi

# Enable conda shell functions
CONDA_BASE="$($CONDA_CMD info --base)"
# shellcheck disable=SC1090
source "$CONDA_BASE/etc/profile.d/conda.sh"

if [[ "$CREATE_ENV" == "1" ]]; then
  if ! $CONDA_CMD env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
    $CONDA_CMD create -y -n "$ENV_NAME" "python=$PYTHON_VERSION"
  fi
fi

set +u
conda activate "$ENV_NAME"
set -u

if [[ "$INSTALL_CONDA_CUDA_TOOLKIT" == "1" ]]; then
  $CONDA_CMD install -y -c "nvidia/label/${CUDA_TOOLKIT_LABEL}" cuda-toolkit
fi

python -m pip install --upgrade pip setuptools wheel

if [[ "$SKIP_PYTORCH_INSTALL" != "1" ]]; then
  python -m pip install \
    "torch==${TORCH_VERSION}+${TORCH_CUDA_TAG}" \
    "torchvision==${TORCHVISION_VERSION}+${TORCH_CUDA_TAG}" \
    "torchaudio==${TORCHAUDIO_VERSION}+${TORCH_CUDA_TAG}" \
    --index-url "https://download.pytorch.org/whl/${TORCH_CUDA_TAG}"
fi

python -m pip install -r "${PROJECT_ROOT}/requirements.txt"

if [[ "$INSTALL_PYTORCH3D" == "1" ]]; then
  # For source builds, make a best effort to load a CUDA module if nvcc is absent.
  if ! command -v nvcc >/dev/null 2>&1 && command -v module >/dev/null 2>&1; then
    for mod in ${CUDA_MODULES_CANDIDATES}; do
      if module load "$mod" >/dev/null 2>&1; then
        echo "Loaded CUDA module: $mod"
        break
      fi
    done
  fi

  if ! command -v nvcc >/dev/null 2>&1; then
    echo "PyTorch3D source build requires nvcc. Run on a CUDA-enabled machine or load a CUDA module." >&2
    echo "Tried CUDA_MODULES_CANDIDATES='${CUDA_MODULES_CANDIDATES}'" >&2
    exit 1
  fi

  export FORCE_CUDA=1
  export TORCH_CUDA_ARCH_LIST="${TORCH_CUDA_ARCH_LIST}"
  if command -v gcc >/dev/null 2>&1; then
    export CC="$(command -v gcc)"
  fi
  if command -v g++ >/dev/null 2>&1; then
    export CXX="$(command -v g++)"
  fi
  export CUDA_HOME
  CUDA_HOME="$(dirname "$(dirname "$(command -v nvcc)")")"
  export CFLAGS="-include cfloat ${CFLAGS:-}"
  export CXXFLAGS="-include cfloat ${CXXFLAGS:-}"
  export TORCH_NVCC_FLAGS="-Xcompiler -include=cfloat ${TORCH_NVCC_FLAGS:-}"

  python -m pip install fvcore iopath
  # This URL installs from source (no prebuilt wheel), compiling extensions locally.
  python -m pip install --no-build-isolation "git+https://github.com/facebookresearch/pytorch3d.git@${PYTORCH3D_REF}"
fi

if [[ "$SKIP_DOWNLOADS" != "1" ]]; then
  python "${PROJECT_ROOT}/download_models.py" \
    --models-dir "${MODELS_DIR}" \
    --cache-dir "${CACHE_DIR}"
fi

echo "Install complete."
echo "Source model paths: source \"${PROJECT_ROOT}/model_paths.env\""
