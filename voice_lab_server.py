#!/usr/bin/env python3
"""
Voice Lab — a tiny web page to audition every Chatterbox voice at once.

Type a line of text, hit Run, and it generates a sample for every voice the
Chatterbox API currently knows about. Each voice can be renamed on disk so you
can tidy up the mixed bag of sample files. Voice list refreshes on every load.

No third-party deps — pure stdlib. Chatterbox restart is handled by you; after
renaming files, restart Chatterbox so it re-discovers the new names, then reload.

Run:  python voice_lab_server.py        (serves on http://0.0.0.0:7070)
"""
import json
import re
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# ---------------------------------------------------------------------------
CHATTERBOX = "http://127.0.0.1:5005"        # OpenAI-compatible Chatterbox API
VOICES_DIR = Path(__file__).parent           # where the sample files live
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 7070
AUDIO_EXTS = (".mp3", ".wav", ".flac")
# ---------------------------------------------------------------------------


def slugify(stem: str) -> str:
    """Match Chatterbox's own voice-id derivation (lowercase, hyphenated)."""
    slug = stem.strip().lower()
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def fetch_voices():
    """Ask Chatterbox for its live voice list and recover each source file."""
    with urllib.request.urlopen(f"{CHATTERBOX}/v1/audio/voices", timeout=15) as r:
        data = json.load(r)
    voices = []
    for v in data.get("data", []):
        desc = v.get("description") or ""
        m = re.search(r"based on (.+)$", desc)
        fname = m.group(1).strip() if m else None
        # Only treat it as renameable if the file actually exists on disk.
        if fname and not (VOICES_DIR / fname).is_file():
            fname = None
        voices.append({
            "id": v.get("id"),
            "name": v.get("name") or v.get("id"),
            "file": fname,
            "available": v.get("available", True),
        })
    return voices


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quieter logs
        pass

    def _send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith("/api/voices"):
            try:
                self._send_json({"voices": fetch_voices()})
            except Exception as e:
                self._send_json({"error": str(e)}, 502)
        else:
            self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._send_json({"error": "bad json"}, 400)
            return

        if self.path.startswith("/api/speech"):
            self._proxy_speech(payload)
        elif self.path.startswith("/api/rename"):
            self._rename(payload)
        else:
            self.send_error(404)

    def _proxy_speech(self, payload):
        voice = (payload.get("voice") or "her").strip()
        text = (payload.get("input") or "").strip()
        if not text:
            self._send_json({"error": "empty text"}, 400)
            return
        req_body = json.dumps({
            "input": text,
            "voice": voice,
            "response_format": "mp3",
        }).encode()
        req = urllib.request.Request(
            f"{CHATTERBOX}/v1/audio/speech",
            data=req_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                audio = r.read()
        except urllib.error.HTTPError as e:
            self._send_json({"error": f"chatterbox {e.code}: {e.read()[:200]!r}"}, 502)
            return
        except Exception as e:
            self._send_json({"error": str(e)}, 502)
            return
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", str(len(audio)))
        self.end_headers()
        self.wfile.write(audio)

    def _rename(self, payload):
        old = (payload.get("file") or "").strip()
        newname = (payload.get("newname") or "").strip()
        if not old or not newname:
            self._send_json({"error": "file and newname required"}, 400)
            return
        # Guard against path traversal — must be a plain filename in VOICES_DIR.
        if "/" in old or "\\" in old:
            self._send_json({"error": "bad file"}, 400)
            return
        src = VOICES_DIR / old
        if not src.is_file() or src.suffix.lower() not in AUDIO_EXTS:
            self._send_json({"error": "source not found"}, 404)
            return
        slug = slugify(Path(newname).stem)
        if not slug:
            self._send_json({"error": "invalid name"}, 400)
            return
        dst = VOICES_DIR / f"{slug}{src.suffix.lower()}"
        if dst.exists() and dst != src:
            self._send_json({"error": f"{dst.name} already exists"}, 409)
            return
        try:
            src.rename(dst)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)
            return
        self._send_json({"ok": True, "file": dst.name, "id": slug})


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Voice Lab</title>
<style>
  :root {
    --bg:#0e1116; --panel:#171b22; --panel2:#1e242e; --line:#2a3240;
    --text:#e7ecf3; --muted:#8b97a8; --accent:#5b9dff; --accent2:#3a7bd5;
    --ok:#39d98a; --warn:#f0a020; --err:#ff6b6b;
  }
  * { box-sizing:border-box; }
  body {
    margin:0; background:var(--bg); color:var(--text);
    font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  }
  header {
    padding:20px 24px; border-bottom:1px solid var(--line);
    display:flex; align-items:baseline; gap:12px; position:sticky; top:0;
    background:var(--bg); z-index:5;
  }
  header h1 { margin:0; font-size:20px; letter-spacing:.2px; }
  header .sub { color:var(--muted); font-size:13px; }
  main { max-width:1100px; margin:0 auto; padding:24px; }
  .controls {
    display:flex; gap:10px; margin-bottom:6px; flex-wrap:wrap;
  }
  textarea {
    flex:1 1 420px; min-height:52px; resize:vertical; padding:12px 14px;
    background:var(--panel); border:1px solid var(--line); color:var(--text);
    border-radius:10px; font:inherit;
  }
  textarea:focus, input:focus { outline:none; border-color:var(--accent); }
  button {
    border:0; border-radius:10px; padding:0 20px; font:inherit; font-weight:600;
    cursor:pointer; color:#fff; background:var(--accent2); height:52px;
  }
  button:hover { background:var(--accent); }
  button.ghost {
    background:transparent; border:1px solid var(--line); color:var(--muted);
    height:auto; padding:6px 12px; font-weight:500; font-size:13px;
  }
  button.ghost:hover { border-color:var(--accent); color:var(--text); background:transparent; }
  button:disabled { opacity:.5; cursor:default; }
  .bar { display:flex; align-items:center; justify-content:space-between; margin:18px 2px 12px; }
  .bar .count { color:var(--muted); font-size:13px; }
  .grid {
    display:grid; grid-template-columns:repeat(auto-fill,minmax(320px,1fr)); gap:14px;
  }
  .card {
    background:var(--panel); border:1px solid var(--line); border-radius:12px;
    padding:14px 16px; display:flex; flex-direction:column; gap:10px;
  }
  .card.gen { border-color:var(--accent2); }
  .card h3 { margin:0; font-size:15px; display:flex; align-items:center; gap:8px; }
  .card .fname { color:var(--muted); font-size:12px; font-family:ui-monospace,Menlo,monospace; word-break:break-all; }
  .status { font-size:12px; color:var(--muted); }
  .status.err { color:var(--err); }
  audio { width:100%; height:36px; }
  .renamer { display:flex; gap:6px; }
  .renamer input {
    flex:1; padding:7px 10px; background:var(--panel2); border:1px solid var(--line);
    color:var(--text); border-radius:8px; font:inherit; font-size:13px;
  }
  .dot { width:8px; height:8px; border-radius:50%; background:var(--muted); flex:none; }
  .dot.busy { background:var(--warn); animation:pulse 1s infinite; }
  .dot.done { background:var(--ok); }
  .dot.err { background:var(--err); }
  @keyframes pulse { 50% { opacity:.35; } }
  .toast {
    position:fixed; bottom:20px; left:50%; transform:translateX(-50%);
    background:var(--panel2); border:1px solid var(--line); padding:10px 16px;
    border-radius:10px; font-size:13px; opacity:0; transition:opacity .2s; pointer-events:none;
  }
  .toast.show { opacity:1; }
</style>
</head>
<body>
<header>
  <h1>🎙️ Voice Lab</h1>
  <span class="sub">audition every Chatterbox voice · rename the messy ones</span>
</header>
<main>
  <div class="controls">
    <textarea id="text" placeholder="Type the line you want every voice to say…">The quick brown fox jumps over the lazy dog.</textarea>
    <button id="run">Run ▸</button>
  </div>
  <div class="bar">
    <div class="count" id="count">Loading voices…</div>
    <button class="ghost" id="reload">↻ Refresh voices</button>
  </div>
  <div class="grid" id="grid"></div>
</main>
<div class="toast" id="toast"></div>
<script>
const grid = document.getElementById('grid');
const countEl = document.getElementById('count');
let voices = [];

function toast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  clearTimeout(t._t); t._t = setTimeout(() => t.classList.remove('show'), 2200);
}

async function loadVoices() {
  countEl.textContent = 'Loading voices…';
  grid.innerHTML = '';
  try {
    const r = await fetch('/api/voices');
    const j = await r.json();
    if (j.error) throw new Error(j.error);
    voices = j.voices;
    countEl.textContent = voices.length + ' voices';
    grid.innerHTML = '';
    voices.forEach(renderCard);
  } catch (e) {
    countEl.textContent = 'Error: ' + e.message + ' (is Chatterbox up on :5005?)';
  }
}

function renderCard(v) {
  const card = document.createElement('div');
  card.className = 'card';
  card.dataset.id = v.id;
  card.innerHTML = `
    <h3><span class="dot"></span>${v.name}</h3>
    <div class="fname">${v.file || '(built-in, no file)'}</div>
    <div class="status">idle</div>
    <audio controls preload="none" style="display:none"></audio>
    ${v.file ? `<div class="renamer">
      <input type="text" placeholder="new name…" value="${v.file.replace(/\.[^.]+$/,'')}">
      <button class="ghost rename">Rename</button>
    </div>` : ''}
  `;
  const renameBtn = card.querySelector('.rename');
  if (renameBtn) {
    renameBtn.onclick = () => doRename(v, card);
    card.querySelector('.renamer input').addEventListener('keydown', e => {
      if (e.key === 'Enter') doRename(v, card);
    });
  }
  grid.appendChild(card);
}

async function generateOne(v, card) {
  const dot = card.querySelector('.dot');
  const status = card.querySelector('.status');
  const audio = card.querySelector('audio');
  const text = document.getElementById('text').value.trim();
  if (!text) return;
  dot.className = 'dot busy'; status.className = 'status'; status.textContent = 'generating…';
  card.classList.add('gen');
  const t0 = performance.now();
  try {
    const r = await fetch('/api/speech', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ voice: v.id, input: text })
    });
    if (!r.ok) { const j = await r.json().catch(()=>({error:r.statusText})); throw new Error(j.error||r.statusText); }
    const blob = await r.blob();
    if (audio.src) URL.revokeObjectURL(audio.src);
    audio.src = URL.createObjectURL(blob);
    audio.style.display = 'block';
    dot.className = 'dot done';
    status.textContent = ((performance.now()-t0)/1000).toFixed(1) + 's · ' + Math.round(blob.size/1024) + ' KB';
  } catch (e) {
    dot.className = 'dot err'; status.className = 'status err'; status.textContent = e.message;
  } finally {
    card.classList.remove('gen');
  }
}

async function runAll() {
  const text = document.getElementById('text').value.trim();
  if (!text) { toast('Enter some text first'); return; }
  const btn = document.getElementById('run');
  btn.disabled = true; btn.textContent = 'Running…';
  const cards = [...grid.children];
  // Sequential — Chatterbox is one GPU model; each card fills as it finishes.
  for (const card of cards) {
    const v = voices.find(x => x.id === card.dataset.id);
    if (v) await generateOne(v, card);
  }
  btn.disabled = false; btn.textContent = 'Run ▸';
}

async function doRename(v, card) {
  const input = card.querySelector('.renamer input');
  const newname = input.value.trim();
  if (!newname) return;
  try {
    const r = await fetch('/api/rename', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ file: v.file, newname })
    });
    const j = await r.json();
    if (j.error) throw new Error(j.error);
    v.file = j.file; v.id = j.id;
    card.dataset.id = j.id;
    card.querySelector('.fname').textContent = j.file + '  (restart Chatterbox to apply)';
    toast('Renamed → ' + j.file);
  } catch (e) {
    toast('Rename failed: ' + e.message);
  }
}

document.getElementById('run').onclick = runAll;
document.getElementById('reload').onclick = loadVoices;
loadVoices();
</script>
</body>
</html>"""


def main():
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    print(f"Voice Lab on http://{LISTEN_HOST}:{LISTEN_PORT}  (proxying Chatterbox at {CHATTERBOX})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
