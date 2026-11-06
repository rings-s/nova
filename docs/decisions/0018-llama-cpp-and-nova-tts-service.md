# 0018 — llama.cpp Serves the Text Model; NOVA's Own Service Serves Sara's Voice

## Status

Accepted — 2026-10-23. Amends ADR-0017's speech server (vLLM-Omni becomes `infra/tts`). ADR-0011's
rule that agents are reached only through `ai_agents/runtime.py` still holds.

> **Superseded in part, 2026-10-28:** vLLM serves the text model now, not llama.cpp
> ([[0019-vllm-serves-the-text-model]]). The speech server below, `infra/tts`, is unchanged.

## Context

The owner asked for production to serve the models with llama.cpp rather than LM Studio, on an
NVIDIA GPU server, with:

- a small Qwen model for text: Qwen3-1.7B, chosen over 4B (Qwen3 has no 2B);
- thinking switched off, for faster replies;
- Sara speaking with the Saudi Qwen3-TTS fine-tune `vadimbelsky/qwen3-TTS-KSA`.

Until now, development ran LM Studio on the host (`AI_PROVIDER=lmstudio`), production had no model
server defined in the repository, and ADR-0017 named vLLM-Omni for speech, unverified.

LM Studio is a desktop application. It is not something to run on a server, and its loaded model
and slot count are not kept across a restart: the AI memory notes record both being lost.

llama.cpp cannot serve the voice:

- its Qwen3-TTS pull request (ggml-org/llama.cpp#20752) was closed unmerged;
- what that PR added was a command-line tool, never an `/audio/speech` endpoint;
- the fine-tune ships as a `qwen-tts` checkpoint (safetensors, 4.5 GB), not GGUF.

vLLM-Omni was never confirmed to expose the fine-tune's baked speaker as a `voice`.

## Decision

### llama.cpp, as the compose `llm` service

The compose service `llm` runs `llama-server`:

- **Image:** no profile, so it starts with the stack (it had profile `llamacpp` until
  2026-10-24); the image is pinned to a build tag
  (`server-b11459`, `server-cuda-b11459` under `infra/docker-compose.gpu.yml`).
- **Model:** it downloads `Qwen/Qwen3-1.7B-GGUF` (Q8_0) into a volume on first start and answers as
  `qwen3-1.7b`.
  - **Update 2026-10-28:** the owner switched the default to Qwen3-4B (`Qwen/Qwen3-4B-GGUF`,
    `Qwen3-4B-Q4_K_M.gguf`, alias `qwen3-4b`) for better answers. Q4_K_M rather than Q8_0 keeps it
    usable on a CPU. The 1.7B remains a `LLM_*` setting away.
- **Port:** none is published; the backend and worker call `http://llm:8080/v1`.

`AI_PROVIDER=llamacpp` reads it like LM Studio:

- the model family comes from the bare name;
- a reasoning model's thinking arrives in `reasoning_content`, never shown as the answer.

Thinking is switched off in three places. Any one should be enough; together, no single setting
(a changed launch command, a server that ignores request kwargs, a model that ignores the prompt
switch) can turn it back on:

1. `--reasoning-budget 0` on the server;
2. the chat template's `enable_thinking: false` on every request (`runtime.py`, `_model_settings`),
   which writes an empty `<think></think>` instead of asking the model not to think;
3. the existing `/no_think` suffix.

The service keeps one slot by default. With several, a turn's follow-up calls can land on a slot
that does not hold the prompt and read it all again (measured in LM Studio). On a GPU,
`LLM_PARALLEL` is raised together with `AI_MAX_CONCURRENT_TURNS`.

The GPU override is a separate file: a GPU reservation fails outright on a host without the NVIDIA
container toolkit, so the base file must not carry one.

### Sara's voice, as the compose `tts` service

`infra/tts/server.py` is a small FastAPI app around `qwen-tts`. It answers the same
`POST /v1/audio/speech` the backend already sends (`integrations/voice/speech.py`), so the backend
changes only in configuration (`VOICE_TTS_BASE_URL=http://tts:8091/v1`). Specifically:

- **Request mapping:** `voice` is the speaker (`ksa_speaker`), and `language` and `instructions`
  pass through. The library rejects an unknown speaker or language, which becomes a 400.
- **Audio:** the model speaks at 24 kHz and a phone line carries 8 kHz, while the backend keeps only
  a mono PCM WAV at the rate it asked for (`wav_problem`). So the service resamples to the request's
  `sample_rate` (1:3 for 8000 Hz, `scipy.signal.resample_poly`) and writes 16-bit PCM.
- **Concurrency:** one clip at a time. Concurrent clips on one GPU only make each caller wait
  longer, and the backend already sends a slow reply to Unifonic's own voice.
- **Image:** `qwen-tts` is installed without its gradio dependency, which is for its demo app. The
  image runs as a non-root user and is built for CUDA by default (`TTS_TORCH_INDEX` builds a CPU
  one for development).
- **Auth:** `VOICE_TTS_API_KEY`, when set, is required by the service too.

## Consequences

- **Development uses llama.cpp too** (since 2026-10-24, at the owner's request): the `llm` service
  starts with `make dev`, and `AI_PROVIDER=llamacpp`, `AI_BASE_URL=http://llm:8080/v1` are the
  `Settings` defaults. The same day, Ollama, LM Studio and the hosted `openai_compatible` provider
  were removed: `AI_PROVIDER` and `VOICE_AI_PROVIDER` accept only `llamacpp`. `tts` stays
  behind `--profile tts`.
- **CPU speed:** the CPU build of `tts` runs on CPU, but far slower than a phone turn allows, so on a
  CPU Unifonic reads Sara's replies.
- **Unverified latencies:** neither service's latency has been measured on a GPU; the development
  machine has none. Before go-live, measure:
  - a chat turn, against `AI_REQUEST_TIMEOUT_SECONDS`;
  - a voice turn's model plus speech, against `VOICE_TURN_BUDGET_SECONDS`.
- **Upgrading llama.cpp** means changing both pinned tags. A newer build may change the default
  `--reasoning-format` that puts thinking in `reasoning_content`.
- **Still open from ADR-0017:** the KSA fine-tune's authors call it not production-ready, and
  whether `ksa_speaker` is a woman's voice remains unconfirmed.
