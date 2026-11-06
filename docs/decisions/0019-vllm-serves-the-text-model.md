# 0019 — vLLM Serves the Text Model

## Status

Accepted — 2026-10-28. Supersedes ADR-0018's text-model half (llama.cpp). ADR-0018's speech
server, `infra/tts`, stands. ADR-0011's rule that agents are reached only through
`ai_agents/runtime.py` still holds.

## Context

The owner asked for vLLM to serve the agents' model instead of llama.cpp, and earlier the same day
for Qwen3-4B instead of Qwen3-1.7B.

vLLM is built for NVIDIA GPUs. Its CPU build runs on x86 with AVX-512, and it differs from
llama.cpp in the one way that matters on a laptop: it loads full-precision weights, not a
quantised GGUF file. In bfloat16, Qwen3-4B is about 8 GB and Qwen3-1.7B about 3.4 GB. The
development laptop (i7-1185G7, AVX-512, 16 GB, no GPU) has about 10 GB free with the rest of the
stack running, which does not leave the 4B room for its KV cache and vLLM's own processes.

## Decision

- **vLLM is the only model server**, as the compose `llm` service, in every environment.
  `AI_PROVIDER` and `VOICE_AI_PROVIDER` accept only `vllm`, so a stale `llamacpp` stops `Settings`
  from loading rather than being ignored. `AI_BASE_URL` defaults to `http://llm:8000/v1`.
- **Images, one release:** the base compose file runs the CPU build
  (`public.ecr.aws/q9t5s3a7/vllm-cpu-release-repo:v0.10.2`); `infra/docker-compose.gpu.yml`
  switches to the CUDA build (`vllm/vllm-openai:v0.10.2`). v0.10.2 was the newest tag published
  for both when this was written.
- **Model per environment:** the default is Qwen3-4B (`LLM_MODEL=Qwen/Qwen3-4B`, served as
  `qwen3-4b`), meant for a GPU. A CPU-only machine sets `LLM_MODEL=Qwen/Qwen3-1.7B`,
  `LLM_ALIAS=qwen3-1.7b` and both `AI_*_MODEL` to match; the development laptop does.
- **Serving flags:** `--served-model-name` is the alias the agents ask for (it must contain `qwen3`
  for thinking to be switched off), `--enable-auto-tool-choice --tool-call-parser hermes` for
  Qwen3's tool calls, `--reasoning-parser qwen3` so any thinking lands in `reasoning_content` and
  is never shown, `--max-model-len 8192` and `--max-num-seqs 1` (`LLM_CTX`, `LLM_PARALLEL`).
- **Thinking stays off two ways:** the chat template's `enable_thinking: false` on every request
  (`runtime.py::_model_settings`, which vLLM accepts as `chat_template_kwargs`) and `/no_think`.
  llama.cpp's third switch, `--reasoning-budget 0`, has no vLLM equivalent.

## Consequences

- Nothing in `runtime.py` changed but names: vLLM speaks the same OpenAI chat protocol, and the
  agents never see which server answers.
- The weights come from Hugging Face in full precision. The `llm_models` volume still holds
  llama.cpp's GGUF files from before; they are unused and can be removed by deleting the volume.
- On a CPU, vLLM reads every weight for every token, so a turn on the laptop is not faster than it
  was on llama.cpp's quantised 4B. The speed has not been measured yet.
- GGUF and int4 quantisations on vLLM's CPU build were not evaluated. If one works, the 4B may fit
  on the laptop after all.
