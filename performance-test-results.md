# Chatterbox-Turbo TTS — Performance Test Results

**Last updated:** 2026-09-16
**Server:** `openai_api_server.py` (OpenAI-compatible), port 5005, systemd unit `chatterbox-api.service`
**Model:** Chatterbox-Turbo (350M), `cuda:0`

> **RTF convention:** RTF = wall_time / audio_duration. **Lower is better.** RTF 0.15 means audio is generated ~6.6× faster than real time.

---

## TL;DR for other agents

1. **Single-request latency is excellent:** ~100-char sentence → **RTF ~0.15–0.18** (~0.8–1.0s for ~6s of audio); ~30-char → **~320 ms**.
2. **Do NOT fan out TTS requests in parallel on this box.** On a single (contended) GPU, concurrency adds *no* throughput and hurts latency. **Issue requests sequentially.**
3. The server enforces this with **`MAX_IN_FLIGHT = 1`** — it serializes GPU work, so even an accidental parallel burst gets best-case behavior. mp3 encoding runs outside the lock, so CPU encode overlaps the next request's GPU compute.
4. At ~6.6× real-time, **one sequential worker easily feeds 13 agents** (13 × ~6s speech = ~78s audio, generated in ~12.5s → ~6× playback headroom).

---

## Environment caveat

`cuda:0` is a ~95 GiB GPU **shared with a main LLM** that frequently holds 80–90 GiB. During these tests GPU0 had only **~3.5 GB free**, i.e. heavy contention. This is the realistic production condition. Absolute numbers would improve with a dedicated/less-contended GPU, but the *relative* conclusion (sequential > parallel on one GPU) holds because inference is GPU-compute-bound.

---

## Optimizations applied (2026-09-16)

| Change | Effect |
|---|---|
| **Per-voice `Conditionals` cache** (encode each voice once at boot, resident in VRAM; `generate(conds=...)`) | ~2× faster single requests; removed a voice-bleed race under concurrency |
| **`run_in_threadpool`** for blocking GPU generation | Concurrent requests no longer serialize behind the async event loop |
| **`MAX_IN_FLIGHT` semaphore** | Bounds concurrent GPU generations; set to **1** (see results) |
| **MP3 `-q:a 9 → 2`** | ~2.5× bitrate/quality (24 kHz mono speech: 30 → 76 kbps) |

---

## Results

### 1. Single request, before vs after the conds cache (warm)

| Test | Before (re-encode/call) | After (conds cache) | Target |
|---|---|---|---|
| 100-char (~5s audio) | 1.70s, RTF 0.339 | **0.81s, RTF 0.176** | ≤0.5 → ✅ |
| 30-char utterance | 0.75s | **0.32s (320 ms)** | <800 ms → ✅ |

### 2. Thirteen distinct `british-*` voices — sequential vs parallel

~100-char line each (~6s audio), `tts-1-hd`, warm.

**Sequential (one after another):** total **12.5s**, ~0.96s/clip, **RTF ~0.15**, dead consistent.

**Parallel, all 13 at once (measured at the then-cap of 3):** total **21.6s** — ~2× *slower*. Processed in clean waves of 3 (the cap working); later requests' apparent RTF is queue-wait, not slow generation.

### 3. Concurrency sweep (13 voices, effective in-flight 1/2/3)

| In-flight | Total (13 clips) | 1st response | 3rd response | Throughput |
|---|---|---|---|---|
| **1 (sequential)** | **12.5s** | **0.76s** | **2.61s** | **6.6× real-time** |
| 2 | 15.7s | 2.24s | 4.55s | 5.3× real-time |
| 3 | 21.6s | 4.88s | 5.55s | 3.8× real-time |

**Monotonic: concurrency 1 wins on total time, first-response latency, prefetch-3 latency, and throughput.** Even getting the first 3 clips ready is faster sequentially (2.61s) than at 3-way concurrency (5.55s).

### 4. Verification of `MAX_IN_FLIGHT = 1`

6 requests fired in parallel against the cap-1 server → **first done 0.69s, all 6 done 4.22s** (vs ~10s under cap-3). The server absorbs a parallel burst and serves it at best-case speed.

---

## Recommendation for client / app integration

- **Issue TTS requests sequentially**, one at a time. Do not thread/fan-out.
- Rely on the server's `MAX_IN_FLIGHT = 1` as a safety net if a burst does happen.
- Expect ~1s to generate a ~6s sentence; first audio is available in <1s.
- Revisit concurrency only if TTS is moved to a **dedicated GPU with real VRAM headroom** — then modest parallelism (2–3) may start to pay off and `MAX_IN_FLIGHT` can be raised.

---

## Boot / operational notes

- All 51 voices' `Conditionals` are built at startup and held in VRAM (~166 KB each, ~8.5 MB total; build ~0.12–0.18s/voice, ~8s total).
- The cache **build** needs transient VRAM headroom. If GPU0 is saturated at boot, some voices fail to pre-cache and fall back to lazy on-first-use encoding (which also needs headroom). Ensure the GPU isn't full when (re)starting the service.
- Restart: `sudo systemctl restart chatterbox-api` (model reload + cache build ≈ 30–35s to healthy).
