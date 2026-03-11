# cineca_agent

Utility repository for working on CINECA across login and compute nodes.

## Contents

- `codex-gpu-bridge/`: login-node client and compute-node server for submitting GPU jobs to a compute node with per-run conda environment selection.
- `model-download-agent/`: helper workflow for downloading model artifacts on the login node and preparing offline-friendly compute-node runs.

## GPU bridge

The GPU bridge separates control and execution:

- `gpuctl` runs on the login node
- `gpu-agent-server` runs on the compute node
- runtime metadata, logs, tokens, and generated client env files live under `codex-gpu-bridge/state/`

Start with:

```bash
cd codex-gpu-bridge
./scripts/start_server.sh
```

Then source the generated handoff file on the login node:

```bash
source codex-gpu-bridge/state/gpu-agent.client.env
"$GPU_AGENT_CLIENT" health
```

See `codex-gpu-bridge/README.md` and `codex-gpu-bridge/docs/architecture.md` for details.

## Model download workflow

Use the login node for setup and downloads:

```bash
cd model-download-agent
./install.sh
python download_models.py
source model_paths.env
```

For offline compute-node runs:

```bash
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
```

See `model-download-agent/README.md` and `model-download-agent/AGENT.md` for the full workflow.
