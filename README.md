# Voice Studio

Local text-to-speech and voice cloning for English and Spanish. Web UI, REST API, OpenAI-compatible API and MCP tools.
Runs in WSL2 / Linux; open it from Windows at http://localhost:8765. Details: `ARCHITECTURE.md`. Licenses: `LICENSES.md`.

## Start
```bash
./install.sh            # once (add --cpu on a PC or VPS without an NVIDIA GPU)
./start.sh --open       # starts the server and opens the browser; Ctrl+C stops it
./windows.sh shortcut   # optional: "Voice Studio" icon on the Windows desktop
./windows.sh autostart on   # optional: start the server when you sign in to Windows
```
Models download on first use. Port: `VOICER_PORT=9000 ./start.sh`.

## Browse the library
Open **Voice Library**. Filter by language, accent, gender, style or license, press ▶ to hear a preview,
then **Add to My Voices**. Only open-license, synthetic voices are listed (no imitations of real people).

## Clone a voice
Open **Clone Voice** → add clean speech of one speaker (at least 20 s, 1–3 minutes is best; upload or record) → check the cleaned clips
and their text → type a test sentence → name the voice, tick the consent box → **Save voice**.
Clone only voices you own or have permission to use. Mix two voices in the **Blend** tab.

## API
```bash
curl -X POST localhost:8765/api/speak -H 'Content-Type: application/json' \
  -d '{"text": "Hola, ¿qué tal?", "voice": "kokoro-ef-dora", "format": "mp3"}' -o hola.mp3
curl 'localhost:8765/api/voices?language=es'      # voice IDs for "voice"
```
OpenAI SDK: `OpenAI(base_url="http://localhost:8765/v1", api_key="x").audio.speech.create(model="tts-1", voice="kokoro-af-heart", input="Hi")`.
From another device: make an API key on **API & Agents** and send `Authorization: Bearer <key>`.
All endpoints: http://localhost:8765/docs

## MCP (agents)
Tools: `list_voices`, `search_voices`, `speak`. HTTP (server running):
```json
{"mcpServers": {"voice-studio": {"type": "http", "url": "http://localhost:8765/mcp"}}}
```
Or `claude mcp add --transport http voice-studio http://localhost:8765/mcp`.
The **API & Agents** page shows copy-ready configs, also for stdio and Windows desktop apps (through `wsl.exe`).

## Backup
**My Voices** → Export all / Import backup. Daily automatic backup: **Settings**.
