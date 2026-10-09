# Voice Studio — Features

Local ElevenLabs-style voice studio. Build in phases. Tick `[x]` when a feature is built AND tested.

## Environment
- Windows PC, WSL2 (Ubuntu). NVIDIA RTX 2080, 8 GB VRAM, 32 GB RAM (often 85% used — keep memory low).
- Verify CUDA in WSL2 before anything else.
- Load models lazily; unload after 10 min idle. Only one large model in VRAM at a time.
- UI and API reachable from Windows at `http://localhost:PORT`.

## Rules
- Use only voices and models with a clear open license. Record license + source for each.
- Never include voices that imitate real or famous people.
- Test each feature end to end before ticking it. Fix all errors before moving on.
- Keep a short `PROGRESS.md` log: what was done, what is next, known issues.

---

## Phase 1 — Core engine
- [x] XTTS-v2 (maintained fork `coqui-tts`): cloning, es + en cross-lingual. Default for cloned voices.
- [x] F5-TTS: optional cloning engine (English base + Spanish fine-tuned checkpoint).
- [x] Kokoro TTS (Apache 2.0): preset voices, English and Spanish.
- [x] Piper TTS: preset voices (es_MX, es_ES, en_US, en_GB).
- [x] Engine selectable per voice.
- [x] Cache voice embeddings and model loads.

## Phase 2 — Natural speech
- [x] Language auto-detect per sentence (es/en); support mixed text; manual override.
- [x] Text normalization per language: numbers, dates, currency (MXN, USD), times, abbreviations, URLs.
- [x] Split long text into sentences; join with natural pauses; no cut words.
- [x] Pronunciation dictionary: word → spoken form, per language (e.g. "Fami" → "Fah-mee", "WhatsApp" → "guatsap" in Spanish). Applied before TTS. CSV import/export.
- [x] Text tags: `[pause 0.5s]`, `[pause 1s]`, `[slow]`, `[fast]`, `[whisper]`, `[happy]`, `[sad]`, `[excited]`. Apply what each engine supports; never speak unsupported tags.

## Phase 3 — Free voice library
- [x] Search the internet for free open-license voices in English and Spanish: Kokoro, Piper, XTTS-v2 studio speakers, others found.
- [x] 30+ voices total; at least 10 Spanish (prefer Mexican/LatAm) and 10 English.
- [x] Per voice: name, language, accent, gender, age range, style tags (warm, narrator, news, conversational, energetic, calm), engine, license, source URL, "commercial OK" / "non-commercial".
- [x] Pre-generated 5–8 s preview clip per voice.
- [x] Script to add more voices later.
- [x] `LICENSES.md` listing every voice and model.

## Phase 4 — Voice cloning
- [x] Upload (drag-and-drop) or record from mic in browser.
  - [x] Web server + UI page on localhost:8765, reachable from Windows.
  - [x] Upload audio files (drag-and-drop) into a new clone draft.
  - [x] Record from the mic in the browser into the clone draft.
- [x] Auto-clean: mono WAV, trim silence, denoise, normalize, split into 6–15 s clips.
- [x] Quality meter; warn if noisy or under 20 s (1–3 min ideal).
- [x] Auto-transcribe with faster-whisper.
- [x] Name, language, description, tags. Preview before save.
- [x] Voice blending: mix two voices into a new one with a ratio slider (e.g. 70/30).

## Phase 5 — Interface (ElevenLabs-style UX)
- [x] Clean, modern, dark theme. Labels in Spanish and English. Fast, responsive, no clutter. Loading states and clear errors. — all sub-items done
  - [x] Dark theme, responsive layout (phone to desktop), loading states, clear errors.
  - [x] UI language switch: every label in English and Spanish.
- [x] Sidebar: Text to Speech, Voice Library, My Voices, Clone Voice, Voice Changer, Dialogue, Batch, Dictionary, History, API & Agents, Usage, Settings. — pre-existing
- [x] Text to Speech: large text box, character count, searchable voice picker, language (auto/es/en), sliders (speed, stability/variation, expressiveness where supported), tag buttons, Generate, waveform player, download (MP3, WAV, OGG/Opus), SRT/VTT option.
  - [x] TTS API: `POST /api/tts` saves each result to history; `GET /api/voices` lists voices for the picker.
  - [x] Page: large text box, character count, searchable voice picker, language (auto/es/en), Generate, player.
  - [x] Sliders: speed, stability/variation, expressiveness where supported.
  - [x] Tag buttons that insert text tags.
  - [x] Waveform player.
  - [x] Download MP3, WAV, OGG/Opus.
  - [x] SRT/VTT option.
- [x] Voice Library: card grid, play-preview, filters (language, accent, gender, age, style, engine, license), search, "Add to My Voices".
  - [x] Library API: `GET /api/library` (search + filters), `GET /api/library/{id}/preview`, `POST /api/library/{id}/add`.
  - [x] Page: card grid, play preview, search, filters, "Add to My Voices".
- [x] My Voices: cards with preview, edit, rename, delete, duplicate, set default, copy voice ID.
  - [x] My Voices API: list, edit/rename, delete, duplicate, set default, preview (made on demand).
  - [x] Page: cards with preview, edit, rename, delete, duplicate, set default, copy voice ID.
- [x] History: text, voice, date, replay, download, delete.
  - [x] History API: `GET /api/history` (newest first, search, paging), `DELETE /api/history/{id}`.
  - [x] Page: list with text, voice, date, replay, download, delete.
- [x] API & Agents: endpoints, API key, copy-ready curl/Python examples, MCP config snippet.
  - [x] Optional API key: off by default; create / replace / turn off; stored as a hash; other devices must send it.
  - [x] Page: endpoint list, API key box, copy-ready curl/Python examples.
  - [x] MCP server (stdio + HTTP) — the Phase 7 item, done here because the page needs it.
  - [x] Page: MCP config snippet.

## Phase 6 — Output formats
- [x] MP3, WAV. — pre-existing (UI, API, MCP)
- [x] WhatsApp voice notes: `ogg_opus` (OGG, Opus, mono, 48 kHz). Must play as native WhatsApp voice note. In UI, API and MCP. — pre-existing in UI/API; MCP added
- [x] Subtitles: auto-generate timed SRT/VTT with each audio. — pre-existing

## Phase 7 — API for agents
- [x] OpenAI-compatible: `POST /v1/audio/speech` {model, input, voice, response_format, speed, stream}. `voice` = name or ID.
- [x] `POST /speak` {text, voice, language?, format?, stream?}.
- [x] `GET /voices` with filters (language, gender, tags).
- [x] `POST /batch`, `POST /dialogue`, `POST /voice-changer`. — split into the three items below; all done
  - [x] `POST /batch`.
  - [x] `POST /dialogue` (needs the Phase 9 dialogue feature).
  - [x] `POST /voice-changer` (needs the Phase 9 voice changer).
- [x] Optional API key. — done with Phase 5 API & Agents
- [x] MCP server (stdio + HTTP). Tools: `list_voices`, `search_voices`, `speak(text, voice, language?, format?, stream?)` → file path or URL. — done with Phase 5 API & Agents

## Phase 8 — Streaming
- [x] Stream audio chunks as generated (HTTP chunked + WebSocket).
- [x] Target first audio under 1 s for short sentences. — Piper 0.05 s, Kokoro 0.15 s, XTTS 0.4 s; F5 1.6 s documented

## Phase 9 — Advanced features
- [x] Voice changer (speech-to-speech): record or upload speech, output in another voice keeping emotion and timing (e.g. OpenVoice v2 tone converter or Seed-VC — check license). — UI page + API; OpenVoice v2 (MIT)
- [x] Multi-speaker dialogue: script with `Speaker A:` / `Speaker B:` lines, assign voice per speaker, one output file. — UI page + API
- [x] Batch mode: upload .txt, .docx, or CSV (text, voice, language, filename). Progress bar. Download as zip. — UI page; /api/batch/parse + /api/batch/zip

## Phase 10 — Scale and access
- [x] Job queue: handle many agent requests at once without crashing; GPU jobs run one at a time. — voicer/jobs.py; 503 + Retry-After when full
- [x] Usage stats: requests, characters, audio minutes per voice and per agent/API key. — voicer/usage.py; GET /api/usage; Usage page
- [x] Remote access via Tailscale so agents on a VPS can use the server securely. — tailscale serve + API page card; key always required through it

## Phase 11 — Backup
- [x] Export one voice or all voices (samples, embeddings, settings, dictionary) as one zip. — GET /api/export; Export buttons on My Voices
- [x] Import zip on another PC or VPS. — POST /api/import; Import backup button on My Voices
- [x] Optional daily auto-backup to a folder. — Settings page card; /api/auto-backup; voicer/autobackup.py

## Phase 12 — Delivery
- [x] One install script, one start script. — install.sh, start.sh, requirements/lock.txt
- [x] Windows desktop shortcut: starts server and opens UI. — done
- [x] Optional auto-start on Windows boot. — done (at sign-in; see ARCHITECTURE)
- [x] Short `README.md` (under 50 lines): start, browse library, clone voice, API examples, MCP config. — done

## Final end-to-end test
- [x] Browse library and play previews. — done
- [x] Clone a voice from a sample; generate Spanish and English. — done
- [x] Blend two voices. — done
- [x] Call API and MCP tool. — done
- [x] Confirm `ogg_opus` with ffprobe. — done
- [x] Measure streaming latency. — done (Piper 0.07 s, Kokoro 0.10 s, XTTS 0.41 s)
- [x] Test a dictionary word and text tags. — done
  - [x] Dictionary API: list, add/change, delete, CSV import/export (the Dictionary page was "Coming soon"). — done
  - [x] Dictionary page: words per language, add/change/delete, CSV import/export, listen. — tests/test_ui_dictionary.py
  - [x] End-to-end: a dictionary word and text tags. — test_e2e_final.py::test_07
- [x] Run a 5-row CSV batch. — test_e2e_final.py::test_08
- [x] Generate a 2-speaker dialogue. — test_e2e_final.py::test_09
- [x] Run voice changer. — test_e2e_final.py::test_10
- [x] Generate SRT for an audio file. — done
  - [x] Subtitles for your own audio file (there was no way): `POST /api/subtitles` and "Subtitles only (SRT)" on the Voice Changer page. — tests/test_subtitles_audio.py, tests/test_ui_changer.py
  - [x] End-to-end: SRT for an audio file. — test_e2e_final.py::test_11
- [x] Send 5 parallel API requests; confirm queue handles them. — test_e2e_final.py::test_12
- [x] Access from another device via Tailscale. — test_e2e_final.py::test_13 (private Headscale tailnet on this PC; HTTPS path needs your Tailscale account)
- [x] Export and re-import a voice. — test_e2e_final.py::test_14
