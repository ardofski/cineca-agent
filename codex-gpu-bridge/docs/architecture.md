# Architecture

This workspace separates control from execution:

- the compute node runs `gpu-agent-server`
- the login node runs `gpuctl`
- each request chooses the target conda env independently

The server is intentionally stdlib-only. It can stay in a stable base Python while launching subprocesses inside arbitrary envs with `conda run`.

## Request Flow

1. `gpuctl` sends an HTTP request to the compute node
2. `gpu-agent-server` writes run metadata and a shell script into `state/runs`
3. the server starts the subprocess and streams stdout/stderr into `state/logs/<run_id>.log`
4. `gpuctl` polls for status or logs

## Supported Controls

- `GET /health`
- `POST /run`
- `GET /runs`
- `GET /runs/<run_id>`
- `GET /runs/<run_id>/logs`
- `POST /runs/<run_id>/cancel`

## Conda Independence

The server itself does not activate the target environment globally. Each run can specify either:

- `conda_prefix`
- `conda_env_name`

The server then launches the command with:

```bash
conda run --no-capture-output ...
```

That keeps the control plane independent from the repo-specific env.

## Network Assumption

This version assumes the login node can reach the compute node over the cluster network on the configured port. If that turns out to be blocked, the same command model can be switched later to a filesystem queue without changing the run payload format.
