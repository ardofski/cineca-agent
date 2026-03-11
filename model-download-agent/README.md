# Model Download Agent (Example)

## Overview
This repo provides a minimal, reusable pattern for downloading model artifacts,
writing `model_paths.env`, and preparing offline-friendly runs.

This directory is an example template only. When adapting a real project, do
not keep editing files in `model-download-agent/`. Copy the relevant logic into
the target repository and create that repository's own `install.sh`,
`download_models.py`, `requirements.txt`, and README updates there.

## What Agents Should Do

1. Read this example and the target repository's setup instructions.
2. Copy the install and download pattern into the target repository.
3. Generate new repo-local files as needed, instead of modifying this example.
4. Adjust env names, dependency versions, downloads, and exported paths for the
   target repository.

## Example Usage
```bash
./install.sh
```

```bash
python download_models.py
source model_paths.env
```

## HPC Cluster Environment
In a real integration, run the copied workflow from the target repository, not
from this example folder. Use the login node for environment setup and initial
downloads. The compute node can run fully offline or re-download if network
access is allowed.

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
