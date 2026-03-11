# Model Download Agent (Example)

## Overview
This repo provides a minimal, reusable pattern for downloading model artifacts,
writing `model_paths.env`, and preparing offline-friendly runs.

## Installation
```bash
./install.sh
```

## Usage
```bash
python download_models.py
source model_paths.env
```

## HPC Cluster Environment
Use the login node for environment setup and initial downloads. The compute
node can run fully offline or re-download if network access is allowed.

### Login Node (setup + downloads)
```bash
export HF_TOKEN=...                 # if gated models are required
./install.sh
source model_paths.env
```

### Compute Node (run jobs)
```bash
source model_paths.env
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
```

If the compute node has internet access, you may re-run downloads:
```bash
python download_models.py
```

### PyTorch3D (optional)
If your repo needs PyTorch3D, run:
```bash
INSTALL_PYTORCH3D=1 ./install.sh
```
This follows the same build flags as the `sam-3d-objects` install flow.
