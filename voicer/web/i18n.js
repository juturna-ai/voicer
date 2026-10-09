// UI labels in English (the keys) and Spanish. t("Added {n} file(s).", { n: 2 }) → current language.
const I18N = {
  es: {
    // shell
    "Text to Speech": "Texto a voz", "Voice Library": "Biblioteca de voces", "My Voices": "Mis voces",
    "Clone Voice": "Clonar voz", "Voice Changer": "Cambiador de voz", "Dialogue": "Diálogo", "Batch": "Lotes",
    "Dictionary": "Diccionario", "History": "Historial", "API & Agents": "API y agentes", "Usage": "Uso",
    "Settings": "Ajustes", "Not found": "No encontrado", "Coming soon.": "Próximamente.",
    "Server ok · v{v}": "Servidor ok · v{v}", "Server offline": "Servidor desconectado", "Server status": "Estado del servidor",
    "Interface language": "Idioma de la interfaz", "Collapse menu": "Contraer menú", "Expand menu": "Expandir menú",
    "Cannot reach the server. Is Voice Studio still running?": "No se puede conectar con el servidor. ¿Sigue abierto Voice Studio?",
    "Something went wrong: {m}": "Algo salió mal: {m}",
    // clone: samples
    "From samples": "Desde muestras", "Blend two voices": "Mezclar dos voces",
    "Add samples of one speaker. Only clone voices you own or have permission to use.":
      "Añade muestras de una sola persona. Clona solo voces propias o con permiso.",
    "1 · Add samples": "1 · Añadir muestras", "Samples": "Muestras",
    "Drop audio files here": "Suelta aquí los archivos de audio",
    "or click to browse · WAV, MP3, M4A, OGG, FLAC, WebM · 1–3 minutes of clean speech is ideal":
      "o haz clic para elegir · WAV, MP3, M4A, OGG, FLAC, WebM · lo ideal es 1–3 minutos de voz limpia",
    "{n} file(s) · {t} total": "{n} archivo(s) · {t} en total",
    "Remove": "Quitar", "Remove {name}": "Quitar {name}",
    "Uploading {n} file(s)…": "Subiendo {n} archivo(s)…", "Added {n} file(s).": "{n} archivo(s) añadido(s).",
    "Some files were skipped: {list}": "Se omitieron algunos archivos: {list}",
    "Upload failed: {m}": "Error al subir: {m}", "Could not remove the file: {m}": "No se pudo quitar el archivo: {m}",
    // clone: recording
    "● Record from microphone": "● Grabar con el micrófono", "■ Stop": "■ Detener", "Input level": "Nivel de entrada",
    "This browser cannot record audio here. Open the page at http://localhost:8765 (mic needs localhost or HTTPS).":
      "Este navegador no puede grabar aquí. Abre la página en http://localhost:8765 (el micrófono necesita localhost o HTTPS).",
    "Microphone access was blocked. Allow it in the browser and try again.":
      "Se bloqueó el acceso al micrófono. Permítelo en el navegador y vuelve a intentarlo.",
    "Cannot open the microphone: {m}": "No se puede abrir el micrófono: {m}",
    "Recording… read naturally in one voice, in a quiet room.": "Grabando… lee con naturalidad, con una sola voz y en un lugar tranquilo.",
    "Recording {n}": "Grabación {n}",
    // clone: clips + quality
    "2 · Cleaned clips": "2 · Clips limpios",
    "Automatic: mono WAV, silence trimmed, noise reduced, volume levelled, split into 6–15 s clips.":
      "Automático: WAV mono, silencios recortados, ruido reducido, volumen igualado, cortado en clips de 6–15 s.",
    "Cleaning audio…": "Limpiando el audio…", "Cleaning failed: {m}": "Error al limpiar: {m}",
    "Skipped: {list}": "Omitidos: {list}", "{n} clip(s) · {t} of clean speech": "{n} clip(s) · {t} de voz limpia",
    "Clips appear here after you add samples.": "Los clips aparecen aquí cuando añades muestras.",
    " · transcribing…": " · transcribiendo…", "Transcribing…": "Transcribiendo…",
    "Transcription failed: {m}": "Error al transcribir: {m}",
    "No speech recognised — type what is said": "No se reconoció voz: escribe lo que se dice",
    "Transcript of {name}": "Transcripción de {name}", "Could not save transcript: {m}": "No se pudo guardar la transcripción: {m}",
    "Quality": "Calidad", "Good": "Buena", "Okay": "Aceptable", "Poor": "Baja",
    "{t} of speech (ideal 1–3 min) · noise: {snr} dB SNR": "{t} de voz (ideal 1–3 min) · ruido: {snr} dB SNR",
    "Only {seconds} s of speech. Add more: at least 20 s, ideally 1–3 minutes.":
      "Solo {seconds} s de voz. Añade más: al menos 20 s, idealmente 1–3 minutos.",
    "{seconds} s of speech. It works, but 1–3 minutes gives a closer match.":
      "{seconds} s de voz. Funciona, pero con 1–3 minutos el parecido es mayor.",
    "{file}: background noise is noticeable ({snr_db} dB SNR). Record in a quieter place if you can.":
      "{file}: se nota ruido de fondo ({snr_db} dB SNR). Graba en un lugar más tranquilo si puedes.",
    "{file}: background noise is high ({snr_db} dB SNR). Record in a quieter place if you can.":
      "{file}: hay mucho ruido de fondo ({snr_db} dB SNR). Graba en un lugar más tranquilo si puedes.",
    "{file}: audio is distorted (clipping). Record a little further from the mic.":
      "{file}: el audio está distorsionado (saturación). Graba un poco más lejos del micrófono.",
    "{file}: very quiet recording. Move closer to the mic.": "{file}: grabación muy baja. Acércate al micrófono.",
    // clone: details
    "3 · Details & preview": "3 · Detalles y prueba", "Name": "Nombre", "Language": "Idioma",
    "Tags (comma separated)": "Etiquetas (separadas por comas)", "warm, narrator": "cálida, narrador", "Engine": "Motor", "Description": "Descripción",
    "Preview text": "Texto de prueba", "Optional": "Opcional", "e.g. My narrator voice": "p. ej. Mi voz de narrador",
    "Leave empty for a standard sentence": "Déjalo vacío para usar una frase estándar",
    "XTTS-v2 (recommended)": "XTTS-v2 (recomendado)", "▶ Preview": "▶ Escuchar prueba",
    "This is my voice, or I have permission from the speaker to clone it.":
      "Es mi voz, o tengo permiso de la persona para clonarla.",
    "Save voice": "Guardar voz", "Add samples first.": "Primero añade muestras.",
    "Listen to a preview before you save.": "Escucha una prueba antes de guardar.",
    "Give the voice a name.": "Ponle un nombre a la voz.",
    "Confirm you have the right to clone this voice.": "Confirma que tienes derecho a clonar esta voz.",
    "Ready to save.": "Lista para guardar.",
    "Generating preview… (the first one loads the model and can take a minute)":
      "Generando prueba… (la primera carga el modelo y puede tardar un minuto)",
    "Preview ready.": "Prueba lista.", "Preview failed: {m}": "Error en la prueba: {m}",
    "Saving…": "Guardando…", "Save failed: {m}": "Error al guardar: {m}",
    "Saved “{name}” to My Voices (ID {id}). ": "“{name}” guardada en Mis voces (ID {id}). ",
    "Open My Voices": "Abrir Mis voces",
    // blend
    "Mix two voices into a new one. Works with cloned voices and XTTS library voices.":
      "Mezcla dos voces en una nueva. Funciona con voces clonadas y voces XTTS de la biblioteca.",
    "Voice A": "Voz A", "Voice B": "Voz B", "Mix": "Mezcla", "Share of voice A": "Proporción de la voz A",
    "{a}% A · {b}% B": "{a} % A · {b} % B", "Save blend": "Guardar mezcla",
    "e.g. Warm narrator blend": "p. ej. Mezcla de narrador cálido",
    "Pick two different voices.": "Elige dos voces distintas.", "Give the blend a name.": "Ponle un nombre a la mezcla.",
    "Loading voices…": "Cargando voces…", "Choose a voice…": "Elige una voz…",
    "Could not load voices: {m}": "No se pudieron cargar las voces: {m}",
    // Text to Speech
    "Turn text into speech with any voice. Spanish and English, even mixed.":
      "Convierte texto en voz con cualquier voz. Español e inglés, incluso mezclados.",
    "Text to speak": "Texto a convertir", "Type or paste the text you want to hear…": "Escribe o pega el texto que quieres oír…",
    "{n} / {max} characters": "{n} / {max} caracteres", "Ctrl+Enter to generate": "Ctrl+Enter para generar",
    "Generate": "Generar", "Generating…": "Generando…", "Voice": "Voz", "Search voices…": "Buscar voces…",
    "No voices match your search.": "Ninguna voz coincide con la búsqueda.", "Choose a voice.": "Elige una voz.",
    "Auto-detect (Spanish / English)": "Detección automática (español / inglés)",
    "Generating speech… (the first request loads the model and can take a minute)":
      "Generando voz… (la primera solicitud carga el modelo y puede tardar un minuto)",
    "Done · {s} s · saved to History": "Listo · {s} s · guardado en Historial",
    "Generation failed: {m}": "No se pudo generar: {m}",
    "Text tags": "Etiquetas de texto", "Pause 0.5 s": "Pausa 0,5 s", "Pause 1 s": "Pausa 1 s",
    "Insert a 0.5 second pause": "Insertar una pausa de 0,5 segundos", "Insert a 1 second pause": "Insertar una pausa de 1 segundo",
    "Slow": "Lento", "Fast": "Rápido", "Whisper": "Susurro", "Happy": "Alegre", "Sad": "Triste", "Excited": "Emocionado",
    "Normal": "Normal", "Speak slower from here": "Hablar más lento desde aquí", "Speak faster from here": "Hablar más rápido desde aquí",
    "Whisper from here": "Susurrar desde aquí", "Sound happy from here": "Sonar alegre desde aquí",
    "Sound sad from here": "Sonar triste desde aquí", "Sound excited from here": "Sonar emocionado desde aquí",
    "Back to the normal voice": "Volver a la voz normal",
    "No room for the tag: the text is at the {max} character limit.": "No cabe la etiqueta: el texto llegó al límite de {max} caracteres.",
    "Playback position": "Posición de reproducción", "Play": "Reproducir", "Pause": "Pausa",
    "Download": "Descargar", "OGG (WhatsApp voice note)": "OGG (nota de voz de WhatsApp)",
    "Subtitles": "Subtítulos", "Timed subtitles, one line per sentence": "Subtítulos con tiempos, una línea por frase",
    // voice changer
    "Speak or upload a recording. Hear the same words, timing and emotion in another voice.":
      "Habla o sube una grabación. Escucha las mismas palabras, el mismo ritmo y la misma emoción con otra voz.",
    "1 · Your speech": "1 · Tu voz", "2 · New voice": "2 · Nueva voz",
    "Drop a recording here": "Suelta aquí una grabación",
    "or click to browse · audio or video · 0.5 s to 5 min": "o haz clic para elegir · audio o vídeo · de 0,5 s a 5 min",
    "This is not an audio file: {name}": "Esto no es un archivo de audio: {name}",
    "Recording… speak naturally.": "Grabando… habla con naturalidad.", "Your recording": "Tu grabación",
    "Convert": "Convertir", "Converting…": "Convirtiendo…",
    "Converting… (the first time loads the model and can take a minute)":
      "Convirtiendo… (la primera vez carga el modelo y puede tardar un minuto)",
    "Conversion failed: {m}": "Error al convertir: {m}", "Language of the recording": "Idioma de la grabación",
    "Only use voices you own or have permission to use. The result is saved to History with subtitles.":
      "Usa solo voces propias o con permiso. El resultado se guarda en el Historial con subtítulos.",
    // dialogue
    "Write a conversation, one line per turn: “Name: text”. Each speaker gets a voice. You get one audio file.":
      "Escribe una conversación, una línea por turno: «Nombre: texto». Cada persona tiene una voz. Obtienes un solo archivo de audio.",
    "Script": "Guion", "Speakers": "Personajes", "Generate dialogue": "Generar diálogo",
    "Ann: Hi Ben! How was the trip?": "Ana: ¡Hola, Beto! ¿Qué tal el viaje?",
    "Ben: Long, but worth it. I saw the sea!": "Beto: Largo, pero valió la pena. ¡Vi el mar!",
    "Ann: [happy] Lucky you!": "Ana: [happy] ¡Qué suerte!",
    "Voice for {name}": "Voz para {name}", "Pause between turns": "Pausa entre turnos",
    "Write lines like “Ann: Hello.” Each new name gets its own voice.":
      "Escribe líneas como «Ana: Hola.». Cada nombre nuevo recibe su propia voz.",
    "Too many speakers ({n}, max {max})": "Demasiados personajes ({n}, máx. {max})",
    // batch
    "Turn a file into many clips at once. Download them all as one ZIP.":
      "Convierte un archivo en muchos clips a la vez. Descárgalos todos en un ZIP.",
    "Drop a .txt, .docx or .csv file here": "Suelta aquí un archivo .txt, .docx o .csv",
    "or click to browse · up to 100 clips": "o haz clic para buscar · hasta 100 clips",
    "TXT: one clip per line.": "TXT: un clip por línea.", "DOCX: one clip per paragraph.": "DOCX: un clip por párrafo.",
    "CSV: a header row with the column text, and optional voice, language, filename.":
      "CSV: una fila de encabezado con la columna text y, si quieres, voice, language, filename.",
    "Reading {name}…": "Leyendo {name}…", "{n} clips found in {name}": "{n} clips encontrados en {name}",
    "Cannot read this file: {m}": "No se puede leer este archivo: {m}", "Done · {s} s": "Listo · {s} s",
    "Generate {n} clips": "Generar {n} clips", "Stop": "Detener", "Download ZIP": "Descargar ZIP",
    "{done} / {n} clips": "{done} / {n} clips", "{n} failed": "{n} con error", "Stopped.": "Detenido.",
    "{ok} of {n} clips made · saved to History": "{ok} de {n} clips hechos · guardados en el Historial",
    "Not generated": "No generado", "Could not make the ZIP: {m}": "No se pudo crear el ZIP: {m}",
    "Used for clips that do not set their own.": "Se usa en los clips que no indican el suyo.",
    "Format": "Formato", "Every clip is also saved to History, with subtitles.":
      "Cada clip también se guarda en el Historial, con subtítulos.",
    "Speed": "Velocidad", "Stability": "Estabilidad", "Expressiveness": "Expresividad",
    "Slower": "Más lenta", "Faster": "Más rápida", "More variable": "Más variable", "More stable": "Más estable",
    "Calmer": "Más tranquila", "Livelier": "Más viva", "Reset settings": "Restablecer ajustes",
    "This voice's engine ({engine}) supports speed only.": "El motor de esta voz ({engine}) solo admite la velocidad.",
    // Voice Library
    "Free voices with open licenses. Listen to a preview, then add the ones you like to My Voices.":
      "Voces gratuitas con licencias abiertas. Escucha una muestra y añade las que te gusten a Mis voces.",
    "Search by name, accent or style…": "Buscar por nombre, acento o estilo…",
    "Accent": "Acento", "Gender": "Género", "Age": "Edad", "Style": "Estilo", "License": "Licencia",
    "Any language": "Cualquier idioma", "Any accent": "Cualquier acento", "Any gender": "Cualquier género",
    "Any age": "Cualquier edad", "Any style": "Cualquier estilo", "Any engine": "Cualquier motor", "Any license": "Cualquier licencia",
    "Commercial use only": "Solo uso comercial", "Clear filters": "Quitar filtros",
    "{n} of {total} voices": "{n} de {total} voces", "No voices match these filters.": "Ninguna voz coincide con estos filtros.",
    "Commercial use OK": "Uso comercial permitido", "Non-commercial": "No comercial",
    "Preview {name}": "Escuchar {name}", "Could not play the preview: {m}": "No se pudo reproducir la muestra: {m}",
    "Add to My Voices": "Añadir a Mis voces", "Adding…": "Añadiendo…", "✓ In My Voices": "✓ En Mis voces",
    "Added “{name}” to My Voices.": "“{name}” añadida a Mis voces.", "Could not add the voice: {m}": "No se pudo añadir la voz: {m}",
    "Estimated from the audio: {list}": "Estimado a partir del audio: {list}", "age": "edad", "tags": "estilo", "gender": "género",
    "Female": "Femenina", "Male": "Masculina", "Neutral (gender)": "Neutra",
    "Young adult": "Adulto joven", "Adult": "Adulta", "Middle-aged": "Mediana edad", "Senior": "Mayor",
    "warm": "cálida", "narrator": "narrador", "news": "noticias", "conversational": "conversacional", "energetic": "enérgica",
    "calm": "tranquila", "multilingual": "multilingüe",
    "American": "Estadounidense", "British": "Británico", "Spain": "España", "Mexican": "Mexicano", "Argentine": "Argentino",
    "Neutral": "Neutro", "Scottish": "Escocés", "Northern English": "Inglés del norte", "Southern English": "Inglés del sur",
    "Neutral (multilingual)": "Neutro (multilingüe)", "Public domain": "Dominio público", "Public domain (LibriVox)": "Dominio público (LibriVox)",
    "Your saved voices: cloned, blended and copied from the library. ": "Tus voces guardadas: clonadas, mezcladas y copiadas de la biblioteca. ",
    "Clone a voice": "Clonar una voz", "Browse the Voice Library": "Ver la biblioteca de voces", "No voices yet.": "Aún no hay voces.",
    "Cloned": "Clonada", "Blend": "Mezcla", "Preset": "Predefinida", "★ Default": "★ Predeterminada", "Not set": "Sin indicar",
    "Copy": "Copiar", "Copy voice ID": "Copiar el ID de la voz", "Copied {id}": "Copiado {id}",
    "Copy is blocked in this browser. The ID is: {id}": "Este navegador bloquea la copia. El ID es: {id}",
    "The first preview is made now and can take a moment.": "La primera muestra se crea ahora y puede tardar un poco.",
    "Rename": "Renombrar", "Edit": "Editar", "Duplicate": "Duplicar", "Set as default": "Usar como predeterminada",
    "Delete": "Eliminar", "Save": "Guardar", "Cancel": "Cancelar", "Saved “{name}”.": "Guardada “{name}”.",
    "Made a copy of “{name}”.": "Se creó una copia de “{name}”.",
    "“{name}” is now the default voice.": "“{name}” es ahora la voz predeterminada.",
    "Delete “{name}”? Its samples and settings are removed. This cannot be undone.": "¿Eliminar “{name}”? Se borran sus muestras y ajustes. No se puede deshacer.",
    "Deleted “{name}”.": "Se eliminó “{name}”.",
    "Every clip you generate is kept here, newest first.": "Aquí se guarda cada clip que generas, del más reciente al más antiguo.",
    "Search text or voice…": "Buscar texto o voz…", "Loading…": "Cargando…", "1 clip": "1 clip", "{n} clips": "{n} clips",
    "No clips yet.": "Aún no hay clips.", "No clips match your search.": "Ningún clip coincide con tu búsqueda.",
    "Go to Text to Speech": "Ir a Texto a voz", "▶ Play": "▶ Reproducir", "Show more": "Ver más", "Show less": "Ver menos",
    "Use in Text to Speech": "Usar en Texto a voz", "Load more ({n} left)": "Cargar más (quedan {n})",
    "Delete this clip? Its audio and subtitles are removed. This cannot be undone.": "¿Eliminar este clip? Se borran su audio y sus subtítulos. No se puede deshacer.",
    "Clip deleted.": "Clip eliminado.", "Could not delete the clip: {m}": "No se pudo eliminar el clip: {m}",
    "Could not load the history: {m}": "No se pudo cargar el historial: {m}",
    "Use Voice Studio from scripts and AI agents.": "Usa Voice Studio desde scripts y agentes de IA.",
    "Server address": "Dirección del servidor", "API key": "Clave de API", "Examples": "Ejemplos", "Endpoints": "Endpoints",
    "Copy code": "Copiar el código", "Copied.": "Copiado.", "On": "Activada", "Off": "Desactivada",
    "List voices": "Listar voces", "Speak and save an MP3": "Hablar y guardar un MP3",
    "WhatsApp voice note (OGG/Opus)": "Nota de voz de WhatsApp (OGG/Opus)", "Subtitles (SRT)": "Subtítulos (SRT)",
    "OpenAI SDK (Python)": "SDK de OpenAI (Python)", "OpenAI-compatible (curl)": "Compatible con OpenAI (curl)",
    "Replace the API key? Agents that use the old key stop working.": "¿Reemplazar la clave de API? Los agentes que usan la clave antigua dejan de funcionar.",
    "New API key made. Copy it now.": "Clave de API nueva creada. Cópiala ahora.",
    "Turn off the API key? Then any device that can reach this server can use it.": "¿Desactivar la clave de API? Entonces cualquier dispositivo que llegue a este servidor puede usarlo.",
    "API key turned off.": "Clave de API desactivada.", "Key {hint}, made {date}.": "Clave {hint}, creada el {date}.",
    "Any device on your network can use the API. Remote access (Tailscale) stays closed until you make a key.": "Cualquier dispositivo de tu red puede usar la API. El acceso remoto (Tailscale) sigue cerrado hasta que crees una clave.",
    "This PC never needs the key. Other devices (phone, VPS, Tailscale) must send it as “Authorization: Bearer <key>”.": "Este PC nunca necesita la clave. Otros dispositivos (teléfono, VPS, Tailscale) deben enviarla como “Authorization: Bearer <key>”.",
    "Copy the key now. It is shown only once. Keep it secret.": "Copia la clave ahora. Solo se muestra una vez. Mantenla en secreto.",
    "Replace key": "Reemplazar la clave", "Create API key": "Crear clave de API", "Turn off": "Desactivar",
    "{n} endpoints. ": "{n} endpoints. ", "Try them in the interactive docs": "Pruébalos en la documentación interactiva",
    "Could not load the endpoint list: {m}": "No se pudo cargar la lista de endpoints: {m}",
    "Examples use the voice “{name}” (ID {id}). Any voice ID from /api/voices works.": "Los ejemplos usan la voz “{name}” (ID {id}). Sirve cualquier ID de voz de /api/voices.",
    "MCP for AI agents": "MCP para agentes de IA",
    "Tools: {tools}. “speak” returns a link to the audio (and the file path on this PC). Use format “ogg_opus” for WhatsApp voice notes.":
      "Herramientas: {tools}. “speak” devuelve un enlace al audio (y la ruta del archivo en este PC). Usa el formato “ogg_opus” para notas de voz de WhatsApp.",
    "Config file (Claude Code, Cursor, VS Code…)": "Archivo de configuración (Claude Code, Cursor, VS Code…)",
    "Claude Code command": "Comando de Claude Code",
    "Config file (agents on this PC or in WSL)": "Archivo de configuración (agentes en este PC o en WSL)",
    "Config file (Claude Desktop and other Windows apps)": "Archivo de configuración (Claude Desktop y otras apps de Windows)",
    "stdio and Windows app configs are shown only on the PC that runs Voice Studio.": "Las configuraciones stdio y de apps de Windows solo se muestran en el PC donde corre Voice Studio.",
    "The API key is on: agents on other devices must send it. Replace YOUR_API_KEY with your key.": "La clave de API está activada: los agentes en otros dispositivos deben enviarla. Cambia YOUR_API_KEY por tu clave.",
    // remote access
    "Remote access (Tailscale)": "Acceso remoto (Tailscale)",
    "Remote access settings are shown only on the PC that runs Voice Studio.": "Los ajustes de acceso remoto solo se muestran en el PC donde corre Voice Studio.",
    "Tailscale is not installed.": "Tailscale no está instalado.",
    "Tailscale is installed but not signed in.": "Tailscale está instalado, pero no has iniciado sesión.",
    "Tailscale is on ({name}). Voice Studio is not shared yet.": "Tailscale está activo ({name}). Voice Studio aún no se comparte.",
    "Shared on your tailnet: {url}": "Compartido en tu tailnet: {url}",
    "Tailscale Funnel is on: the server is open to the whole internet, not just your tailnet. Turn it off with: tailscale funnel reset":
      "Tailscale Funnel está activo: el servidor está abierto a todo internet, no solo a tu tailnet. Desactívalo con: tailscale funnel reset",
    "The API key is off, so remote requests are refused. Make a key on this page.": "La clave de API está desactivada, así que se rechazan las solicitudes remotas. Crea una clave en esta página.",
    "Agents on a VPS reach this PC through Tailscale. Only devices in your tailnet can connect, the link is encrypted, and every request must send the API key.":
      "Los agentes en un VPS llegan a este PC por Tailscale. Solo los dispositivos de tu tailnet pueden conectarse, la conexión va cifrada y cada solicitud debe enviar la clave de API.",
    "Tailscale runs in this WSL/Linux. Sign in:": "Tailscale corre en este WSL/Linux. Inicia sesión:",
    "Install Tailscale on this Windows PC and sign in:": "Instala Tailscale en este PC con Windows e inicia sesión:",
    "Make an API key (card above). Remote requests without it are refused.": "Crea una clave de API (tarjeta de arriba). Sin ella se rechazan las solicitudes remotas.",
    "Share Voice Studio on your tailnet only (in this WSL terminal):": "Comparte Voice Studio solo en tu tailnet (en esta terminal de WSL):",
    "Share Voice Studio on your tailnet only (in Windows PowerShell):": "Comparte Voice Studio solo en tu tailnet (en PowerShell de Windows):",
    "On the VPS, install Tailscale and sign in to the same tailnet:": "En el VPS, instala Tailscale e inicia sesión en la misma tailnet:",
    "Test from the VPS. Use the same address for the REST API, the OpenAI API ({v1}) and MCP ({mcp}):":
      "Prueba desde el VPS. Usa la misma dirección para la API REST, la API de OpenAI ({v1}) y MCP ({mcp}):",
    "Do not use “tailscale funnel”: it opens the server to the whole internet. To stop sharing: {cmd}":
      "No uses “tailscale funnel”: abre el servidor a todo internet. Para dejar de compartir: {cmd}",
    // backup
    "Export": "Exportar", "Export all voices": "Exportar todas las voces",
    "Download this voice (samples, settings, dictionary) as a zip, to use on another PC or VPS.":
      "Descarga esta voz (muestras, ajustes, diccionario) en un zip, para usarla en otro PC o VPS.",
    "Download all your voices and the pronunciation dictionary as one zip.": "Descarga todas tus voces y el diccionario de pronunciación en un zip.",
    "Import backup": "Importar copia", "Importing…": "Importando…",
    "Add the voices and dictionary words from a backup zip. Nothing you have is overwritten.":
      "Añade las voces y las palabras del diccionario de un zip de copia. No se sobrescribe nada de lo que tienes.",
    "Imported {n} voices and {w} dictionary words.": "Importadas {n} voces y {w} palabras del diccionario.",
    "{n} voices were already here, so they were added as copies.": "{n} voces ya estaban aquí, así que se añadieron como copias.",
    "Could not import the backup: {m}": "No se pudo importar la copia: {m}",
    // auto-backup (Settings)
    "Daily backup": "Copia diaria", "Folder": "Carpeta",
    "Backup settings are shown only on the PC that runs Voice Studio.": "Los ajustes de copia solo se muestran en el PC donde corre Voice Studio.",
    "Last backup failed: {m}": "La última copia falló: {m}",
    "Last backup: {when} ({file}). {n} kept in the folder.": "Última copia: {when} ({file}). {n} guardadas en la carpeta.",
    "No automatic backup yet.": "Aún no hay copias automáticas.",
    "Once a day, all your voices and the pronunciation dictionary are saved as one zip in a folder. Import the zip on My Voices to restore them.":
      "Una vez al día, todas tus voces y el diccionario de pronunciación se guardan en un zip en una carpeta. Importa el zip en Mis voces para recuperarlas.",
    "Make a backup every day": "Hacer una copia cada día",
    "Empty = {path}. A Windows folder such as {example} also works.": "Vacío = {path}. También sirve una carpeta de Windows como {example}.",
    "Keep the newest": "Guardar las más recientes",
    "Backing up…": "Haciendo copia…", "Back up now": "Hacer copia ahora",
    "Next backup: {when}": "Próxima copia: {when}",
    "Backup settings saved.": "Ajustes de copia guardados.", "Backup made.": "Copia hecha.",
    // usage
    "Last 24 hours": "Últimas 24 horas", "Last 7 days": "Últimos 7 días", "Last 30 days": "Últimos 30 días", "All time": "Todo",
    "Requests": "Solicitudes", "Characters": "Caracteres", "Minutes": "Minutos", "Audio minutes": "Minutos de audio",
    "Nothing in this period.": "Nada en este periodo.", "Period": "Periodo",
    "By voice": "Por voz", "By app or agent": "Por app o agente", "App or agent": "App o agente",
    "By API key or device": "Por clave de API o dispositivo", "API key or device": "Clave de API o dispositivo",
    "By connection": "Por conexión", "Connection": "Conexión",
    "REST API": "API REST", "OpenAI API": "API de OpenAI", "MCP (HTTP)": "MCP (HTTP)", "MCP (local app)": "MCP (app local)",
    "Other": "Otro", "This PC": "Este PC", "No key (key off)": "Sin clave (clave desactivada)", "Web browser": "Navegador web",
    "Unknown": "Desconocido", "Dialogue (several voices)": "Diálogo (varias voces)",
    "Clips made, characters read and audio minutes, per voice and per app or API key. One request = one clip saved to History.":
      "Clips creados, caracteres leídos y minutos de audio, por voz y por app o clave de API. Una solicitud = un clip guardado en el Historial.",
    "Name your app: send the header X-Voicer-Agent: <name> with each request. MCP apps are named automatically.":
      "Pon nombre a tu app: envía el encabezado X-Voicer-Agent: <nombre> con cada solicitud. Las apps MCP se nombran solas.",
    // dictionary
    "Tell the voices how to say a word: names, brands, abbreviations. Used before every generation, in the app and the API.":
      "Indica a las voces cómo decir una palabra: nombres, marcas, siglas. Se usa antes de cada generación, en la app y en la API.",
    "Word": "Palabra", "Say it as": "Decir como", "Add word": "Añadir palabra", "Save change": "Guardar cambio",
    "▶ Listen": "▶ Escuchar", "Listen to {word}": "Escuchar {word}", "Search words…": "Buscar palabras…",
    "1 word": "1 palabra", "{n} words": "{n} palabras", "{n} of {total} words": "{n} de {total} palabras", "No words match.": "Ninguna palabra coincide.",
    "No words yet. Add the first one above.": "Aún no hay palabras. Añade la primera arriba.",
    "Type the word and how to say it.": "Escribe la palabra y cómo decirla.",
    "Added “{word}”.": "Añadida “{word}”.", "Saved “{word}”.": "Guardada “{word}”.", "Deleted “{word}”.": "Eliminada “{word}”.",
    "Delete “{word}” from the dictionary?": "¿Eliminar “{word}” del diccionario?",
    "Imported {n} words.": "{n} palabras importadas.", "Export CSV": "Exportar CSV", "Import CSV": "Importar CSV",
    "Download all words as a CSV file (language, word, spoken form).":
      "Descarga todas las palabras como archivo CSV (idioma, palabra, forma hablada).",
    "Add words from a CSV file: language, word, spoken form. Words you have are changed, none are removed.":
      "Añade palabras desde un archivo CSV: idioma, palabra, forma hablada. Las que ya tienes se cambian, ninguna se elimina.",
    // voice changer: subtitles only
    "Subtitles only (SRT)": "Solo subtítulos (SRT)", "Making subtitles…": "Creando subtítulos…",
    "Subtitles downloaded: {name} · {n} lines": "Subtítulos descargados: {name} · {n} líneas",
    "Subtitles failed: {m}": "No se pudieron crear los subtítulos: {m}",
    "Make timed subtitles of the recording as it is, without changing the voice (up to 10 min).":
      "Crea subtítulos con tiempos de la grabación tal cual, sin cambiar la voz (hasta 10 min).",
  },
};
const UI_LANGS = [["en", "English"], ["es", "Español"]];
let uiLang = (() => {
  let v = null;
  try { v = localStorage.getItem("ui-lang"); } catch { /* storage blocked */ }
  if (UI_LANGS.some(([c]) => c === v)) return v;
  return (navigator.language || "en").toLowerCase().startsWith("es") ? "es" : "en";
})();
function t(key, vars = {}) {
  const s = (uiLang !== "en" && I18N[uiLang]?.[key]) || key;
  return s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));
}
