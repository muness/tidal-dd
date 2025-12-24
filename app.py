"""Tidal Daily Discovery Sync - Railway/Render version"""

import os
import json
import tidalapi
from tidalapi.session import LinkLogin
from datetime import date, timedelta
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

app = FastAPI()

# Persistent storage (Railway/Render volume)
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
TOKENS_FILE = DATA_DIR / "tokens.json"
PENDING_FILE = DATA_DIR / "pending.json"
CONFIG_FILE = DATA_DIR / "config.json"

DEFAULT_CONFIG = {
    "selected_mixes": [],
    "retention_days": 7,
}


def load_json(path):
    return json.loads(path.read_text()) if path.exists() else None

def save_json(path, data):
    path.write_text(json.dumps(data, indent=2))

def get_config():
    return load_json(CONFIG_FILE) or DEFAULT_CONFIG.copy()

def get_session():
    tokens = load_json(TOKENS_FILE)
    if not tokens:
        return None
    session = tidalapi.Session()
    if session.load_oauth_session(tokens["token_type"], tokens["access_token"], tokens.get("refresh_token")):
        if session.access_token != tokens["access_token"]:
            save_json(TOKENS_FILE, {
                "token_type": session.token_type,
                "access_token": session.access_token,
                "refresh_token": session.refresh_token
            })
        return session
    return None


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/check_auth")
async def check_auth():
    pending = load_json(PENDING_FILE)
    if not pending:
        return {"error": True, "message": "No pending authorization"}

    session = tidalapi.Session()
    link_login = LinkLogin({
        "deviceCode": pending["device_code"],
        "userCode": pending["user_code"],
        "verificationUri": pending["verification_uri"],
        "verificationUriComplete": pending["verification_uri_complete"],
        "expiresIn": 300,
        "interval": 2
    })

    try:
        result = session._check_link_login(link_login, until_expiry=False)
        session.process_auth_token(result)
        if session.check_login():
            save_json(TOKENS_FILE, {
                "token_type": session.token_type,
                "access_token": session.access_token,
                "refresh_token": session.refresh_token
            })
            PENDING_FILE.unlink(missing_ok=True)
            return {"success": True, "message": "Authorization complete!"}
    except Exception as e:
        if "expired" in str(e).lower():
            PENDING_FILE.unlink(missing_ok=True)
            return {"expired": True, "message": "Authorization expired, refresh to try again"}
        return {"pending": True, "message": "Waiting for authorization..."}
    return {"pending": True, "message": "Waiting for authorization..."}


@app.get("/", response_class=HTMLResponse)
async def home():
    session = get_session()
    if session:
        config = get_config()
        mix_count = len(config.get("selected_mixes", []))
        retention = config.get("retention_days", 7)
        return f"""<h1>Tidal Mix Sync</h1>
<p style="color: green;">Connected to Tidal</p>
<p>Syncing {mix_count} mix(es), keeping {retention} days</p>
<ul>
<li><a href="/config">Configure mixes &amp; retention</a></li>
<li><a href="/sync">Run sync now</a></li>
<li><a href="/logout">Disconnect Tidal</a></li>
</ul>"""

    pending = load_json(PENDING_FILE)
    if pending:
        return f"""<h1>Waiting for Tidal Authorization</h1>
<p id="status">Checking...</p>
<p><a href='https://{pending['verification_uri_complete']}' target='_blank'>Click here if you haven't authorized yet</a></p>
<script>
async function check() {{
    const r = await fetch('/check_auth');
    const d = await r.json();
    document.getElementById('status').innerText = d.message;
    if (d.success) location.href = '/';
    else if (d.expired) location.href = '/';
}}
check(); setInterval(check, 3000);
</script>"""

    session = tidalapi.Session()
    login_info, future = session.login_oauth()
    future.cancel()

    save_json(PENDING_FILE, {
        "device_code": login_info.device_code,
        "user_code": login_info.user_code,
        "verification_uri": login_info.verification_uri,
        "verification_uri_complete": login_info.verification_uri_complete
    })

    link = login_info.verification_uri_complete
    return f"""<h1>Connect Tidal</h1>
<p><strong><a href='https://{link}' target='_blank'>1. Click here to authorize with Tidal</a></strong></p>
<p>2. This page will detect when you're done</p>
<p id="status" style="color: #666;">Waiting...</p>
<script>
async function check() {{
    const r = await fetch('/check_auth');
    const d = await r.json();
    if (d.success) location.href = '/';
    else if (d.pending) document.getElementById('status').innerText = d.message;
}}
setTimeout(() => {{ check(); setInterval(check, 3000); }}, 5000);
</script>"""


@app.get("/logout")
async def logout():
    TOKENS_FILE.unlink(missing_ok=True)
    PENDING_FILE.unlink(missing_ok=True)
    return HTMLResponse("<h1>Disconnected</h1><p><a href='/'>Connect again</a></p>")


@app.get("/api/mixes")
async def get_mixes():
    session = get_session()
    if not session:
        return {"error": "Not authenticated"}

    mixes = []
    for category in session.mixes().categories:
        if hasattr(category, "items"):
            for item in category.items:
                if hasattr(item, "id"):
                    mixes.append({
                        "id": item.id,
                        "title": getattr(item, "title", "Unknown"),
                        "sub_title": getattr(item, "sub_title", ""),
                    })
    return {"mixes": mixes}


@app.get("/api/config")
async def get_config_api():
    return get_config()


@app.post("/api/config")
async def save_config_api(request: Request):
    data = await request.json()
    config = get_config()
    if "selected_mixes" in data:
        config["selected_mixes"] = data["selected_mixes"]
    if "retention_days" in data:
        config["retention_days"] = max(1, min(365, int(data["retention_days"])))
    save_json(CONFIG_FILE, config)
    return {"success": True, "config": config}


@app.get("/config", response_class=HTMLResponse)
async def config_page():
    if not get_session():
        return HTMLResponse("<h1>Not connected</h1><p><a href='/'>Connect first</a></p>")

    return """<h1>Configure Sync</h1>
<div id="loading">Loading mixes...</div>
<div id="config" style="display:none;">
<h2>Select Mixes to Sync</h2>
<div id="mixes"></div>
<h2>Retention</h2>
<p><label>Keep playlists for <input type="number" id="retention" min="1" max="365" value="7" style="width:60px"> days</label></p>
<p><button onclick="saveConfig()">Save</button></p>
<p id="status"></p>
<p><a href="/">Back</a></p>
</div>
<script>
let mixes=[], config={};
async function load() {
    const [m,c] = await Promise.all([fetch('/api/mixes').then(r=>r.json()), fetch('/api/config').then(r=>r.json())]);
    mixes = m.mixes || []; config = c;
    document.getElementById('mixes').innerHTML = mixes.map(m =>
        '<label style="display:block;margin:8px 0"><input type="checkbox" value="'+m.id+'" '+(config.selected_mixes?.includes(m.id)?'checked':'')+'> <strong>'+m.title+'</strong> '+(m.sub_title||'')+'</label>'
    ).join('');
    document.getElementById('retention').value = config.retention_days || 7;
    document.getElementById('loading').style.display = 'none';
    document.getElementById('config').style.display = 'block';
}
async function saveConfig() {
    const selected = [...document.querySelectorAll('#mixes input:checked')].map(c=>c.value);
    const retention = parseInt(document.getElementById('retention').value) || 7;
    const res = await fetch('/api/config', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({selected_mixes:selected, retention_days:retention})});
    const d = await res.json();
    document.getElementById('status').innerText = d.success ? 'Saved!' : 'Error';
    document.getElementById('status').style.color = d.success ? 'green' : 'red';
}
load();
</script>"""


@app.get("/sync")
async def sync():
    session = get_session()
    if not session:
        return {"error": "Not authenticated", "setup": "/"}

    config = get_config()
    selected = config.get("selected_mixes", [])
    retention = config.get("retention_days", 7)

    if not selected:
        return {"error": "No mixes selected", "config": "/config"}

    # Get mixes
    all_mixes = {}
    for cat in session.mixes().categories:
        if hasattr(cat, "items"):
            for item in cat.items:
                if hasattr(item, "id"):
                    all_mixes[item.id] = item

    results = []
    today = date.today().isoformat()

    for mix_id in selected:
        mix = all_mixes.get(mix_id)
        if not mix:
            results.append({"mix_id": mix_id, "error": "Not found"})
            continue
        try:
            tracks = mix.items()
            title = getattr(mix, "title", "Mix")
            name = f"{today} {title}"
            playlist = session.user.create_playlist(name, f"Auto-synced from Tidal")
            playlist.add([t.id for t in tracks])
            session.user.favorites.add_playlist(playlist.id)
            results.append({"mix": title, "playlist": name, "tracks": len(tracks), "success": True})
        except Exception as e:
            results.append({"mix_id": mix_id, "error": str(e)})

    # Cleanup old playlists
    cutoff = date.today() - timedelta(days=retention)
    deleted = []
    try:
        for pl in session.user.playlists():
            name = pl.name
            if len(name) >= 10 and name[4] == '-' and name[7] == '-':
                try:
                    pl_date = date.fromisoformat(name[:10])
                    if pl_date < cutoff and 'Auto-synced' in (getattr(pl, 'description', '') or ''):
                        pl.delete()
                        deleted.append(name)
                except ValueError:
                    pass
    except Exception as e:
        pass

    return {"success": True, "synced": results, "deleted": deleted}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
