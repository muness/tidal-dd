import tidalapi
import json
from datetime import date

def handler(pd: "pipedream"):
    data_store = pd.inputs["data_store"]

    # Check for tokens
    if "tidal_tokens" not in data_store:
        print("No tokens found - user needs to complete setup first")
        return {"error": "Not authenticated"}

    # Load session
    tokens = json.loads(data_store["tidal_tokens"])
    session = tidalapi.Session()
    if not session.load_oauth_session(
        tokens["token_type"],
        tokens["access_token"],
        tokens.get("refresh_token")
    ):
        print("Failed to load session - tokens may be expired")
        return {"error": "Session expired"}

    # Get Daily Discovery
    print("Fetching mixes...")
    mixes_page = session.mixes()

    daily_discovery = None
    for category in mixes_page.categories:
        if hasattr(category, "items"):
            for item in category.items:
                if "daily" in getattr(item, "title", "").lower():
                    daily_discovery = item
                    break
        if daily_discovery:
            break

    if not daily_discovery:
        print("Could not find Daily Discovery mix")
        return {"error": "Daily Discovery not found"}

    # Get tracks
    tracks = daily_discovery.items()
    print(f"Found {len(tracks)} tracks in Daily Discovery")

    # Create playlist with today's date
    today = date.today().isoformat()
    playlist_name = f"{today} Daily Discovery"

    print(f"Creating playlist: {playlist_name}")
    playlist = session.user.create_playlist(playlist_name, "Auto-synced from Tidal Daily Discovery")

    # Add tracks
    track_ids = [t.id for t in tracks]
    playlist.add(track_ids)
    print(f"Added {len(track_ids)} tracks")

    # Favorite the playlist so it shows in Roon
    session.user.favorites.add_playlist(playlist.id)
    print("Favorited playlist")

    return {
        "success": True,
        "playlist_name": playlist_name,
        "track_count": len(track_ids)
    }
