# Tidal Daily Discovery Sync

Automatically sync your Tidal Daily Discovery (and other mixes) to dated playlists that appear in Roon.

## Why?

Tidal's "My Daily Discovery" and other dynamic mixes don't appear in Roon. This tool creates regular playlists from them, which Roon can sync.

## Vision

A **self-service tool** for non-technical users:
- Deploy your own instance (no shared service / no data sharing)
- Web UI for Tidal OAuth login
- **Config UI to select which mixes to sync** (Daily Discovery, My Mix 1-6, etc.)
- **Retention settings** (how many days to keep old playlists)
- One-click deploy to Railway (~$1/month)

## Current Status

- [x] OAuth login via web UI
- [x] Daily Discovery → playlist sync
- [x] Favorites playlist (for Roon visibility)
- [x] Config UI for mix selection
- [x] Retention settings / auto-cleanup
- [x] Scheduled daily sync (cron)
- [x] Railway template for one-click deploy

## Deploy

### Option 1: Railway (easiest)

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.com/deploy/stunning-inspiration)

**Cost:** ~$1/month on Railway (Hobby plan)

1. Click "Deploy on Railway" above
2. Wait for deployment to complete
3. Find your app URL:
   - Click on the **tidal-dd** service in the left panel
   - Go to **Settings** → **Networking**
   - Copy the public URL (e.g., `xxx.up.railway.app`)
4. Visit your app URL and follow the setup wizard

**Updating Railway:** Click on your service → **Settings** → **Source** → **Check for updates**

### Option 2: Docker Compose (self-hosted)

Download [`docker-compose.yml`](https://github.com/muness/tidal-dd/blob/main/docker-compose.yml):

```bash
curl -O https://raw.githubusercontent.com/muness/tidal-dd/main/docker-compose.yml

# Start the container
docker compose up -d
```

Visit `http://localhost:8080` (or your server's IP)

**Updating Docker:**
```bash
docker compose pull
docker compose up -d
```

**Note:** For daily automatic syncs, set up a cron job to call `/sync`:
```bash
0 10 * * * curl -s http://localhost:8080/sync > /dev/null
```

## Setup

**Note:** Safari (especially on iPhone) may not work for Tidal login. Use Chrome on a computer.

1. Visit your app URL
2. Set a PIN to protect your instance
3. Click the Tidal login link and authenticate
4. Select which mixes to sync (Daily Discovery is selected by default)
5. Done! (Railway syncs daily at 10am UTC automatically)

## Manual Sync

Visit `/sync` to trigger a sync manually.

## How it works

- Creates a playlist named `YYYY-MM-DD <Mix Name>` for each selected mix
- Favorites the playlist so it syncs to Roon
- Automatically deletes playlists older than retention period
- Roon picks it up on next library sync

**Tip:** To see new playlists in Roon immediately, go to **Settings > Services > TIDAL > Edit > Sync library now**

## Development

```bash
# Local Docker
docker build -t tidal-dd . && docker run -p 8080:8080 -v $(pwd)/data:/data tidal-dd

# Local Python
pip install -r requirements.txt
DATA_DIR=./data python -m uvicorn app:app --reload
```

---

If you find this useful, [buy me a coffee](https://buymeacoffee.com/muness)!
