# cineca-agent

Utility repository for working on CINECA across login and compute nodes.

## Contents

- `codex-gpu-bridge/`: login-node client and compute-node server for submitting GPU jobs to a compute node with per-run conda environment selection.
- `model-download-agent/`: example/template workflow showing how to add install and model-download logic to another repository.

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

## Model download template

`model-download-agent/` is an example only. Agents should not treat it as a shared working directory to customize per project.

Instead, copy the relevant install and model-download logic from that example into the target repository, then create the target repo's own files such as:

- `install.sh`
- `download_models.py`
- `requirements.txt`
- `model_paths.env` generation logic

See `model-download-agent/README.md` and `model-download-agent/AGENT.md` for the template workflow and adaptation rules.
