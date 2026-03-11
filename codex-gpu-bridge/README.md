# Codex GPU Bridge

Standalone compute-node server and login-node client for running commands on a GPU node while selecting the target conda environment per request.

## Layout

- `bin/gpu-agent-server`: wrapper for the compute-node server
- `bin/gpuctl`: wrapper for the login-node client
- `scripts/start_server.sh`: start the server on the compute node
- `src/gpu_agent_server.py`: HTTP server
- `src/gpuctl.py`: CLI client
- `state/logs`: run logs
- `state/runs`: run metadata and generated command scripts

## Quick Start

### 1. Start the server on the compute node

On the compute node:

```bash
cd /leonardo_work/EUHPC_B29_018/agoktogan/projects/codex-gpu-bridge
# Optional: source ./scripts/server.env.example after editing overrides
./scripts/start_server.sh
```

`start_server.sh` now does the setup itself:

- generates a token if `state/gpu-agent.token` does not exist
- writes a single handoff file at `state/gpu-agent.client.env`
- prints the URL, token path, env-file path, and server log path
- starts the compute-node HTTP server

By default it binds to `0.0.0.0:9000` and writes its own log to `state/server.log`.

### 2. Use the generated handoff file on the login node

On the login node:

```bash
source /leonardo_work/EUHPC_B29_018/agoktogan/projects/codex-gpu-bridge/state/gpu-agent.client.env
```

That one file contains:

- `GPU_AGENT_URL`
- `GPU_AGENT_TOKEN`
- `GPU_AGENT_CLIENT`
- server paths and short usage instructions in comments

### 3. Check health

```bash
"$GPU_AGENT_CLIENT" health
```

### 4. Run inside any conda env

By prefix:

```bash
"$GPU_AGENT_CLIENT" run \
  --cwd /leonardo_work/EUHPC_B27_009/agoktogan/projects/multiview-diffusion/met3r \
  --conda-prefix /shared/envs/met3r-py310 \
  --env CUDA_VISIBLE_DEVICES=0 \
  -- python -c 'import torch; print(torch.cuda.is_available())'
```

By env name:

```bash
"$GPU_AGENT_CLIENT" run \
  --cwd /path/to/repo \
  --conda-env met3r-py310 \
  --module-setup 'module load cuda/11.8' \
  -- pip install -e .
```

### 5. Inspect a run

```bash
"$GPU_AGENT_CLIENT" status <run_id>
"$GPU_AGENT_CLIENT" logs <run_id> --follow
```

## LLM Usage

The intended handoff to Codex is the generated file:

```bash
/leonardo_work/EUHPC_B29_018/agoktogan/projects/codex-gpu-bridge/state/gpu-agent.client.env
```

It already includes:

- the server URL
- the bearer token
- the `gpuctl` path
- comments telling the LLM to use `gpuctl run`, `gpuctl status`, and `gpuctl logs`

If you launch Codex from a shell where that file has been sourced, Codex can use the exported variables directly. If not, you can point Codex to that file and tell it to read it before using the bridge.

## Request Fields

- `command`: shell command to execute
- `cwd`: working directory
- `conda_prefix`: absolute path to the target env
- `conda_env_name`: alternative to `conda_prefix`
- `module_setup`: shell snippet executed before the command
- `env`: key/value environment variables
- `timeout_seconds`: optional hard timeout

## Notes

- The server process is independent from the target conda env.
- Logs and metadata persist under `state/`.
- If the login node cannot reach the compute node over TCP, this design will need a filesystem-queue variant.
