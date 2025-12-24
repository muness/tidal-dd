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

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.com/deploy/stunning-inspiration)

**Cost:** ~$1/month on Railway (Hobby plan)

> **Note:** After deploying, Railway will automatically create a persistent volume for your data.

## Setup

1. Click "Deploy on Railway" above
2. Wait for deployment to complete
3. Find your app URL:
   - Click on the **tidal-dd** service in the left panel
   - Go to **Settings** → **Networking**
   - Copy the public URL (e.g., `xxx.up.railway.app`)
4. Visit your app URL
5. Set a PIN to protect your instance
6. Click the Tidal login link and authenticate
7. Select which mixes to sync (Daily Discovery is selected by default)
8. Done! Sync runs daily at 10am UTC.

## Updating

To get the latest version:
1. Click on your **tidal-dd** service
2. Go to **Settings** → scroll to **Source**
3. Click **Check for updates** under "Upstream Repo"
4. If updates are available, Railway will redeploy automatically

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
