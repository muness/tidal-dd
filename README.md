# Tidal Daily Discovery Sync

Automatically sync your Tidal Daily Discovery to a dated playlist that appears in Roon.

## Why?

Tidal's "My Daily Discovery" is a dynamic mix that doesn't appear in Roon. This tool creates a regular playlist from it daily, which Roon can sync.

## Deploy

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/YOUR_TEMPLATE_ID)

**Cost:** ~$1/month on Railway

## Setup

1. Click "Deploy on Railway" above
2. Visit your app URL
3. Click the Tidal login link and authenticate
4. Click "done" to confirm
5. Done! Sync runs daily.

## Manual Sync

Visit `/sync` to trigger a sync manually.

## How it works

- Creates a playlist named `YYYY-MM-DD Daily Discovery` each day
- Favorites the playlist so it syncs to Roon
- Roon picks it up on next library sync
