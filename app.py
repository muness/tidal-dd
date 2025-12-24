"""Tidal Daily Discovery Sync - Railway/Render version"""

import os
import json
import tidalapi
from tidalapi.session import LinkLogin
from datetime import date
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

# Persistent storage (Railway/Render volume)
DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
TOKENS_FILE = DATA_DIR / "tokens.json"
PENDING_FILE = DATA_DIR / "pending.json"


def load_json(path):
    return json.loads(path.read_text()) if path.exists() else None

def save_json(path, data):
    path.write_text(json.dumps(data))


@app.get("/", response_class=HTMLResponse)
async def setup():
    """OAuth setup - user visits once"""

    # Already authenticated?
    tokens = load_json(TOKENS_FILE)
    if tokens:
        session = tidalapi.Session()
        if session.load_oauth_session(tokens["token_type"], tokens["access_token"], tokens.get("refresh_token")):
            return "<h1>Connected!</h1><p><a href='/sync'>Run sync now</a></p>"

    session = tidalapi.Session()

    # Check pending auth from previous visit
    pending = load_json(PENDING_FILE)
    if pending:
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
                return "<h1>Success!</h1><p>Tidal connected.</p><p><a href='/sync'>Run sync now</a></p>"
        except Exception as e:
            print(f"OAuth check failed: {type(e).__name__}: {e}")
            PENDING_FILE.unlink(missing_ok=True)
            return f"<h1>Auth check failed</h1><p>{type(e).__name__}: {e}</p><p><a href='/'>Try again</a></p>"

    # Start new OAuth
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
<p>1. <a href='https://{link}' target='_blank'>Login to Tidal</a></p>
<p>2. <a href='/'>Click here when done</a></p>"""


@app.get("/sync")
async def sync():
    """Create today's Daily Discovery playlist"""

    tokens = load_json(TOKENS_FILE)
    if not tokens:
        return {"error": "Not authenticated", "setup": "/"}

    session = tidalapi.Session()
    if not session.load_oauth_session(tokens["token_type"], tokens["access_token"], tokens.get("refresh_token")):
        return {"error": "Session expired"}

    # Find Daily Discovery
    mixes = session.mixes()
    dd = next((item for cat in mixes.categories if hasattr(cat, "items")
               for item in cat.items if "daily" in getattr(item, "title", "").lower()), None)

    if not dd:
        return {"error": "Daily Discovery not found"}

    tracks = dd.items()

    # Create dated playlist
    name = f"{date.today().isoformat()} Daily Discovery"
    playlist = session.user.create_playlist(name, "Auto-synced from Tidal")
    playlist.add([t.id for t in tracks])
    session.user.favorites.add_playlist(playlist.id)

    return {"success": True, "playlist": name, "tracks": len(tracks)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
