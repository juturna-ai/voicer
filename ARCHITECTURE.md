# Voice Studio — Architecture

Local ElevenLabs-style voice studio. Python backend (FastAPI) + static web UI. Runs in WSL2 on an RTX 2080 (8 GB).

## Layout
| Path | Purpose |
|---|---|
| `voicer/config.py` | Settings (paths, port, device, idle unload). All overridable by `VOICER_*` env vars. |
| `voicer/engines/` | One module per TTS engine. All implement `Engine` (`base.py`) and return `Audio(samples float32 mono, sr)`. |
| `voicer/engines/__init__.py` | `ENGINES` registry: engine name → class. |
| `voicer/engines/openvoice.py` | OpenVoice v2 tone colour converter (voice changer model). Not a TTS engine: not in `ENGINES`. |
| `voicer/jobs.py` | Job queue: speech jobs (REST, OpenAI, WebSocket, MCP `speak`) wait their turn and run one at a time; full queue → 503 + `Retry-After`. See "Job queue". |
| `voicer/remote.py` | Remote access through Tailscale: finds the Tailscale CLI (WSL or Windows), reads `tailscale status` / `serve status`, and builds the public `https://<pc>.ts.net` base for links. See "Remote access". |
| `voicer/usage.py` | Usage stats: one line per clip saved to History in `data/usage.jsonl`, with channel, agent and API key/device; `summary(days)` adds them up. See "Usage stats". |
| `voicer/models.py` | Model manager: lazy load, one *large* engine in VRAM at a time, idle unload thread. `use(name)` holds an engine for one job. `MODELS` = `ENGINES` + `openvoice`. |
| `voicer/voice_changer.py` | Voice changer: recording + target voice → converted clip in History (with Whisper subtitles). |
| `voicer/voices.py` | Voice store (`data/voices/<id>/voice.json` + `samples/`). Lookup by id or name. |
| `voicer/tts.py` | Synthesis service: text + voice + language → `Audio`. |
| `voicer/text/` | Text pipeline: `split.py` (sentences), `lang.py` (es/en detect), `normalize.py` (spell out numbers etc.). |
| `voicer/dictionary.py` | Pronunciation dictionary (`data/dictionary.json`), CSV import/export. |
| `voicer/text/tags.py`, `voicer/effects.py` | Inline tags parser; DSP effects for styles (pitch, gain, whisper). |
| `voicer/subtitles.py` | SRT / WebVTT from sentence timings (two lines of ≤42 characters per cue). |
| `voicer/apikey.py` | Optional API key: make / replace / turn off, SHA-256 hash in `settings.json`, "is this request from this PC" check. |
| `voicer/mcp_server.py` | MCP server for agents (tools `list_voices`, `search_voices`, `speak`). stdio: `.venv/bin/python -m voicer.mcp_server`; HTTP: `/mcp` on the main server. |
| `voicer/backup.py` | Backup: export My Voices + the pronunciation dictionary as one zip (`/api/export`) and import it (`/api/import`). See "Backup". |
| `voicer/autobackup.py` | Optional daily auto-backup to a folder (off by default; Settings page). Timer thread started in the server lifespan. See "Backup". |
| `voicer/batch.py` | Batch Text to Speech (`/api/batch`): many items, per-item errors, optional ZIP with `manifest.json`. Reads .txt / .docx / .csv files (`/api/batch/parse`) and zips clips already in History (`/api/batch/zip`). |
| `voicer/dialogue.py` | Multi-speaker dialogue: parse `Name: text` scripts, speak each turn with its voice, level and join into one clip. |
| `voicer/stream.py` | Live streaming: `open_stream` (first sentence spoken before the answer, then one piece per sentence), `Encoder` (piece-by-piece WAV/PCM/MP3/OGG/AAC/FLAC). |
| `voicer/openai_api.py` | OpenAI-compatible `POST /v1/audio/speech` (router `/v1`, OpenAI error shape). |
| `voicer/settings.py` | App settings in `data/settings.json` (`default_voice`); atomic writes, missing/broken file → defaults. |
| `voicer/library.py` | Voice Library: curated catalog `library/catalog.json`, search/filters, add to My Voices. |
| `voicer/server.py`, `voicer/__main__.py` | FastAPI app: web UI at `/` (static files `voicer/web/`), JSON API under `/api`. Start: `.venv/bin/python -m voicer` → `0.0.0.0:8765`. Starts the idle-model reaper. |
| `voicer/web/` | UI: `index.html`, `app.css` (dark theme), `app.js` (vanilla JS, hash routes `#tts`, `#clone`…; no build step). |
| `voicer/audio.py` | Audio file read/write helpers; `decode()` reads any container (WebM/Opus, MP3, M4A…) via PyAV/FFmpeg. |
| `voicer/cleanup.py` | Sample cleaning: 24 kHz mono, 70 Hz high-pass, spectral-gating denoise (`noisereduce`), silence trim, level to −20 dBFS / peak −1 dBFS, split 6–15 s at pauses. |
| `voicer/clone.py` | Clone drafts: uploaded/recorded audio kept in `data/drafts/<id>/raw/` before a voice is saved. |
| `voicer/analysis.py` | Estimates gender, age range and style tags from a speech clip (pitch, 3rd formant, rate, brightness). |
| `scripts/add_voice.py` | Adds a preset voice to the library: validates license/source (Piper: read from MODEL_CARD), test-synthesizes, then fills metadata and renders the preview. Requires `--confirm-not-real-person`. |
| `scripts/make_licenses.py` | Writes `LICENSES.md` (all models + every library voice) from the catalog. `add_voice.py` runs it. |
| `LICENSES.md` | Generated license list. `tests/test_licenses.py` fails if it is out of date. |
| `scripts/make_previews.py` | Renders a 5–8 s MP3 preview per library voice → `library/previews/<id>.mp3`, sets `preview`. |
| `scripts/fill_metadata.py` | Fills missing gender/age/style tags in the library catalog from a synthesized clip (cached in `data/cache/analysis/`). |
| `tests/` | pytest. `gpu` marker = needs models. `conftest.py` isolates data in a temp dir and has a faster-whisper transcription check. |
| `install.sh`, `start.sh` | Install (uv + `.venv` + packages) and start the server. See "Install and start". |
| `README.md` | Short user guide (under 50 lines): start, library, cloning, API and MCP examples. `tests/test_readme.py` runs its examples. |
| `windows.sh` | Windows desktop shortcut and optional auto-start at sign-in (WSL only). See "Install and start". |
| `requirements/lock.txt` | Tested package versions (freeze of the working `.venv`), used as a constraint by `install.sh`. |
| `data/models/` | Downloaded model files (Piper voices). Shared with tests (`VOICER_MODELS`). |
| `data/` | Runtime user data (git-ignored): voices, cache, outputs, models. |

## Environment
- Python 3.11 venv in `.venv` (created with `uv`). PyTorch 2.7.1 + CUDA 12.6 wheels (supports RTX 2080, sm_75).
- CUDA verified in WSL2 (driver CUDA 13.3, `torch.cuda.is_available() == True`).
- `requirements/constraints.txt` pins torch and `transformers<4.58` (coqui-tts 0.27.5 breaks on transformers 5).

## Install and start
- `./install.sh [--cpu] [--dev]` (Linux, WSL2, VPS): finds `uv` (`$UV`, PATH, `~/.local/bin`, `~/.cargo/bin`) or installs it with the official installer (no PATH edits); makes `.venv` with Python 3.11 if missing; installs `requirements/base.txt` with `-c constraints.txt -c lock.txt` and the PyTorch CUDA 12.6 index (`--cpu`: the CPU index); `--dev` adds `dev.txt` + Playwright Chromium; ends with an import check that prints the GPU. Safe to run again. Models are not downloaded here (lazy, on first use).
- `./start.sh [--open]`: runs `.venv/bin/python -m voicer` in the foreground (Ctrl+C stops it; port `VOICER_PORT`, default 8765). If `/api/health` already answers, it does not start a second server. `--open` opens the UI once the server answers: `$VOICER_BROWSER` if set (tests), else under WSL `cmd.exe /c start` (the Windows default browser), else `xdg-open`.
- `requirements/lock.txt`: `uv pip freeze` of the working `.venv` without local tags (`+cu126`) and URL lines, so the same pins serve GPU and CPU installs. Remake it after a package change.
- `./windows.sh shortcut | remove-shortcut` (WSL only): makes or removes `Voice Studio.lnk` on the Windows desktop (PowerShell + `WScript.Shell`). Target `%SystemRoot%\System32\wsl.exe`, arguments `-d <distro> --cd "<repo>" -- [env VOICER_PORT=… VOICER_DATA=… VOICER_BROWSER=…] ./start.sh --open`, minimized window (closing it stops the server), working folder `%USERPROFILE%`. `VOICER_DESKTOP` (a Windows path) overrides the folder for tests. Double-click: starts the server (or finds it running) and opens the Windows browser.
- `./windows.sh autostart on | off` (WSL only, optional, off by default): puts or removes the same kind of shortcut (`./start.sh`, no `--open`, minimized) in the user's Windows Startup folder (`[Environment]::GetFolderPath('Startup')`; `VOICER_STARTUP` overrides for tests). Windows runs it at each sign-in. If the desktop icon is used later, `start.sh` finds the running server and only opens the browser.
- Tests: `tests/test_scripts.py` (syntax, help, start/open/already running/Ctrl+C; full fresh install only with `VOICER_TEST_INSTALL=1`); `tests/test_windows.py` (shortcut made in a Windows temp folder, its target/arguments/window read back, launched like a double-click, UI opened, `/api/health` reached from Windows, removed; auto-start shortcut launched like a sign-in: server up, no browser, then turned off; skipped outside WSL).

## Engines
| Engine | Key | Size | Cloning | Languages | License |
|---|---|---|---|---|---|
| XTTS-v2 (`coqui-tts` 0.27.5) | `xtts` | large (~2 GB VRAM) | yes, zero-shot from samples | en, es (cross-lingual) | Code MPL-2.0; weights Coqui Public Model License (non-commercial) |
| F5-TTS (`f5-tts` 1.1.22) | `f5` | large (~1.5 GB VRAM) | yes, from one ≤11 s clip + transcript | en (`SWivid/F5-TTS` F5TTS_v1_Base), es (`jpgallegoar/F5-Spanish`, F5TTS_Base arch) | Code MIT; weights CC-BY-NC-4.0 (non-commercial) |
| Kokoro-82M (`kokoro` 0.9.4) | `kokoro` | small (~0.35 GB VRAM) | no (preset voices) | en-US (`a*`), en-GB (`b*`), es (`e*`) | Apache-2.0 (code + weights) |
| Piper (`piper-tts` 1.8.0, ONNX) | `piper` | small (CPU) | no (preset voices) | es_MX, es_ES, es_AR, en_US, en_GB | Code GPL-3.0 (local use only, not redistributed); each voice has its own license (MODEL_CARD) |

### XTTS-v2
- Weights download on first load to `~/.local/share/tts/` (1.9 GB). `COQUI_TOS_AGREED=1` is set in config (non-commercial CPML).
- Cloned voice: conditioning latents from all `samples/*.wav` (`gpt_cond_len=30`, `max_ref_length=60`).
- Studio voice: `engine_voice` = built-in speaker name (58 synthetic speakers in `speakers_xtts.pth`).
- Output 24 kHz.

### F5-TTS
- Checkpoint picked by language; only one F5 checkpoint loaded at a time (switching language reloads).
- `f5_tts` seeds every call with a random number up to 2**63 and writes it to `os.environ["PYTHONHASHSEED"]`. Python only accepts 0–4294967295 there, so every Python process started later from the server died at start-up (MCP stdio, scripts). `F5Engine.synthesize` puts the old value back after each call.
- Real load is deferred to first synthesis because the checkpoint depends on language.
- Reference: first sample cut to 11 s → `voices/<id>/cache/f5_ref.wav`, transcript from faster-whisper → `f5_ref.txt` (cached).
- Vocoder: Vocos `charactr/vocos-mel-24khz` (MIT). Output 24 kHz.

### Kokoro
- `engine_voice` = Kokoro voice id (e.g. `af_heart`, `bm_george`, `ef_dora`, `em_alex`).
- Pipeline chosen from requested language: `es` → `e`; `en` → voice prefix (`a`/`b`). One `KPipeline` per code, cached; they share one `KModel`.
- Spanish G2P via espeak-ng (bundled by `espeakng-loader`); English via misaki + spaCy `en_core_web_sm` (installed from wheel URL — the venv has no pip for runtime download).
- Not "large": may stay loaded next to XTTS/F5. Output 24 kHz.

### Piper
- `engine_voice` = Piper voice key (`es_MX-ald-medium`, `en_US-lessac-medium`, …). Optional `settings.speaker_id` for multi-speaker models.
- Voice files downloaded on first use from HF `rhasspy/piper-voices` to `data/models/piper/` (`VOICER_MODELS`), loaded once and kept in RAM.
- Runs on CPU (onnxruntime). Speed → `length_scale = 1/speed`. Output rate from the voice config (16 or 22.05 kHz).

## Speech-to-text (`voicer/asr.py`)
- faster-whisper `small` on CPU int8 (keeps VRAM for TTS). Model name via `VOICER_WHISPER`.

## Text → speech pipeline (`tts.speak`)
0. `tags.parse` — split text into text items (with style) and pause items (see Text tags).
1. `split_paragraphs` → `split_sentences` — splits on `. ! ? …` before a capital/`¿`/`¡`/digit; skips abbreviations (`Dr.`, `Sra.`, initials). Each sentence carries the pause that follows it (`PAUSE` table in `text/split.py`: `.` 0.35 s, `?`/`!` 0.4 s, line break 0.5 s, paragraph 0.7 s).
2. Language per sentence: `language="auto"` → `text.lang.detect` (stop-word + accent/`ñ¿¡` score; ties keep the previous sentence's language, first sentence falls back to the voice's language). `language="es"|"en"` overrides all sentences.
3. `dictionary.apply(sentence, lang)` — whole-word, case-insensitive, longest entry first. Runs **before** normalization so entries can override numbers/abbreviations (e.g. `24/7`).
4. `normalize(sentence, lang)` (skip with `normalize_text=False`), in this order: e-mails/URLs → money → dates → times → percent → ordinals → `No.`/`#` → abbreviations → negative numbers → plain numbers → Spanish apocope (`veintiún años`, `un libro`, `primer lugar`).
   - Money: `$` = MXN in Spanish, USD in English; `US$`, `€`, `MXN`, `USD`, `EUR` explicit. Number formats `1,234.50` (MX/US), `1.234,50` (ES), `3,5` (es decimal).
   - Dates: ISO `YYYY-MM-DD`; slashes are `d/m/y` in Spanish and `m/d/y` in English.
   - Times: `3:30 pm`, `15:45` → `las tres y media de la tarde` / `three thirty PM`.
5. `chunk(sentence, engine.max_chars)` — over-long sentences cut at `; : —`, then `,`, then a space; never inside a word (xtts 200, f5 300, kokoro/piper 400 chars). Short pauses after clause cuts (`,` 0.15 s).
6. `synthesize` per segment → `trim` (drop silence below −40 dB of peak, keep 50 ms margin, 5 ms fades) → `concat` with each segment's pause.
`plan()` returns `Segment(text, lang, pause)`. `tts.synthesize` = single engine call (one language).

## Text tags (`text/tags.py`, `effects.py`)
- `[pause 0.5s]`, `[pause 1s]`, `[pause 300ms]` (max 10 s): exact gap at that spot (replaces the natural pause; consecutive tags add up; tags before any text = leading silence).
- Style tags apply to following text until the next style tag or `[normal]`:
  | Tag | All engines | XTTS only (`expressive`) |
  |---|---|---|
  | `[slow]` / `[fast]` | speed ×0.8 / ×1.25 | – |
  | `[whisper]` | DSP: STFT phase randomization (removes pitch) −6 dB | – |
  | `[happy]` | speed ×1.05, pitch +1 st | temperature 0.8 |
  | `[excited]` | speed ×1.15, pitch +2 st, +2 dB | temperature 0.85 |
  | `[sad]` | speed ×0.88, pitch −1.5 st, −3 dB | temperature 0.6 |
- Unknown or malformed `[...]` tags are removed and never spoken. `tags.strip()` gives tag-free text.
- No engine here has native emotion/whisper control, so styles are prosody + DSP approximations.

## Pronunciation dictionary (`voicer/dictionary.py`)
- File: `data/dictionary.json` = `{"es": {word: spoken}, "en": {...}}`. Atomic writes, in-memory cache.
- `set_entry`, `delete_entry`, `apply(text, lang)`, `export_csv()`, `import_csv(text, replace=False)`.
- CSV columns: `language,word,spoken` (header optional, UTF-8 BOM tolerated; `,` `;` or tab, picked from the first line; language case-insensitive). Import is all or nothing: a bad row → `ValueError("Row N: …")`, nothing saved.
- Limits: word ≤ 100 characters, spoken form ≤ 300, 5000 words per language. Words match without case: adding "whatsapp" replaces "WhatsApp" (no duplicates). `set_entry(lang, word, spoken, old=…)` renames a word.
- API (see route table): `GET/PUT/DELETE /api/dictionary`, `POST /api/dictionary/listen`, `GET /api/dictionary/export`, `POST /api/dictionary/import`. Tests: `tests/test_dictionary.py`, `tests/test_dictionary_api.py`.
- Page `#dictionary` (`views.dictionary` in `app.js`): form (language, word, "say it as") → Add word / Save change (edit sends `old_word`; a language change = add in the new one + delete in the old one), ▶ Listen speaks the typed spoken form; a list of both languages with search, ▶ per row (speaks the *word*, so you hear the dictionary at work), Edit, Delete (confirm). Export CSV link, Import CSV (adds or changes words; no replace in the UI). Tests: `tests/test_ui_dictionary.py`.
- Backup import adds only words you do not have (case-insensitive) and skips entries over the limits (never cuts them).

## Voice Library (`library/catalog.json`, `voicer/library.py`)
- Curated preset voices; each entry has the full voice record + `license_url`, `model_url` (Piper). Ids: `kokoro-<voice>`, `piper-<key>[-<speaker>]`, `xtts-<name>`.
- Sources researched (Oct 2026):
  - Kokoro-82M (HF `hexgrad/Kokoro-82M`, Apache-2.0): 12 English + 3 Spanish. Excluded `af_sky`, `af_alloy`, `af_nova`, `am_echo`, `am_onyx`, `bm_fable` (named after another company's voices → possible imitation) and packs graded D or lower in VOICES.md.
  - Piper (HF `rhasspy/piper-voices`): license per training dataset from each `MODEL_CARD`. Excluded voices whose card says only "See URL" (amy, danny, kusal, alan, jenny_dioco), Quran-recitation dataset (reza_ibrahim), and 100+-speaker sets.
  - XTTS-v2 studio speakers: all 58 synthetic speakers in `speakers_xtts.pth` (CPML, non-commercial). Cross-lingual (can speak Spanish).
    8 of them also have a Spanish entry (id suffix `-es`, accent "Neutral (multilingual)") so Spanish users can find them.
  - Counts: 107 voices — 20 Spanish (3 native Latin American: Piper es_MX ald, es_MX claude, es_AR daniela), 87 English.
  - Not added: community es_MX Piper checkpoints on HF (e.g. HirCoir/*) — unclear licenses and several imitate real people or characters (rule: no real/famous voice imitation).
  - Also checked: F5-Spanish (cloning model, no presets), facebook MMS-TTS (CC-BY-NC, single voice/language — not added).
- Metadata per voice: name, language, accent, gender (`female`/`male`/`neutral`), age (`young adult`/`adult`/`middle-aged`/`senior`),
  style tags (`warm`, `narrator`, `news`, `conversational`, `energetic`, `calm`), engine, license, license_url, source_url, `commercial` (bool).
- Fields not stated by the source are **estimated** (`scripts/fill_metadata.py`, `voicer/analysis.py`) and listed in the voice's `estimated` field:
  - gender: score = semitones(median F0 / 155 Hz) + semitones(3rd formant / 2650 Hz); ≥ −1.05 → female. 45/47 correct on voices of known gender.
  - age: median F0 vs the usual adult range for that gender (coarse).
  - style: rank among same-language voices for speaking rate, pitch movement, brightness.
  - Values stated by the source win (`DOCUMENTED` in the script; e.g. Piper `sam` is a non-binary voice → `neutral`).
  - Kokoro gender comes from the voice name prefix (`af`/`am`…, documented by Kokoro).
- Previews: `library/previews/<id>.mp3` (5–8 s, MP3 for small size, ~4.7 MB total). `preview` field is relative to `library/`.
  Text per language tries 3 lengths until the clip is 5–8 s. `library.preview_path(v)` resolves it (only inside `library/previews/`).
  `add_to_my_voices` copies it to `voices/<id>/preview.mp3`.
- Adding voices later: `scripts/add_voice.py` (see its `--help`). `commercial` is never assumed "yes": it must be given,
  or is set to "no" when the license text says non-commercial / NC / CPML. Piper cards that say only "See URL" are refused.
- `voices.find()` resolves My Voices first, then library ids, then names (with or without the ` (Engine)` suffix).
- `library.add_to_my_voices(id)` copies an entry into `data/voices/` (`kind=preset`, `library_id` kept).

## Server and UI
- `python -m voicer` runs uvicorn on `VOICER_HOST` (default `0.0.0.0`) : `VOICER_PORT` (default 8765).
  Binding `0.0.0.0` in WSL2 makes it reachable from Windows at `http://localhost:8765` (verified with PowerShell `Invoke-WebRequest`).
- API routes:
  | Method | Path | Purpose |
  |---|---|---|
  | GET | `/api/health` | status, version, loaded models, `queue: {running, waiting, done, rejected, max_waiting}` |
  | POST | `/api/clone/drafts` | new clone draft → `{id, files: []}` |
  | GET | `/api/clone/drafts/{id}` | draft with files and `total_seconds` |
  | POST | `/api/clone/drafts/{id}/files?source=upload\|mic` | multipart `files` (many). Bad files are skipped and listed in `errors`; 400 if all bad |
  | GET / DELETE | `/api/clone/drafts/{id}/files/{name}` | play / remove one raw file |
  | POST | `/api/clone/drafts/{id}/process` | auto-clean all raw files → `clips` (6–15 s), `clean_seconds`, `clean_errors` |
  | GET | `/api/clone/drafts/{id}/clips/{name}` | play one cleaned clip (WAV) |
  | POST | `/api/clone/drafts/{id}/transcribe?language=auto\|en\|es` | transcribe clips that have no text yet |
  | PUT | `/api/clone/drafts/{id}/clips/{name}/text` | save a corrected transcript `{"text": "..."}` (max 1000 chars) |
  | POST | `/api/clone/drafts/{id}/preview` | `{text?, language?, engine?}` → WAV spoken with the draft clips (max 300 chars) |
  | GET | `/api/blend/sources` | voices that can be blended (`origin` mine/library) |
  | POST | `/api/blend/preview` | `{a, b, ratio, text?, language?}` → WAV of the unsaved blend |
  | POST | `/api/blend` | `{a, b, ratio, name, language?, description?, tags?}` → new blended voice (no `dir`) |
  | POST | `/api/clone/drafts/{id}/save` | `{name, language, description?, tags?, engine?, consent: true}` → new My Voices entry (no `dir`) |
  | GET | `/api/library?q=&language=&accent=&gender=&age=&style=&engine=&license=&commercial=` | library voices (all filters optional, combined with AND); adds `license_short`, `preview_url`, `added` (already copied to My Voices) |
  | GET | `/api/library/{id}/preview` | the voice's 5–8 s MP3 preview (cached 1 day) |
  | POST | `/api/library/{id}/add` | copy to My Voices → the new voice (`library_id` kept, preview copied) |
  | GET | `/api/my-voices` | My Voices: full records (no paths) + `preview_url`, `has_preview`, `default`, `allowed_engines` |
  | PATCH | `/api/my-voices/{id}` | edit `name, description, tags, language, accent, gender, age, engine` (validated; other keys → 400). ID never changes |
  | DELETE | `/api/my-voices/{id}` | delete the voice folder; clears the default if it was the default |
  | POST | `/api/my-voices/{id}/duplicate` | `{name?}` → independent copy (samples, caches, preview), name "<name> (copy)" |
  | GET | `/api/my-voices/{id}/preview` | preview clip; made once on first request from a standard sentence if missing |
  | GET/PUT | `/api/default-voice` | `{voice: id|null}`; any My Voices or library ID. A deleted voice reads back as `null` |
  | GET/POST/DELETE | `/api/api-key` | status `{enabled, hint, created}` / make a new key (replaces the old; the key is in this response only) / turn the key off |
  | GET | `/api/voices` (alias `/voices`) `?language=&gender=&tags=` | voices for pickers and agents: My Voices (`origin: mine`) + library (`origin: library`); short cards, no paths or samples. Filters optional, case-insensitive; `tags` comma-separated, a voice must have all |
  | POST | `/api/tts` | `{text, voice, language?=auto, speed?=1.0 (0.5–2), stability?, expressiveness? (0–1), engine?}` → history entry; `voice` = ID or name; max 5000 chars |
  | POST | `/api/speak` (alias `/speak`) | `{text, voice, language?=auto, format?=mp3 (mp3\|wav\|ogg_opus\|flac\|aac\|pcm), stream?=false, speed?, engine?, download?}` → audio bytes in one call (saved to History); headers `X-Voicer-Id`, `X-Voicer-Seconds`; `stream=true` → live chunked stream (see "Live streaming"; `X-Voicer-Sample-Rate` instead of `X-Voicer-Seconds`); errors like `/api/tts` (404 unknown voice, 400 bad input) |
  | POST | `/api/batch` (alias `/batch`) | `{items: [{text, voice?, language?, speed?, engine?, name?}] (1–100), voice?, language?=auto, format?=mp3, zip?=false}` → `{format, count, ok, failed, items: [{index, name, status: ok, id, voice_id, voice, seconds, url, subtitles_url} \| {index, name, status: error, error}]}`; `zip=true` → `voicer-batch.zip` (`001-<name>.<ext>` per ok item + `manifest.json`; 400 if none worked). See `voicer/batch.py` |
  | POST | `/api/batch/parse` | multipart `file` (.txt: one clip per line; .docx: one clip per paragraph; .csv: header row with `text`, optional `voice`, `language`, `filename`; `,` `;` or tab; max 5 MB, 100 clips) → `{count, items}` ready for `/api/batch`. Nothing is spoken. 400 wrong type / no text / too many |
  | POST | `/api/batch/zip` | `{format?=mp3, items: [{id, name?} \| {error, name?}]}` → `voicer-batch.zip` of History clips, same layout as `/api/batch` `zip=true` (numbers follow the list, failed rows only in `manifest.json`). 404 unknown ID, 400 none with an ID |
  | POST | `/api/dialogue` (alias `/dialogue`) | `{script, voices: {speaker: voice ID or name}, language?=auto, speed?=1, gap?=0.4 (0–3 s), format?=mp3, stream?, download?}` → one audio file (saved to History), same headers as `/api/speak`; 400 missing speaker voice / bad script, 404 unknown voice. See "Dialogue" |
  | POST | `/api/voice-changer` (alias `/voice-changer`) | multipart: `file` (any common audio/video, ≤100 MB, 0.5 s–5 min), `voice`, `language?=auto` (for the transcript), `format?=mp3`, `stream?`, `download?` → converted audio (saved to History), same headers as `/api/speak`; 400 bad/short/long/silent file, 404 unknown voice. See "Voice changer" |
  | GET | `/api/history?q=&limit=50&offset=0` | `{total, items}` newest first; `q` matches text, voice name/ID, language, engine (any case); items add `has_subtitles`; limit 1–200 |
  | GET | `/api/remote-access` | this PC only (else 403): `{installed, where (linux\|windows), running, dns_name, ips, serving, funnel, url, api_key_on, port, warnings}` |
  | GET | `/api/dictionary` | pronunciation dictionary `{es: [{word, spoken}], en: [...], count}` (A–Z, case-insensitive) |
  | PUT | `/api/dictionary` | `{language: es\|en, word, spoken, old_word?}` add or change (`old_word` = rename) → the list. 400 bad value/too long/full, 404 unknown `old_word` |
  | DELETE | `/api/dictionary?language=&word=` | remove one word (exact spelling) → the list. 404 unknown |
  | POST | `/api/dictionary/listen` | `{language, text, voice?}` → WAV of `text` with the dictionary applied, not saved to History. Voice: `voice`, else the default voice if it has this language, else `kokoro-ef-dora` / `kokoro-af-heart`. 400 bad language/text (1–300 chars), 404 unknown voice |
  | POST | `/api/subtitles` (multipart `file`, `language?=auto`, `format?=srt`) | SRT or VTT for your own audio/video (0.5 s–10 min, ≤ clone upload limit), Whisper timings; download `<name>.srt` (ASCII name). 400 empty/not audio/silent/too short/too long/no speech/bad language or format. Nothing saved |
  | GET | `/api/dictionary/export` | `voicer-dictionary.csv` (`language,word,spoken`, UTF-8 with BOM for Excel) |
  | POST | `/api/dictionary/import` (multipart `file`, `replace?=false`) | CSV (≤ 1 MB, UTF-8 or Windows-1252, `,`/`;`/tab) → `{imported, es, en, count}`. 400 bad row (names it) / no words / too big; nothing changes |
  | GET | `/api/export?voice=<id>&voice=…&dictionary=true` | backup zip: the listed My Voices (none = all) + dictionary; one voice → `<id>.voicer.zip`, else `voicer-backup-<date>.zip`. 404 unknown or library voice |
  | POST | `/api/import` (multipart `file`) | import a backup zip → `{voices: [{id, name, from_id, renamed}], dictionary_added, dictionary_kept, default_voice}`. 400 bad/unsafe zip (nothing changed) |
  | GET | `/api/auto-backup` | daily auto-backup `{enabled, folder, keep, path, default_folder, last, last_file, last_error, last_try, next, count}` (times = Unix seconds). This PC only (403) |
  | PUT | `/api/auto-backup` `{enabled, folder, keep}` | save; folder empty = `data/backups`, `C:\…` → `/mnt/c/…` under WSL; turned on → folder made and write-tested. 400 bad value. This PC only |
  | POST | `/api/auto-backup/run` | make one auto-backup now. This PC only |
  | GET | `/api/usage?days=30` | usage for the last `days` days (0 = all time; <0 → 400): `{days, since, totals, by_voice, by_agent, by_key, by_channel, by_day}`; each row `{name, requests, characters, seconds, minutes}` (`by_voice` adds `voice_id`) |
  | DELETE | `/api/history/{id}` | delete the clip folder (WAV, encoded copies, subtitles) → `{deleted}` |
  | GET | `/api/history/{id}` | one history entry |
  | GET | `/api/history/{id}/audio?format=wav\|mp3\|ogg_opus&download=` | the clip; `download=true` → attachment `voicer-<id>.<ext>` |
  | GET | `/api/history/{id}/subtitles?format=srt\|vtt&download=` | timed subtitles, one cue per sentence; `download=true` → attachment `voicer-<id>.<srt\|vtt>` |
  | GET | `/api/mcp-config` | `{http_path, tools, stdio}` for the API page snippets; `stdio` = `{python, venv_python, root, module, wsl_distro}` only for requests from this PC, else `null` |
  | WS | `/api/ws/speak` (alias `/ws/speak`) | WebSocket live speech; see "Live streaming" (not in OpenAPI) |
  | POST | `/v1/audio/speech` | OpenAI-compatible text → audio bytes; see "OpenAI-compatible API" |
  | POST/GET/DELETE | `/mcp` | MCP streamable HTTP endpoint (not in OpenAPI). Same API key rules; see "MCP server" |
- UI: sidebar with 12 sections in the order of features.md Phase 5 (pre-existing; order and navigation tested in `test_shell_loads_and_navigates`); unbuilt sections show "Coming soon". Health dot polls `/api/health` every 15 s.
  - Look (2026-10-09): dark navy theme with a blue accent (`--accent #3b82f6`), cards with soft shadows and 14 px corners, buttons with a blue gradient and glow, inputs with a blue focus ring, page tabs (Clone / Blend) as pills. Each sidebar entry has a line icon (`NAV_ICONS` + `navIcon()` in `app.js`; drawn for this app, no icon library); the active entry is a navy pill with a light-blue border. The label stays a plain text node in the link (tests and `text=` selectors find the link itself).
  - Collapse button `#nav-toggle` next to the logo: the sidebar shrinks to icons only (`body.nav-collapsed`, label hidden with `font-size: 0`, name shown as the link's `title`); stored in `localStorage["nav-collapsed"]`; label/aria text in both languages. Hidden on phones (top bar). Test: `tests/test_ui_theme.py::test_sidebar_collapse_button`.
  - Theme: dark colour tokens on `:root` (`color-scheme: dark`), inline SVG favicon (no extra request), visible keyboard focus ring.
  - Responsive: under 700 px the sidebar becomes a top bar that scrolls sideways; the active section is scrolled into view; file rows wrap. No page-level sideways scroll at 390, 768 or 1440 px (tested on every route).
  - Errors: `request()`/`api()` turn network failures into "Cannot reach the server…" and show the API `detail` text for 4xx/5xx. Each action shows its own message next to the control; anything unhandled shows a toast (`#toast`, 6 s).
  - Loading: each slow action shows a status line ("Cleaning audio…", "Generating preview…", "Loading voices…") and disables its buttons while busy.
  - Text to Speech (`#tts`, the start page): text box (max 5000, live character count, Ctrl+Enter), searchable voice list (My Voices then Voice Library; filter on name, ID, accent, language, gender, engine, tags), language Auto/English/Español, Generate → `POST /api/tts`, player for the history audio. Text is kept while you switch sections; the chosen voice is kept in `localStorage["tts-voice"]`.
    Tag buttons (`TTS_TAGS`): pauses are inserted at the cursor; a style button wraps selected text as `[style] … [normal]`, or starts the style at the cursor. Spaces are added only where needed; a tag that would pass 5000 characters is refused with a message.
    Waveform player (`waveformPlayer(src, id)`, reusable): the browser decodes the WAV (`OfflineAudioContext`) into peaks and draws bars on a canvas; played part in the accent colour. Play/pause button, click or drag to seek, keys ←/→ (1 s), PgUp/PgDn (5 s), Home/End, Space. The canvas is an ARIA slider with the time as its value text. If decoding fails, playback still works.
    Download links under the player: MP3, WAV, OGG (WhatsApp voice note).
  - Voice Library (`#library`): search box + selects for language, accent, gender, age, style, engine, license (options built from the data), "Commercial use only" box, "Clear filters", live count. Card grid (auto-fill, min 240 px): name, commercial/non-commercial badge (full license in its tooltip), language · accent · gender · age (`*` + tooltip when estimated), style chips, engine · license link, "▶ Preview" (one shared `Audio`, a second click or another card stops it; stops when you leave the page), "Add to My Voices" (→ "✓ In My Voices", disabled; toast). Values are shown translated (`LIB_VALUES`); language names in their own language like the TTS picker.
  - My Voices (`#voices`): search box + live count, card grid (same card style as the library). Card: name, "★ Default" or kind badge (Cloned/Blend/Preset), language · accent · gender · age, description, tag chips, engine · ID + "Copy" (clipboard API, falls back to select-and-copy; toast), "▶ Preview" (shared player; first play makes the clip), Rename (opens the edit form with the name selected), Edit (inline form: name, description, tags, language, accent, gender, age, engine from `allowed_engines` → `PATCH`; errors show in the form), Duplicate, "Set as default" (`PUT /api/default-voice`; disabled on the default card), Delete (browser confirm → `DELETE`). Empty state links to Clone and Voice Library. The TTS page starts with the default voice until you pick another one in that visit.
  - History (`#history`): search box (one `GET /api/history?q=` 250 ms after typing stops; a newer search wins over a slower older one) + count, list of 30 clips per page with "Load more (N left)". Each clip: voice · language · engine · length · date (`<time>`, local format in the interface language), text (cut to 3 lines above 240 characters, "Show more"/"Show less"), "▶ Play" (shared preview player), download MP3 / WAV / OGG, SRT / VTT (only when the clip has timings), "Use in Text to Speech" (puts text and voice on the TTS page), Delete (browser confirm → `DELETE`; stops it if playing; clears the TTS result if it was that clip). Empty state links to Text to Speech.
  - API & Agents (`#api`): server address (`location.origin`) with Copy; API key box (Off/On + hint and date; Create / Replace (confirm) / Turn off (confirm); a new key is shown once with Copy and a warning); examples in curl and Python (stdlib `urllib`, no install) for list voices, speak → MP3, WhatsApp OGG/Opus, SRT; tab "OpenAI SDK" (Python `openai` package with `base_url=<origin>/v1`, and a `/v1/audio/speech` curl → `note.ogg`) — they use the default voice (else the first My Voice) and add `Authorization: Bearer $VOICER_API_KEY` only when a key is on; endpoint table built from the live `/openapi.json` (method, path, first docstring line; `lang="en"`, not translated) + link to `/docs`. Every code block has a Copy button. The test runs the copied curl and Python examples against the server.
    - MCP card: tool list and tabs HTTP / stdio / Windows with copy-ready config. HTTP: `{"mcpServers": {"voice-studio": {"type": "http", "url": "<origin>/mcp"}}}` (+ `headers.Authorization: "Bearer YOUR_API_KEY"` when a key is on) and the `claude mcp add --transport http …` command. stdio: venv Python, `-m voicer.mcp_server`, `env.PYTHONPATH` = project folder. Windows (Claude Desktop etc.): `wsl.exe -d <distro> --cd <project> .venv/bin/python -m voicer.mcp_server`. stdio/Windows tabs need paths, so they show only on this PC (`GET /api/mcp-config` sends `stdio: null` to other devices). The test connects with each copied config (HTTP, stdio, and the real `wsl.exe` launcher).
  - Interface language: `web/i18n.js` (loaded before `app.js`) holds `I18N.es` (English text → Spanish) and `t(key, vars)` with `{var}` placeholders. The English text is the key, so a missing entry falls back to English. Picker `#ui-lang` in the sidebar; the choice is stored in `localStorage["ui-lang"]` (first visit: browser language, `es*` → Spanish). Changing it sets `<html lang>` and re-renders the current view. Quality warnings are translated from `quality.issues` codes (`ISSUE_TEXT` in `app.js`).
- Tests: `tests/test_server.py` (TestClient), `tests/test_ui_theme.py` (layout sizes, theme, error and loading states), `tests/test_ui_i18n.py` (every `t()` key has Spanish text; no English left on any route in Spanish; choice survives reload), `tests/test_ui_browser.py` (marker `browser`; Voice Library: `test_voice_library_page`, `test_voice_library_phone_layout`, Playwright Chromium with fake mic; it fails on any JS or console error, and a test may drop an error it expects from `page.errors`; fixture `live_server` runs uvicorn in a thread). Playwright is a dev dependency (`requirements/dev.txt`).

### Clone drafts (`data/drafts/<id>/`)
- `draft.json`: `{id, created_at, files: [{name, original, source, seconds, sample_rate, bytes}]}`; `raw/NN_<safe name>` = original bytes, untouched.
- Auto-clean (`clone.process` → `cleanup.clean` + `cleanup.split`): each raw file is cleaned on its own (never joined), output
  `clips/clip_NN.wav` (24 kHz mono PCM16, 10 ms fades). Clips are regenerated from `raw/` every time; raw files are never changed.
  - Speech detection: 20 ms frames louder than max(noise floor + 10 dB, loudest − 40 dB); gaps < 0.15 s closed.
  - Denoise: stationary spectral gating with a noise profile from the non-speech frames (`prop_decrease` 0.85; 0.6 if < 0.25 s of silence).
  - Silence: lead/tail cut to 0.1 s; inner pauses longer than 0.35 s shortened to 0.35 s.
  - Split: cut at the quietest point in each 6–15 s window (prefers ~10 s, never leaves a < 6 s remainder). Files under 15 s stay one clip.
  - UI runs it automatically after every upload, recording or removal.
- Quality meter (`cleanup.measure` per raw file, `cleanup.quality` overall) → draft `quality = {score 0–100, level good/ok/poor, seconds, snr_db, warnings}`.
  - SNR = speech level − 10th-percentile frame level (capped 60 dB). Noisy < 20 dB, bad < 12 dB. Clipping = > 0.1 % samples at full scale. Too quiet = speech < −40 dBFS.
  - Score = 50 % duration (full at 60 s) + 50 % SNR (12→35 dB) − 20 if clipped; capped at 39 ("poor") when < 20 s of speech or SNR < 12 dB.
  - Warnings in plain words: < 20 s, < 1 min, noise, clipping, too quiet.
- Auto-transcribe (`clone.transcribe`): faster-whisper `small` on CPU (int8, keeps VRAM for TTS) runs on each clip without `text`. Each clip gets `text`, `language`; draft `language` = language with the most seconds.
  - Every clip stores `hash` (SHA-1 of its WAV). Re-cleaning keeps `text`/`language`/`edited` for clips with the same audio, so only new clips are transcribed and user edits survive.
  - `clone.set_clip_text` saves a user edit (`edited: true`); transcription never overwrites a clip that already has text.
  - UI calls transcribe after every auto-clean and shows an editable text box under each clip (saved on change).
- Details, preview, save (`clone.as_voice`, `clone.preview`, `clone.save`):
  - The draft's clips act as a temporary voice (`id draft-<id>`, samples `clips/clip_NN.wav`). Preview runs the normal `tts.speak` pipeline → `<draft>/preview.wav`; draft `preview.clips` records which clip set it was made from.
  - Save validates: consent must be `true`, name 1–80 chars, language en/es, description ≤ 500, tags (list or comma string) lower-cased, de-duplicated, ≤ 20 × 30 chars, engine must support cloning (xtts default, f5).
  - Saved voice: `kind cloned`, clean clips → `samples/sample_NN.wav`, `transcripts {sample: text}`, `consent {confirmed, at}`, `preview.wav` only if made from the current clips. Draft gets `saved_voice` and is kept (raw files stay for re-cleaning).
  - F5-TTS reference text = saved clip transcript when the first sample is ≤ 11 s (else Whisper as before); the transcript is part of the F5 cache key.
  - UI card "3 · Details & preview": Save is enabled only after a preview of the current clips, a name and the consent box. After save, the page starts a fresh draft and links to My Voices.

## Job queue (`voicer/jobs.py`)
- Every request that makes audio or runs a model takes a turn: POST `/api/speak` `/speak` `/api/tts` `/api/batch` `/batch` `/api/dialogue` `/dialogue` `/api/voice-changer` `/voice-changer` `/v1/audio/speech` `/api/blend` `/api/blend/preview` `/api/clone/drafts/{id}/process|transcribe|preview|save` `/api/dictionary/listen` `/api/subtitles` (ASGI `QueueMiddleware`, inside the API key check), each WebSocket speech request, and the MCP `speak` tool. Voice previews are not queued (made once, then read from disk); `/api/batch/parse` and `/api/batch/zip` are not queued.
- One job runs at a time (one GPU). Waiting is FIFO and async: a waiting job holds no server thread, so the UI, voice list and History stay fast under load (measured: 80 requests at once → `/api/voices` slowest answer 19.3 s before, 0.85 s after). A streaming reply keeps its turn until the last byte.
- `VOICER_MAX_QUEUE` (default 64) jobs may wait; the next one gets **503** `{"detail": "Server busy: …"}` (OpenAI route: `{"error": {…, "code": "server_busy"}}`) with `Retry-After` = mean job time × jobs ahead (1–300 s). A job that waits longer than `VOICER_QUEUE_TIMEOUT` (default 900 s) gets the same 503. WebSocket: `{"type":"error","status":503,…,"retry_after"}`; MCP: tool error.
- Counts in `/api/health` → `queue`. One queue per server process: the stdio MCP server is a separate process with its own models and its own queue.
- Tests: `tests/test_jobs.py` (order, cancel while waiting, full queue, 60 requests at once against a live server).

## Usage stats (`voicer/usage.py`, `data/usage.jsonl`)
- `history.add` calls `usage.record` after it saves a clip, so every way to make audio is counted once: REST, OpenAI, WebSocket, MCP, batch (one line per clip), dialogue (`voice_id` `dialogue`), voice changer (0 characters). Live streams count when they are saved (a stream the client leaves early is not saved and not counted). Voice previews are not History clips and are not counted.
- One request = one clip. Line: `{t, id, kind (tts|dialogue|voice-changer), voice_id, voice, chars, seconds, channel, agent, key}`. The file is separate from History, so deleting clips keeps the stats. A broken last line (crash while writing) is skipped. A write error loses a stats line, never the clip.
- Who asked: a context variable set per request. HTTP job routes (see Job queue): in the `require_api_key` middleware, channel `rest` or `openai` (`/v1/`). WebSocket: channel `websocket`, after accept. MCP `speak`: channel `mcp` (HTTP) or `mcp-stdio`, agent = the MCP client's own name from `initialize` (`clientInfo.name`). The value reaches the worker thread because Starlette and anyio copy the context into it.
- Agent: header `X-Voicer-Agent` (cleaned, max 60 chars), else the first word of `User-Agent` (`curl/8.5` → `curl`, any `Mozilla/` → `Web browser`), else `Unknown`. Key/device: the API key hint (`vs_…abcd`) if a valid key was sent, else `This PC` (direct local request), else `No key (key off)`. The key itself is never stored.
- UI page `#usage` (`views.usage`): period (24 h / 7 / 30 days / all time, kept in `localStorage["usage-days"]`), three totals (requests, characters, audio minutes) and tables by voice, by app or agent, by API key or device, by connection. Tests: `tests/test_usage.py`, `tests/test_ui_usage.py`, `tests/test_mcp.py` (stdio channel).

## Voice blending (`voicer/blend.py`)
- Mixes two voices' XTTS speaker latents: `gpt_cond_latent` and `speaker_embedding` are averaged with weight `ratio` (share of voice A, 0.05–0.95); the speaker embedding is rescaled to the mixed norm (`engines.xtts.mix_latents`).
- Blendable: XTTS studio speakers (library), cloned voices with samples, and saved blends. Piper/Kokoro presets are not (no XTTS latents).
- Unsaved blend (preview) = voice dict with `blend {a, a_name, b, b_name, ratio}`; XTTS mixes the sources on the fly (cached per blend key).
- Saved blend: `kind blended`, `engine xtts` (only engine allowed), `blend` info, mixed latents in `data/voices/<id>/blend.pt` → keeps working if a source is deleted. A `preview.wav` is made on save.
- License: blend lists the source licenses; `commercial` is true only if every source with a flag allows it.
- UI: "Blend two voices" tab on Clone Voice (`#blend`): two pickers, 5–95 % slider, preview, then Save (enabled only after a preview of the same A/B/ratio).
- Each file must decode as audio (`audio.decode`) or it is removed and reported. Limits: 100 MB per file, 50 files.
- Ids are 12 hex chars; file names are reduced to their base name → no path traversal.
- Mic recording (UI): `getUserMedia` (no echo cancel / noise suppression / AGC, to keep the real voice) → `MediaRecorder`
  (WebM/Opus preferred) → uploaded as `source=mic`. Shows timer and input level. Needs `localhost` or HTTPS (browser rule).
  Blocked mic → clear error message.
- UI keeps the current draft id in `localStorage` (`clone-draft`) so samples survive a page reload; works without storage.

## Voice settings sliders (`Engine.controls`, `engines/base.slider`)
- Every engine lists the sliders it honours in `controls`; `/api/voices` cards include them so the UI disables the rest. Unsupported values sent to the API are ignored and left out of the entry's `settings`.
- 0–1 sliders, 0.5 = the engine's own default (`slider()` maps 0 → low end, 0.5 → default, 1 → high end):
  | Engine | speed | stability | expressiveness |
  |---|---|---|---|
  | XTTS | `speed` | `temperature` 1.0 → 0.3 (a style tag's temperature wins) | `top_p` 0.6 → 1.0 |
  | Piper | `length_scale = 1/speed` | `noise_scale` 2×default → 0 (1.0 = repeatable) | `noise_w_scale` 0 → 2×default (timing variation) |
  | Kokoro, F5 | `speed` | — | — |
- Tests: `tests/test_tts_controls.py`, `tests/test_ui_browser.py::test_tts_sliders_follow_engine_and_reach_api`.

## Output formats (`voicer/formats.py`)
| Format | Container / codec | Rate | Bitrate | MIME |
|---|---|---|---|---|
| `wav` | WAV / PCM 16-bit | engine rate (22.05–24 kHz) | — | `audio/wav` |
| `mp3` | MP3 / libmp3lame | 44.1 kHz | 128 kbps | `audio/mpeg` |
| `ogg_opus` | OGG / libopus (`application=voip`) | 48 kHz | 32 kbps | `audio/ogg` |
| `flac` | FLAC | engine rate | lossless | `audio/flac` |
| `aac` | ADTS / AAC | 44.1 kHz | 128 kbps | `audio/aac` |
| `pcm` | raw s16le, no header | 24 kHz | — | `audio/pcm` |
- All mono. Encoded with PyAV (bundled FFmpeg) on first request, cached beside `audio.wav` (`audio.mp3`, `audio.ogg`); written to a temp name then renamed, so parallel requests never see half a file.
- Where: UI download buttons (TTS page, History), API `GET /api/history/{id}/audio?format=`, MCP `speak(format=…)` (Phase 6 checked: wav/mp3/ogg_opus pre-existing in UI/API; MCP added with the MCP server). `flac`, `aac`, `pcm` were added for the OpenAI-compatible API (also accepted by `?format=`); the UI buttons stay MP3 / WAV / OGG.
- WhatsApp voice note check (`test_ogg_opus_is_a_clean_whatsapp_voice_note`): exactly one Opus stream, mono, 48 kHz, < 64 kbps, `OpusHead` header, decodes with no FFmpeg errors. Not tested inside the WhatsApp app itself (needs a phone and account).
- Tests: `tests/test_formats.py` (ffprobe codec, rate, channels, duration; Whisper on each file), `tests/test_ui_browser.py::test_tts_download_buttons`.

## Subtitles (`voicer/subtitles.py`)
- Timings come from the synthesis itself, not from speech recognition: `tts.speak_timed()` records where each sentence's trimmed audio starts and ends in the joined clip (same sample counts as `concat`, after the lead pause and tagged pauses). Pieces of one long sentence share one timing.
- Cue text is the sentence as typed (before the dictionary and number spelling), tags removed. Cues longer than two lines of 42 characters are cut at spaces; the time is shared by character count.
- Stored per entry as `cues.json` (`[{start, end, text}]`, seconds). Entries without it (none yet) → 404 "has no subtitles".
- TTS page: "Subtitles: SRT · VTT" download links under the audio downloads.
- Tests: `tests/test_subtitles.py` (format, wrapping, each cue's audio slice checked with Whisper, pause gap, numbers as written), `tests/test_ui_browser.py::test_tts_subtitle_links`.
- Your own recording: `subtitles.from_audio(path, language)` decodes it (PyAV; 0.5 s–10 min, not silent), runs Whisper (CPU, `asr.transcribe`, VAD on) and returns one timing per Whisper segment; `render()` makes the SRT/VTT as above. No speech → error. Nothing is saved. API `POST /api/subtitles` (job queue). UI: **Subtitles only (SRT)** on the Voice Changer page (same upload/record, its language select; no voice needed) downloads `<file name>.srt`. Tests: `tests/test_subtitles_audio.py`, `tests/test_ui_changer.py::test_changer_subtitles_only_downloads_an_srt`.

## API key (`voicer/apikey.py`)
- Off by default. When on, an HTTP middleware checks every request except `/`, `/static/*` and `/api/health`.
- Key off: open to this PC and the local network, but a request through a proxy (remote access, e.g. `tailscale serve`) is always refused: 401 "Remote access needs the API key…". So sharing the server on Tailscale exposes nothing until a key exists.
- Accepted as `Authorization: Bearer <key>` (OpenAI style) or `X-API-Key: <key>`. Missing → 401 "API key required…", wrong → 401 "Invalid API key", both with `WWW-Authenticate: Bearer`.
- Requests straight from this PC need no key: loopback client address and no proxy headers (`X-Forwarded-For`, `X-Forwarded-Host`, `X-Forwarded-Proto`, `X-Real-IP`, `Forwarded`, `Tailscale-User-Login`). The Windows browser at `localhost:8765` reaches WSL as 127.0.0.1 (checked), so the UI keeps working.
- Key format `vs_` + 43 URL-safe characters (256 bits). Stored as SHA-256 only, compared in constant time; the UI shows the hint `vs_…abcd`.
- Tests: `tests/test_api_key.py`.

## Backup (`voicer/backup.py`)
- Export zip layout: `voicer-backup.json` (manifest `{format: "voicer-backup", version: 1, app_version, created, voices: [{id, name, kind, engine, files}], dictionary, dictionary_entries, default_voice}`), `voices/<id>/…` (the whole voice folder: `voice.json` with its settings/consent/license, `samples/`, model caches = embeddings such as XTTS latents and F5 references, blend latents, `preview.wav`), `dictionary.json` (both languages).
- Left out: `*.tmp` and hidden files, links, History clips, usage stats, `settings.json` (API key hash). `default_voice` is in the manifest only if that voice is exported.
- Built in a temp file (`voicer-export-*.zip`), sent with `FileResponse`, deleted after sending. Audio/compressed files are stored, the rest deflated.
- UI: My Voices — **Export** on each card, **Export all voices** in the search card (plain download links). Tests: `tests/test_backup.py`.
- Import (`import_zip`, `POST /api/import`; on a VPS: `curl -F file=@backup.zip http://HOST:8765/api/import` with the API key): every entry is checked before anything is written — manifest format and version (newer → "update Voice Studio"), only `voices/<id>/…`, `dictionary.json` and the manifest, valid voice IDs, plain relative paths (no `..`, absolute paths, drives, backslashes or links), at most 20,000 files and 20 GB, no file over 10 MB that unpacks to more than 500× its packed size, enough free disk. Each voice is unpacked in a hidden staging folder in `data/voices/` and then renamed into place; any error removes the voices this import added (all or nothing).
- Import never overwrites: a voice ID that is already here → new ID, name "<name> (imported)", `imported_from`. `voice.json` is cleaned: known fields only (`voices.FIELDS` + id, created_at), `samples`/`preview` kept only if they name a file in the zip. Dictionary words are added; a word you already have keeps your spoken form. The backup's default voice is set only if you have none.
- UI: My Voices — **Import backup** button next to Export all (file picker, message with counts, list reloads). Tests: `tests/test_backup_import.py`.
- Daily auto-backup (`voicer/autobackup.py`), off by default. Settings in `settings.json`: `auto_backup {enabled, folder, keep (1–365, default 7)}` and `auto_backup_state {last_try, last_ok, last_file, last_error}`. A daemon thread (started in the lifespan, one per process) looks 1 min after start and then every 10 min; it backs up when the last good backup is 24 h old, and after a failure waits 1 h before the next try. Each backup is `backup.export` of all voices + dictionary, written as a hidden `.part` file and renamed to `voicer-auto-YYYYmmdd-HHMMSS.zip`; then only the newest `keep` files with exactly that name pattern are kept — no other file in the folder is ever touched. The folder must be a full path and not inside `data/voices`.
- UI: Settings page — **Daily backup** card (on/off, folder, keep the newest N, Save, Back up now, last backup or error, next backup). The card and its API work only on the PC that runs Voice Studio, because they show and choose folder paths. Tests: `tests/test_autobackup.py`.

## Remote access (`voicer/remote.py`, Tailscale)
- Setup (shown step by step on the API page, card "Remote access (Tailscale)"): Tailscale on this Windows PC (or inside WSL) → make the API key → `tailscale serve --bg http://127.0.0.1:8765` (Windows forwards localhost to WSL) → Tailscale on the VPS, same tailnet → the VPS uses `https://<pc>.<tailnet>.ts.net` for REST, `/v1` (OpenAI) and `/mcp`. Stop: `tailscale serve reset`.
- Security: only tailnet devices can connect (not the internet); Tailscale encrypts the link and gives HTTPS; the proxy adds `X-Forwarded-*` / `Tailscale-User-Login`, so the server treats the request as another device and requires the API key (refused even when the key is off). `tailscale funnel` (public internet) is warned against; `/api/remote-access` flags it.
- Links in answers (`/api/batch` URLs, `/api/batch/zip` manifest, MCP `speak` URL) use `remote.public_base`: `X-Forwarded-Proto` / `X-Forwarded-Host` when present, so a VPS gets `https://<pc>.ts.net/...` and not `http://127.0.0.1:8765/...`. MCP `speak` gives no file path to remote clients.
- `/api/remote-access` (this PC only) runs `tailscale status --json` and `tailscale serve status --json` (5 s timeout each) and reports whether a serve handler proxies to this server's port.
- The card's address follows the serve type: HTTPS (default, `https://<pc>.ts.net`) or plain HTTP (`serve --http=80` → `http://<pc>…`; another port is shown).
- Unit tests use a stand-in `tailscale` program for the status JSON and the headers `tailscale serve` adds (`tests/test_remote.py`, `tests/test_ui_remote.py`). End to end: `tests/test_e2e_final.py::test_13` builds a real private tailnet on this PC with no account (see Final end-to-end test).

## MCP server (`voicer/mcp_server.py`)
- Official MCP Python SDK `mcp` 2.3.0 (MIT, https://github.com/modelcontextprotocol/python-sdk), class `MCPServer`. One tool set, two transports:
  - stdio: `.venv/bin/python -m voicer.mcp_server` (the agent starts it; it needs no running web server to speak; the SDK points stray stdout at stderr so model logs cannot break the protocol).
  - streamable HTTP: `http://localhost:8765/mcp`, inside the main FastAPI app. Each server start makes a new SDK session manager (lifespan); `_McpEndpoint` sends requests to the running one.
- Tools:
  - `list_voices(language?, gender?, tag?)` → My Voices then library; short cards (`id, name, language, accent, gender, age, tags, engine, license, commercial, description, origin, default`).
  - `search_voices(query, language?, gender?, tag?, limit=20)` → same cards whose id/name/accent/description/tags contain `query`.
  - `speak(text, voice, language="auto", format="mp3"|"wav"|"ogg_opus", stream=false, speed=1.0)` → `{id, voice, voice_id, language, format, mime, seconds, stream, url, subtitles_url, path?}`. Runs `tts.generate` (saved to History), encodes with `formats.encode`. `url` uses the HTTP request's own address (stdio: `http://localhost:PORT`). `path` (file on this PC) only for stdio and local HTTP clients.
- Bad input (unknown voice, empty text, bad format) → tool error with the plain message, no traceback.
- Guards on `/mcp`: the API key middleware (other devices need the key) and an Origin check: a request with an `Origin` header that is not localhost/127.0.0.1/[::1] gets 403 unless it has a valid key (blocks DNS-rebinding pages in a browser; agents send no Origin).
- Tests: `tests/test_mcp.py` (stdio client: tools, search, WhatsApp-note speak checked with ffprobe + Whisper, errors; HTTP client: filters, speak MP3 + download; Origin 403; key needed through a proxy; no `path` for remote).

## Dialogue (`voicer/dialogue.py`)
- Script: one turn per `Name: text` line (name 1–40 characters, no `:` `[` `]`); a line without `Name:` continues the turn before; blank lines are skipped; text before the first speaker → error with the line number. Names match in any case (`ann:` = `Ann:`, first spelling kept). Max 10 speakers, 5000 characters.
- `generate(script, cast, language, speed, gap)`: every speaker needs a voice (checked before any synthesis). Each turn goes through `tts.speak_timed` (tags, language per sentence, dictionary), is resampled to the first turn's rate (voices may use different engines), levelled to −20 dBFS RMS with the peak under −1 dBFS, and joined with `gap` seconds of silence.
- Saved to History: `text` = the script, `voice_id` = first speaker's voice, `voice_name` = `Dialogue: Ann (Lessac), Ben (Michael)`, `engine` = engines joined with `+`, `settings.dialogue` = speaker → voice ID. Subtitle cues per sentence, prefixed with the speaker (`Ann: …`).
- API: `POST /api/dialogue` (Phase 7).
- UI page `#dialogue` (`views.dialogue` in `app.js`): script box (Ctrl+Enter generates); side card "Speakers" lists each name found (same parse rule as the server, names match in any case) with its own voice select, plus Language and "Pause between turns" (0–2 s). A new speaker gets an unused voice, preferring the other gender in the same language as the speaker before; the first gets the default voice. The cast (lowercase name → voice ID) is kept in `localStorage["dlg-cast"]`. More than 10 speakers disables Generate. Posts `format: "wav"`, then plays/downloads from History through the shared `renderResult` helper (also used by the Voice Changer page). Server errors (e.g. "Line 1 has no speaker") show under the button. Tests: `tests/test_ui_dialogue.py`.
- Tests: `tests/test_dialogue_api.py` (parser; Piper + Kokoro voices in one WAV checked with Whisper; speaker cues; loudness within 6 dB; OGG stream; 7 error cases).

## Voice changer (`voicer/voice_changer.py`, `engines/openvoice.py`)
- Model: OpenVoice v2 tone colour converter (MyShell, MIT, `myshell-ai/OpenVoiceV2`), loaded through `coqui-tts` (`voice_conversion_models/multilingual/multi-dataset/openvoice_v2`; downloaded on first use to the Coqui model folder). ~33 M parameters, ~130 MB VRAM, 22.05 kHz in and out. Managed by the model manager as `openvoice` (lazy load, idle unload; `large = False`, so it may sit next to one large TTS model).
- It swaps the voice colour only: words, timing (same length ±0.1 s), pitch movement and emotion come from the recording. Language independent.
- Target voice reference: a cloned voice's own samples (max 5); any other voice (library, preset, blend) speaks a fixed ~10 s text once (`REF_TEXT`, voice's language) → cached in `data/cache/vc_refs/<id>-<hash>.wav` (hash of the voice record, so an edited blend gets a new clip).
- `convert(path, voice, language, source_name)`: decode (PyAV) → checks (0.5 s–5 min, not silent) → resample to 22.05 kHz (librosa, band-limited) → convert → peak ≤ 0.95 → Whisper transcript of the recording (CPU; `language` auto/en/es) gives the History `text` and one subtitle cue per Whisper segment (no speech → no subtitles, text `(voice changer: <file>)`) → `history.add(engine="openvoice", settings={voice_changer, source, source_seconds})`.
- API: `POST /api/voice-changer` (Phase 7); the upload is written to a temp folder in `data/cache/` and removed after.
- UI page `#changer` (`views.changer` in `app.js`): drop zone / file picker (audio or video; other files are refused in the browser) or **Record from microphone** (its own small recorder `vcRec`, separate from the clone recorder; level meter + timer), a player for the source with **Remove**, the voice list (same search and groups as Text to Speech; choice kept in `localStorage["vc-voice"]`), the recording's language (Auto/English/Español, for the transcript). **Convert** posts the form with `format=wav` (the stored file, no encoding wait), reads `X-Voicer-Id`, loads the History entry and shows the waveform player, MP3/WAV/OGG downloads and SRT/VTT subtitles. The file and the result stay while you switch sections. Tests: `tests/test_ui_changer.py`.
- License: the converter is MIT; the output also carries the license of the target voice's model (e.g. XTTS-based voices stay non-commercial).
- Tests: `tests/test_voice_changer.py` (Piper female → Kokoro male: same length, Whisper words, median pitch moves to the target's; OGG/Opus Spanish note → cloned voice; 9 error cases).

## OpenAI-compatible API (`voicer/openai_api.py`)
- `POST /v1/audio/speech` takes the OpenAI body `{model, input, voice, response_format, speed, stream, stream_format, instructions}` plus our `language` (auto/en/es). Point any OpenAI SDK at `base_url = http://localhost:8765/v1`; `api_key` is ignored on this PC and is the Voice Studio API key for other devices.
  - `voice`: a voice ID or name (My Voices or library), or `{"id": "…"}` (newer SDK shape).
  - `model`: ignored (`tts-1`, `gpt-4o-mini-tts` … all use the voice's own engine) unless it names an engine: `xtts`, `f5`, `kokoro`, `piper`.
  - `response_format`: `mp3` (default), `opus` (= `ogg_opus`, OGG/Opus like OpenAI), `aac`, `flac`, `wav`, `pcm` (raw 16-bit 24 kHz mono like OpenAI). `ogg_opus` also accepted.
  - `speed`: OpenAI range 0.25–4.0 accepted, clamped to our 0.5–2.0.
  - `stream: true` or `stream_format: "audio"` → live stream (each sentence sent as soon as it is spoken, see "Live streaming"); `stream_format: "sse"` → 400.
  - Response: audio bytes with the format's MIME, header `X-Voicer-Id` = History ID (subtitles at `/api/history/{id}/subtitles`).
- Errors use the OpenAI shape `{"error": {"message", "type": "invalid_request_error", "param", "code"}}`: 400 for unknown voice (`code: voice_not_found`), bad format/speed/model/language, empty text, and body validation errors (missing `input`/`voice`) on `/v1/*` paths (other paths keep FastAPI's 422); 401 `invalid_api_key` from the key middleware on `/v1/*`.
- Tests: `tests/test_openai_api.py` (official `openai` SDK 3.26.1, dev only: each format checked with ffprobe + Whisper, raw PCM, voice by name/object, speed clamp, engine via `model`, chunked stream, 9 error cases, key rule), `tests/test_ui_browser.py::test_api_page_key_and_examples_run` (runs the OpenAI SDK and curl snippets).

## Live streaming (`voicer/stream.py`)
- `tts.speak_parts` is the `speak` pipeline one segment at a time (planning at once, so bad input fails early); `tts.join_parts` makes the clip + subtitle cues (`speak_timed` = both, unchanged output).
- `open_stream(text, voice, language, speed, engine, fmt)` checks the request, speaks the first sentence, then returns `({id, format, mime, sample_rate}, bytes iterator)`. So errors are normal 4xx; the first byte arrives after one sentence, not the whole text.
- Each sentence goes out with its following pause (no stall in the player). At the end the whole clip is saved to History under the ID sent in `X-Voicer-Id` / `start` (`settings.stream = true`). Client leaves early → generation stops, nothing saved. Engine error after the first byte → stream ends short and is logged (WebSocket: `{"type":"error","status":500}`).
- `Encoder`: `wav` = 44-byte header with unknown sizes (`0xFFFFFFFF`, standard for live WAV) + 16-bit samples; `pcm` = 16-bit 24 kHz; others = PyAV muxer writing to memory with `flush_packets=1` (OGG: `page_duration` 0.1 s) so each sentence leaves at once.
- HTTP: `POST /api/speak` / `/speak` with `stream=true` and `POST /v1/audio/speech` with `stream=true`. Chunked; headers `X-Voicer-Id`, `X-Voicer-Sample-Rate`.
- WebSocket `ws://localhost:8765/api/ws/speak` (alias `/ws/speak`): send `{text, voice, language?, speed?, engine?, format?=pcm}`; receive `{"type":"start", id, format, mime, sample_rate}`, binary frames, `{"type":"done", id, seconds, url}`. Errors `{"type":"error", status, detail}` keep the socket open; many requests per connection. Auth: same as HTTP (this PC free; else key in `Authorization`/`X-API-Key` header or `?api_key=` for browsers); other-site `Origin` refused (close 1008), like `/mcp`.
- First sentence in pieces (`tts.speak_parts(stream_first=True)`): if the engine can stream (`Engine.streams`; now XTTS) and the sentence has no style tag, `tts.synthesize_stream` yields pieces while the model works — XTTS `inference_stream`, a piece every 12 GPT tokens (~0.5 s of speech; `XTTSEngine.STREAM_TOKENS`). The engine runs in its own thread that holds the model lock for the sentence (the lock is an RLock, so it cannot pass between the server's worker threads); pieces come through a queue. Only the start of that sentence is trimmed (the end is already sent); an empty part then carries its pause. Normal (non-live) generation does not use this, so its output is unchanged.
- First audio for a short sentence (warm model, RTX 2080, median): Piper 0.05 s, Kokoro 0.15 s, XTTS 0.4 s (was 0.9–1.1 s before engine streaming), F5 1.6 s (see Decisions). A cold model adds its load time once (XTTS ~20 s, F5 ~15 s): models load lazily and unload after 10 min idle (features.md rule).
- Tests: `tests/test_stream.py` (first audio < 1 s: Piper, Kokoro, XTTS (gpu); XTTS streamed = saved + Whisper; start-only trim; first bytes < 60 % of total time, ≥ 4 pieces; every format decoded + Whisper; stream = saved History clip; OpenAI live PCM; 4 errors before audio; early leave saves nothing; WebSocket: two paths, PCM + OGG, errors keep the socket, Origin, API key).

## Generation history (`voicer/history.py`, `data/outputs/<id>/`)
- `tts.generate()` validates input, runs `tts.speak()` and stores the result with `history.add()`: `audio.wav` + `cues.json` (sentence timings) + `meta.json` `{id, text, voice_id, voice_name, language, engine, settings, seconds, created}`.
- IDs are `YYYYMMDD-HHMMSS-<6 hex>` (sortable, newest first). Any other ID is a 404 — no path traversal.
- `history.entries()` skips folders with a broken `meta.json` (the list never fails because of one bad entry). `history.search()` filters and pages it.
- Tests: `tests/test_tts_api.py` (Piper, CPU; output checked with Whisper)., `tests/test_history_api.py` (list, search, paging, delete).

## Caching
- **Model loads**: `ModelManager` keeps engine objects and loaded weights until idle (10 min) or until another *large* engine needs the GPU. Kokoro pipelines and Piper voices are cached inside their engines.
- **XTTS latents**: memory dict per voice + disk `voices/<id>/cache/xtts_latents.pt`. Key = SHA-1 of sample names/sizes/mtimes (`samples_key`), so editing samples invalidates it.
- **F5 reference**: `cache/f5_ref.wav` + `f5_ref.txt` + `f5_ref.key` (same key rule).

## Voice record (`voice.json`)
`id, name, kind (preset|cloned|blend), engine, engine_voice, language, accent, gender, age, tags[], license, source_url, commercial, description, samples[], preview, settings{}, created_at`.
Cloned voices default to engine `xtts`.

### My Voices management (`voices.edit`, `duplicate`, `set_default`, `default_id`, `preview_file`)
- `edit` accepts only `EDITABLE` fields; name 1–80, description ≤ 500, tags like cloning (lower-case, unique, ≤ 20), language en/es, gender `female|male|neutral|""`, age `young adult|adult|middle-aged|senior|""`, engine via `allowed_engines`. Editing gender/age/tags removes them from `estimated`.
- `duplicate` copies the whole folder (samples, XTTS/F5 caches, blend latents, preview) to a new ID; `duplicated_from` records the source.
- Default voice lives in `data/settings.json`, not in each voice. `/api/voices` cards carry `default`.
- `preview_file` makes `preview.wav` with `PREVIEW_TEXT[language]` when the voice has no preview (presets created by scripts); a lock stops double work.

### Engine selection
- Each voice stores its `engine`. `voices.allowed_engines(voice)`: presets → only their own engine; cloned/blend → every engine with `supports_cloning` (`xtts`, `f5`).
- Change it with `voices.set_engine(id, engine)` / `voices.update(id, engine=...)` (validated).
- `tts.synthesize(..., engine=...)` overrides for one request (same validation).

## Final end-to-end test (`tests/test_e2e_final.py`)
- Runs the app as a user does: `./start.sh` on a free port with an empty data folder, real models, headless Chromium. One test per features.md item, in order (`test_01_…`). Slow; run alone: `pytest tests/test_e2e_final.py`.
- 01 Library: all 107 previews are MP3, 3–10 s; UI filters (language + engine) and ▶/■ for a Spanish Piper, Spanish Kokoro and English XTTS voice; each preview is heard as speech by Whisper.
- 02 Clone: one 20 s+ synthetic sample (Kokoro `bf_emma` via `/api/speak`) uploaded on Clone Voice → auto clips + transcript → preview → consent → Save; then the Text to Speech page speaks Spanish and English with it (Whisper match > 0.7).
- 03 Blend: Clone Voice → Blend tab, two XTTS library voices at 50/50 → preview (heard as speech) → Save → My Voices has the blend (sources + ratio) → Text to Speech speaks Spanish with it.
- 04 API and MCP: REST `/api/speak` (MP3, saved to History), OpenAI SDK (`opus`), MCP over HTTP (`search_voices`, `speak` → URL) and over stdio (`speak` → file path); every clip checked with Whisper.
- 05 `ogg_opus`: from `/api/speak`, the History download and MCP `speak`; ffprobe: OGG, one Opus stream, mono, 48 kHz, duration = reported seconds; ffmpeg decodes with no errors; Whisper hears the text.
- 06 Streaming latency (warm, median of 3, short sentence, first audio over the network, 2026-10-08): Piper HTTP 0.07 s / WebSocket 0.06 s; Kokoro 0.10 / 0.09 s; XTTS 0.41 / 0.42 s. 8-sentence text (Kokoro): first audio 0.13 s of 0.98 s total. Limit in the test: < 1 s, first < half of total.
- 07 Dictionary + tags: the Dictionary page adds `CDMX` → "Ciudad de México" (es), ▶ plays it; the Text to Speech page says "Vivo en CDMX. [pause 1s] [slow] Me gusta mucho. [normal] [whatever] Adiós." (Kokoro `ef_dora`): Whisper hears "Ciudad de México" and no tag word, ffmpeg finds a 0.9–1.4 s silence, `[slow]` clip ≥ 1.15× longer.
- 08 CSV batch: Batch page, `episode.csv` with 5 rows (Piper/Kokoro/XTTS, es + en, a quoted comma, one row on the page defaults) → MP3 → `episode.zip` with `001-intro.mp3` … and `manifest.json` (right voice per row); every clip in History and heard by Whisper (≥ 0.75).
- 09 Dialogue: Dialogue page, Spanish script Ana (Kokoro `ef_dora`) / Luis (XTTS Luis Moray), 4 turns → one WAV in History; Whisper hears the script (≥ 0.75); SRT cues start with the speaker; median pitch of Ana's cues > Luis's + 40 Hz (librosa pYIN), so the turns really use two voices.
- 10 Voice changer: a Spanish MP3 "voice note" (Piper `es_MX-claude`, female) uploaded on the Voice Changer page → Kokoro `em_alex` (male) → History; same length (± 0.2 s), Whisper hears the words (≥ 0.75), SRT has them; median pitch 188 → 136 Hz (target voice 132 Hz).
- 11 SRT for an audio file: a 3-sentence Spanish MP3 (`programa 12.mp3`) → Voice Changer page → **Subtitles only (SRT)** → `programa_12.srt`; ≥ 3 cues, text matches (≥ 0.85), and Whisper on each cue's own stretch of audio hears that cue's text (≥ 0.6); the API's VTT has the same number of cues.
- 12 Queue: 5 `/api/speak` requests at once (Piper, Kokoro, XTTS, es + en) → all 200, each clip has its own text (Whisper), `/api/health` never shows more than 1 running (peak 4 waiting), done +5, none rejected; `/api/voices` answered in ≤ 0.83 s meanwhile (limit 2 s).
- 13 Tailscale: a private tailnet on this PC: Headscale 0.29.4 (open-source Tailscale control server, BSD-3, github.com/juanfont/headscale) + two Tailscale 1.104.1 nodes (BSD-3, pkgs.tailscale.com) in userspace mode, `voicer-pc` and `other-device`. The PC runs `tailscale serve --bg --http=80 http://127.0.0.1:PORT`; `/api/remote-access` shows it shared, no warnings. The other device (through its node's HTTP proxy, so only via the tailnet) gets 401 without / with a wrong key, speech with the key over `/api/speak` and `/v1/audio/speech` (Whisper checked), batch links on `http://voicer-pc.tailnet.test/...`; after `tailscale serve reset` it cannot connect. The binaries are found through `VOICER_TAILNET_BIN` or PATH, else the test is skipped. Limit: both nodes run on this PC; the HTTPS (`*.ts.net` certificate) path needs a real Tailscale account and was not run.
- 14 Export and re-import: My Voices → **Export** on the cloned voice (zip: manifest + `voices/<id>/` with `voice.json`, samples, embeddings, preview) → **Delete** (confirm) → **Import backup** with that zip → the card is back with the same ID, name, kind and language; every file is byte-identical except `voice.json`, which import rewrites (cleaned) with the same content; the voice then speaks Spanish and English on Text to Speech (Whisper checked). Run alone, it first makes the clone (test 02).

## Decisions
- F5-TTS is not under the 1 s first-audio target (1.6 s for a short sentence): it is a diffusion model that makes the whole sentence at once, and the time is GPU work (32 steps). 16 steps would give ~0.8 s but lower quality, so it was not done silently. For live use pick Kokoro, Piper or XTTS (the default clone engine).
- Live streaming sends audio per sentence (the pipeline's natural unit), not per engine step: every engine works the same and sentence joins stay identical to the saved file. The first sentence is made before the HTTP answer so bad requests still get a clear 4xx. WebSocket key may come as `?api_key=` because browser WebSockets cannot set headers.
- Blending = weighted average of XTTS latents (the standard XTTS approach; no training, instant). Blends store their own latents so they do not depend on the source voices later.
- Cloning requires an explicit consent tick (stored with the voice), and the UI requires a preview of the current clips before Save. The API does not require a preview (scripts/agents), only consent.
- Drafts are kept after save (not deleted) so original recordings are never lost.
- Transcripts are made per clean clip (not per raw file), so each clip has the matching text that reference-based engines (F5-TTS) need.
- Denoise with `noisereduce` (MIT, spectral gating) instead of a neural denoiser: no extra model in VRAM, fast on CPU, fewer artifacts on clean input.
- UI is plain HTML/CSS/JS served by FastAPI (no framework, no build) → tiny download, fast load, nothing to compile.
- Voice gender/age/style are estimated from audio and marked `estimated`, not guessed from voice names (names do not state gender). Users can edit their My Voices copy.
- Port **8765** (START.md has the port masked as `****`; 8765 was free). Override with `VOICER_PORT`.
- Python 3.11 (widest support across coqui-tts, F5-TTS, Kokoro, Piper).
- F5-Spanish model card says CC0 in text but CC-BY-NC-4.0 in metadata → treated as **non-commercial** (safest).
- Kokoro `af_sky` is excluded from the library (name linked to a famous-voice controversy; rule: no voices imitating real people).
- Normalizer is rule-based with `num2words` (already a coqui-tts dependency).
- Language detection is a word-list heuristic, not a model: zero memory, zero download, instant; good for es/en only.
- Tests use XTTS studio speakers (synthetic) as reference audio for cloning — no real-person voices.
- UI translation is a plain JS dictionary, not an i18n library: no extra download, no build step. Server messages (API errors, clean errors, voice/library metadata) stay in English; only interface labels are translated. Quality warnings carry codes so the UI can translate them.
- Text to Speech results are always saved to history (like ElevenLabs). Max 5000 characters per request, speed 0.5–2.0.
- Stability/expressiveness are offered only where an engine has a real native control (XTTS sampling, Piper noise). Kokoro and F5 get speed only rather than a fake slider.
- MP3 128 kbps / 44.1 kHz (common default). OGG/Opus mono 48 kHz at 32 kbps with the VoIP profile: speech-tuned, small, the format WhatsApp uses for voice notes.
- Subtitle timings are measured during synthesis (exact, free) instead of running Whisper alignment afterwards (slower, needs a model in VRAM, can mishear). One cue per sentence; long sentences cut to the common 2 × 42-character limit.
- Voice Library page loads the whole library once (`GET /api/library`, ~107 voices) and filters in the browser: no request per keystroke. The API filters stay for agents and scripts.
- Default voice is an app setting (`data/settings.json`), so setting a new default changes one value instead of rewriting voice files. Deleting a voice never leaves a broken default (`default_id()` checks the voice still exists).
- My Voices preview clips are made lazily on first play (not at startup or save) — no GPU work until someone listens.
- My Voices edits are inline in the card (no modal dialog): fewer moving parts, works on phones, keyboard friendly. Delete uses the browser `confirm()` because it removes files and cannot be undone.
- The default voice wins over the voice remembered in this browser (`localStorage`) when the TTS page opens: setting a default is an explicit choice. Picking a voice in the list still wins for that visit.
- History searches and pages on the server (`q`, `limit`, `offset`), unlike the library: history grows without limit, the library is a fixed ~107 voices.
- API key: only "other devices" need it — the local UI and local agents stay zero-setup, like other local AI servers; anything reaching the server through a proxy or the network must send the key. Hash-only storage, like GitHub tokens: a lost key is replaced, not recovered. A browser on another device cannot send the key yet (audio links cannot carry headers) — planned with remote access (Phase 10, e.g. a cookie login).
- The endpoint list on the API page is read from the live OpenAPI schema, so new endpoints (Phase 7) show up without UI changes. API reference text stays English (it is code documentation); the page around it is translated.
- MCP uses the official SDK (MIT) rather than a hand-written JSON-RPC server: it follows the spec as it changes. HTTP MCP lives inside the main server (same port, same API key) instead of a second port. The SDK's Host-header check is off for `/mcp` because remote access (Tailscale) uses other host names; the API key and the Origin check protect it instead.
- MCP `speak` returns a URL always and a file path only to local clients: a path on this PC is useless to (and should not be shown to) other devices. `stream=true` is accepted now and means "give me a URL to play"; the clip is finished first (MCP tool results are one message; for live audio use `/api/speak` with `stream=true` or the WebSocket).
- Voice changer model: OpenVoice v2 (MIT) over Seed-VC (GPL-3.0) and kNN-VC: permissive license, already supported by the installed `coqui-tts` (no new package), small enough to share the GPU, keeps timing exactly. Reference clips for non-cloned voices are made with the voice itself, so every voice in the app can be a target.
- Dialogue page: the browser remembers voice choices per speaker name, so the same script names keep their voices across sessions (decision: browser storage, not the server, because it is a per-viewer convenience).
- Dialogue turns are levelled to one loudness because voices from different engines come out at very different volumes; a listener should not have to ride the volume between speakers.
- Batch page (`#batch`, `views.batch`): upload → `/api/batch/parse` → list of clips (name, text, own voice/language) → Generate sends one `/api/batch` request per clip so the progress bar moves after each clip and Stop takes effect between clips → Download ZIP posts the History IDs to `/api/batch/zip`, saved as `<file name>.zip`. Side card: Voice (for clips without one, kept in `localStorage["batch-voice"]`), Language, Format. Tests: `tests/test_batch_files.py`, `tests/test_ui_batch.py`.
- Batch files are read on the server with the standard library (`.docx` = zip + XML; no extra package). A .docx with a text part over 20 MB unpacked is refused (zip bomb). Text files are read as UTF-8, else Windows-1252 (old Notepad files). CSV separator is detected (`,` `;` tab) because Excel in Spanish saves with `;`.
- Backup (decision): one plain zip with the voice folders as they are on disk plus a JSON manifest, so a backup can be checked or restored by hand, and new cache files are included without code changes. The API key is never exported: a new PC makes its own.
- Import (decision): the safest merge — add, never overwrite or delete. An ID clash gives a copy, your dictionary words and default voice win, and a bad or unsafe zip changes nothing. No restore of History, usage stats or settings.
- Auto-backup (decision): off by default (optional feature, uses disk space); one timer thread with a 10-minute check instead of a cron job, so it works the same on Windows/WSL and a VPS and catches up after the PC was off; pruning deletes only files that match the app's own auto-backup name, so a shared folder is safe; settings are this-PC-only because a remote client must not choose where files are written.
- Install (decision): `uv` + a plain `.venv` (fast, no system Python changes, same tool used to build the dev setup) and a version lock taken from the tested environment, so a new PC or VPS gets exactly the tested versions. Bash scripts only: the app runs in WSL/Linux; Windows reaches it through WSL's localhost forwarding. The start script runs in the foreground (no hidden daemon), which is the simplest to stop and to debug.
- Windows shortcut (decision): a `.lnk` to `wsl.exe` (always present on WSL PCs; no extra launcher, no `.bat`/`.vbs`) that runs `start.sh --open`. The window is minimized, not hidden, so the user can see it runs and close it to stop. Shortcut file on the Windows drive (a `\\wsl$` target gives a security prompt). Made by a script, not by the installer, so `install.sh` stays the same on a VPS.
- README (decision): only copy-ready commands that are run by `tests/test_readme.py` (curl, OpenAI SDK, MCP HTTP config) against a test server, so the README cannot go out of date silently; all other detail stays in this file and in the API & Agents page.
- Dictionary API (decision): the Dictionary sidebar page was still "Coming soon", so the final test item "test a dictionary word" could not be done by a user; the API + page were added first (split in features.md). CSV import accepts `;` and Windows-1252 because Spanish Excel saves CSV that way; an import with no words is refused so `replace` can never empty the dictionary by mistake. Listen uses the default voice only when it speaks the word's language (a Spanish word read by an English voice is useless); the page has no "replace all" import, the safer choice (the API keeps it).
- Tailscale test (decision): a real Tailscale account needs a sign-in by you, so the "another device" check uses Headscale (the standard self-hosted, open-source control server) and a second Tailscale node with its own network stack. It runs the same Tailscale software and `tailscale serve` path as a real tailnet, except the HTTPS certificate. The downloaded binaries are not part of the app.
- Subtitles for an audio file (decision): features.md's final check "Generate SRT for an audio file" had no feature behind it (subtitles existed only for clips made here, and via the voice changer, which changes the voice). Added `POST /api/subtitles` + a button on the Voice Changer page, which already has the upload/record UI and the recording-language select; no new sidebar page. Limit 10 min because Whisper runs on the CPU and the request holds a queue slot.
- UI look (decision, 2026-10-09): restyled to match the MeetAI dashboard you showed (shadows, round corners, glow, blue selected tab); "minimize / maximize" was read as the sidebar collapse button, because a browser page cannot minimize its own window. CSS only plus icons and the toggle; no page markup or test IDs changed. Main content now uses up to 1440 px wide (was 1100 px) so wide screens have less empty space; the width limit is on the page content, not on the scroll area, so the page scrollbar stays at the right edge of the window (test_ui_theme.py::test_page_scrollbar_is_at_window_edge); the text box on Text to Speech and Dialogue grows to the height of the settings column.
- Auto-start (decision): the per-user Startup folder (runs at sign-in) instead of a Task Scheduler task at boot. A boot task that runs before sign-in needs the Windows password stored or admin rights, and WSL normally runs per user. Startup-folder items need no admin, are easy to see and remove (Task Manager → Startup apps), and are off unless the user runs `autostart on`.
- Remote access (decision): Tailscale `serve` (tailnet only, HTTPS, no open router port, no new code in the server) over binding the server to a public IP, a VPN of our own, or Tailscale Funnel. The server does not run Tailscale itself; the user runs one command. Proxied requests need the key even when the key is off: safe by default.
- Usage stats (decision): counted at the one place every clip passes (`history.add`) into an append-only JSON-lines file, not a database: no new package, safe to append from many threads under a lock, easy to read or delete by hand. Grouped on each request (fast for years of normal use; one line ≈ 250 bytes). Agents are named by the `X-Voicer-Agent` header, User-Agent, or the MCP client name, because there is one API key, so the key alone cannot tell apps apart.
- Job queue (decision): refuse with 503 + Retry-After when 64 jobs wait, instead of an unbounded queue; agents get a clear "try later" at once rather than a timeout minutes later. All speech jobs share one turn (also CPU engines like Piper), because the model manager already ran them one at a time; the queue only makes the waiting cheap and visible.
- Batch runs items one by one (one large model in VRAM; the GPU is the limit, not the request count) and keeps going when an item fails, reporting the error in its place: one typo in 100 lines should not throw away 99 clips. Items without a voice fall back to the batch voice, then the default voice. ZIP is stored, not compressed (audio is already compressed).
- `/speak`, `/voices`, `/batch`, `/dialogue` and `/voice-changer` are short aliases of `/api/speak`, `/api/voices`, `/api/batch`, `/api/dialogue` and `/api/voice-changer` (features.md names); only the `/api/…` names are in the OpenAPI schema and endpoint table, so each endpoint is listed once.
- OpenAI-compatible API: `model` is ignored unless it names an engine, because OpenAI model names mean nothing here and clients often hard-code `tts-1`. OpenAI voice names (`alloy`, `nova` …) are not mapped to our voices: a made-up mapping would surprise users; they get a clear `voice_not_found` error instead. Speed outside 0.5–2.0 is clamped instead of rejected, so OpenAI clients that send valid OpenAI values never fail. SSE streaming is refused with a clear error rather than faked.
- MCP config for Windows desktop apps starts the stdio server through `wsl.exe` (checked from WSL with the real launcher) instead of asking users to install Python on Windows. The HTTP config is the first tab: it needs no paths and works from any device.
