"""Tidal Daily Discovery Sync - Railway/Render version"""

import os
import json
import tidalapi
from tidalapi.session import LinkLogin
from datetime import date, datetime, timedelta
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(
        run_scheduled_sync,
        CronTrigger(hour=10, minute=0),  # 10:00 UTC daily
        id="daily_sync",
        replace_existing=True
    )
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)

# Persistent storage (Railway/Render volume)
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
TOKENS_FILE = DATA_DIR / "tokens.json"
PENDING_FILE = DATA_DIR / "pending.json"
CONFIG_FILE = DATA_DIR / "config.json"
PIN_FILE = DATA_DIR / "pin.json"
SYNC_STATUS_FILE = DATA_DIR / "sync_status.json"

AUTH_COOKIE = "tidal_sync_pin"

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

def get_pin():
    data = load_json(PIN_FILE)
    return data.get("pin") if data else None

def set_pin(pin):
    save_json(PIN_FILE, {"pin": pin})

def check_auth(cookie_pin: str = None) -> bool:
    stored_pin = get_pin()
    if not stored_pin:
        return True  # No PIN set yet
    return cookie_pin == stored_pin

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


def save_sync_status(trigger: str, results: list, deleted: list, error: str = None):
    status = {
        "last_sync": datetime.utcnow().isoformat() + "Z",
        "trigger": trigger,
        "results": results,
        "deleted_count": len(deleted),
        "error": error,
    }
    save_json(SYNC_STATUS_FILE, status)


def perform_sync(trigger: str = "manual"):
    """Core sync logic used by both manual and scheduled sync."""
    session = get_session()
    if not session:
        save_sync_status(trigger, [], [], error="Not connected to Tidal")
        return {"error": "Not connected to Tidal"}

    config = get_config()
    selected = config.get("selected_mixes", [])
    retention = config.get("retention_days", 7)

    if not selected:
        save_sync_status(trigger, [], [], error="No mixes selected")
        return {"error": "No mixes selected"}

    # Get mixes
    all_mixes = {}
    for cat in session.mixes().categories:
        if hasattr(cat, "items"):
            for item in cat.items:
                if hasattr(item, "id"):
                    all_mixes[item.id] = item

    results = []
    today = date.today().isoformat()

    # Get existing playlists to avoid duplicates
    existing_names = {pl.name for pl in session.user.playlists()}

    for mix_id in selected:
        mix = all_mixes.get(mix_id)
        if not mix:
            results.append({"mix_id": mix_id, "error": "Not found"})
            continue
        try:
            title = getattr(mix, "title", "Mix")
            name = f"{today} {title}"

            if name in existing_names:
                results.append({"mix": title, "playlist": name, "skipped": "Already exists"})
                continue

            tracks = mix.items()
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
    except Exception:
        pass

    save_sync_status(trigger, results, deleted)
    return {"results": results, "deleted": deleted}


def run_scheduled_sync():
    """Called by APScheduler for daily sync."""
    perform_sync(trigger="scheduled")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/debug/storage")
async def debug_storage():
    """Check if persistent storage is working."""
    return {
        "data_dir": str(DATA_DIR),
        "data_dir_exists": DATA_DIR.exists(),
        "pin_file_exists": PIN_FILE.exists(),
        "tokens_file_exists": TOKENS_FILE.exists(),
        "config_file_exists": CONFIG_FILE.exists(),
        "files_in_data_dir": [f.name for f in DATA_DIR.iterdir()] if DATA_DIR.exists() else [],
    }


@app.get("/login", response_class=HTMLResponse)
async def login_page(error: str = None):
    stored_pin = get_pin()
    if not stored_pin:
        # First time - set PIN
        return """<h1>Tidal Mix Sync - Setup</h1>
<p>Set a PIN to protect your instance:</p>
<form method="POST" action="/login">
<p><input type="password" name="pin" placeholder="Choose a PIN" required autofocus style="font-size:18px;padding:8px"></p>
<p><button type="submit" style="font-size:18px;padding:8px 16px">Set PIN</button></p>
</form>"""

    error_msg = "<p style='color:red'>Wrong PIN</p>" if error else ""
    return f"""<h1>Tidal Mix Sync</h1>
{error_msg}
<form method="POST" action="/login">
<p><input type="password" name="pin" placeholder="Enter PIN" required autofocus style="font-size:18px;padding:8px"></p>
<p><button type="submit" style="font-size:18px;padding:8px 16px">Login</button></p>
</form>"""


@app.post("/login")
async def login_submit(request: Request):
    form = await request.form()
    pin = form.get("pin", "").strip()

    if not pin:
        return RedirectResponse("/login?error=1", status_code=303)

    stored_pin = get_pin()
    if not stored_pin:
        # First time - save PIN
        set_pin(pin)
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(AUTH_COOKIE, pin, httponly=True, max_age=86400*365)
        return response

    if pin == stored_pin:
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(AUTH_COOKIE, pin, httponly=True, max_age=86400*365)
        return response

    return RedirectResponse("/login?error=1", status_code=303)


def auth_required(cookie_pin: str = Cookie(None, alias=AUTH_COOKIE)):
    """Check if auth is required and redirect if not authenticated."""
    if not check_auth(cookie_pin):
        return RedirectResponse("/login", status_code=303)
    return None


@app.get("/check_tidal_auth")
async def check_tidal_auth():
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

            # Auto-select daily mixes if no config exists
            config = get_config()
            if not config.get("selected_mixes"):
                try:
                    daily_ids = []
                    for cat in session.mixes().categories:
                        if hasattr(cat, "items"):
                            for item in cat.items:
                                title = getattr(item, "title", "")
                                if "daily" in title.lower() and hasattr(item, "id"):
                                    daily_ids.append(item.id)
                    if daily_ids:
                        config["selected_mixes"] = daily_ids
                        save_json(CONFIG_FILE, config)
                except Exception:
                    pass  # Non-critical, user can configure manually

            return {"success": True, "message": "Authorization complete!"}
        return {"pending": True, "message": "Login check failed after token processing"}
    except Exception as e:
        err_str = str(e).lower()
        if "expired" in err_str:
            PENDING_FILE.unlink(missing_ok=True)
            return {"expired": True, "message": "Authorization expired, refresh to try again"}
        if "pending" in err_str or "authorization_pending" in err_str:
            return {"pending": True, "message": "Waiting for authorization..."}
        # Return actual error for debugging
        return {"error": True, "message": f"Auth error: {e}"}


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # Always require PIN setup/login first
    stored_pin = get_pin()
    cookie_pin = request.cookies.get(AUTH_COOKIE)

    if not stored_pin or cookie_pin != stored_pin:
        return RedirectResponse("/login", status_code=303)

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
<li><a href="/status">Sync status</a></li>
<li><a href="/logout">Disconnect Tidal</a></li>
</ul>
<p style="margin-top:30px;font-size:14px;color:#666;"><a href="https://buymeacoffee.com/muness" target="_blank">Buy me a coffee</a> if you find this useful!</p>"""

    pending = load_json(PENDING_FILE)
    if pending:
        return f"""<h1>Waiting for Tidal Authorization</h1>
<p id="status">Checking...</p>
<p><a href='https://{pending['verification_uri_complete']}' target='_blank'>Click here if you haven't authorized yet</a></p>
<p><a href='/reset_auth'>Start over</a> (if authorization expired)</p>
<script>
async function check() {{
    const r = await fetch('/check_tidal_auth');
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
    const r = await fetch('/check_tidal_auth');
    const d = await r.json();
    document.getElementById('status').innerText = d.message;
    if (d.error) document.getElementById('status').style.color = 'red';
    if (d.success) location.href = '/';
    else if (d.expired) location.href = '/';
}}
setTimeout(() => {{ check(); setInterval(check, 3000); }}, 5000);
</script>"""


@app.get("/logout")
async def logout(request: Request):
    cookie_pin = request.cookies.get(AUTH_COOKIE)
    if not check_auth(cookie_pin):
        return RedirectResponse("/login", status_code=303)
    TOKENS_FILE.unlink(missing_ok=True)
    PENDING_FILE.unlink(missing_ok=True)
    return HTMLResponse("<h1>Disconnected</h1><p><a href='/'>Connect again</a></p>")


@app.get("/reset_auth")
async def reset_auth(request: Request):
    """Clear pending auth and start fresh."""
    cookie_pin = request.cookies.get(AUTH_COOKIE)
    if not check_auth(cookie_pin):
        return RedirectResponse("/login", status_code=303)
    PENDING_FILE.unlink(missing_ok=True)
    return RedirectResponse("/", status_code=303)


@app.get("/api/mixes")
async def get_mixes(request: Request):
    cookie_pin = request.cookies.get(AUTH_COOKIE)
    if not check_auth(cookie_pin):
        return {"error": "Not authenticated"}

    session = get_session()
    if not session:
        return {"error": "Not authenticated"}

    mixes = []
    for category in session.mixes().categories:
        if hasattr(category, "items"):
            for item in category.items:
                if hasattr(item, "id"):
                    title = getattr(item, "title", "Unknown")
                    mixes.append({
                        "id": item.id,
                        "title": title,
                        "sub_title": getattr(item, "sub_title", ""),
                        "is_daily": "daily" in title.lower(),
                    })
    return {"mixes": mixes}


@app.get("/api/config")
async def get_config_api(request: Request):
    cookie_pin = request.cookies.get(AUTH_COOKIE)
    if not check_auth(cookie_pin):
        return {"error": "Not authenticated"}
    return get_config()


@app.post("/api/config")
async def save_config_api(request: Request):
    cookie_pin = request.cookies.get(AUTH_COOKIE)
    if not check_auth(cookie_pin):
        return {"error": "Not authenticated"}

    data = await request.json()
    config = get_config()
    if "selected_mixes" in data:
        config["selected_mixes"] = data["selected_mixes"]
    if "retention_days" in data:
        config["retention_days"] = max(1, min(365, int(data["retention_days"])))
    save_json(CONFIG_FILE, config)
    return {"success": True, "config": config}


@app.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    cookie_pin = request.cookies.get(AUTH_COOKIE)
    if not check_auth(cookie_pin):
        return RedirectResponse("/login", status_code=303)

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

    // Default: select "daily" mixes if nothing selected yet
    let selected = config.selected_mixes || [];
    if (selected.length === 0) {
        selected = mixes.filter(m => m.is_daily).map(m => m.id);
    }

    document.getElementById('mixes').innerHTML = mixes.map(m =>
        '<label style="display:block;margin:8px 0"><input type="checkbox" value="'+m.id+'" '+(selected.includes(m.id)?'checked':'')+'> <strong>'+m.title+'</strong> '+(m.sub_title||'')+'</label>'
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


@app.get("/status", response_class=HTMLResponse)
async def status_page(request: Request):
    cookie_pin = request.cookies.get(AUTH_COOKIE)
    if not check_auth(cookie_pin):
        return RedirectResponse("/login", status_code=303)

    status = load_json(SYNC_STATUS_FILE)
    next_run = scheduler.get_job("daily_sync")
    next_run_str = next_run.next_run_time.strftime("%Y-%m-%d %H:%M UTC") if next_run and next_run.next_run_time else "Not scheduled"

    html = "<h1>Sync Status</h1>"

    if not status:
        html += "<p>No sync has been run yet.</p>"
    else:
        html += f"<p><strong>Last sync:</strong> {status['last_sync']}</p>"
        html += f"<p><strong>Trigger:</strong> {status['trigger']}</p>"

        if status.get("error"):
            html += f"<p style='color:red'><strong>Error:</strong> {status['error']}</p>"
        else:
            results = status.get("results", [])
            created = [r for r in results if r.get("success")]
            skipped = [r for r in results if r.get("skipped")]
            errors = [r for r in results if r.get("error")]

            if created:
                html += "<h3>Created</h3><ul>"
                for r in created:
                    html += f"<li>{r['playlist']} ({r['tracks']} tracks)</li>"
                html += "</ul>"

            if skipped:
                html += "<h3>Skipped</h3><ul>"
                for r in skipped:
                    html += f"<li>{r['playlist']}</li>"
                html += "</ul>"

            if errors:
                html += "<h3 style='color:red'>Errors</h3><ul>"
                for r in errors:
                    html += f"<li>{r.get('mix', r.get('mix_id', 'Unknown'))}: {r['error']}</li>"
                html += "</ul>"

            if status.get("deleted_count", 0) > 0:
                html += f"<p>Cleaned up {status['deleted_count']} old playlist(s)</p>"

    html += f"<p style='margin-top:20px'><strong>Next scheduled sync:</strong> {next_run_str}</p>"
    html += "<p><a href='/'>← Back to home</a></p>"

    return HTMLResponse(html)


@app.get("/cron/sync")
async def cron_sync(key: str = None):
    """Secret-key endpoint for external cron services (e.g., cron-job.org)."""
    cron_key = os.getenv("CRON_SECRET")
    if not cron_key or key != cron_key:
        return {"error": "Unauthorized"}, 401
    result = perform_sync(trigger="cron")
    return {"status": "ok", "result": result}


@app.get("/sync", response_class=HTMLResponse)
async def sync(request: Request):
    cookie_pin = request.cookies.get(AUTH_COOKIE)
    if not check_auth(cookie_pin):
        return RedirectResponse("/login", status_code=303)

    result = perform_sync(trigger="manual")

    if result.get("error"):
        return HTMLResponse(f"<h1>Sync Error</h1><p>{result['error']}</p><p><a href='/'>← Back</a></p>")

    results = result.get("results", [])
    deleted = result.get("deleted", [])

    html = "<h1>Sync Complete</h1>"

    created = [r for r in results if r.get("success")]
    skipped = [r for r in results if r.get("skipped")]
    errors = [r for r in results if r.get("error")]

    if created:
        html += "<h2>Created</h2><ul>"
        for r in created:
            html += f"<li><strong>{r['playlist']}</strong> ({r['tracks']} tracks)</li>"
        html += "</ul>"

    if skipped:
        html += "<h2>Skipped (already exist)</h2><ul>"
        for r in skipped:
            html += f"<li>{r['playlist']}</li>"
        html += "</ul>"

    if errors:
        html += "<h2 style='color:red'>Errors</h2><ul>"
        for r in errors:
            html += f"<li>{r.get('mix', r.get('mix_id', 'Unknown'))}: {r['error']}</li>"
        html += "</ul>"

    if deleted:
        html += f"<h2>Cleaned up</h2><p>Deleted {len(deleted)} old playlist(s)</p>"

    if not created and not skipped and not errors:
        html += "<p>Nothing to sync.</p>"

    html += "<p style='margin-top:20px'><a href='/'>← Back to home</a></p>"

    return HTMLResponse(html)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
