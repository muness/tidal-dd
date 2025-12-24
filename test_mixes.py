#!/usr/bin/env python3
"""Quick test to see if we can access Daily Discovery via tidalapi."""

import tidalapi
from pathlib import Path

SESSION_FILE = Path("session.json")


def login():
    """Login to Tidal, reusing session if available."""
    session = tidalapi.Session()

    if SESSION_FILE.exists():
        print("Loading existing session...")
        session.load_session_from_file(SESSION_FILE)
        if session.check_login():
            print(f"Logged in (user id: {session.user.id})")
            return session
        print("Session expired, re-authenticating...")

    print("Starting OAuth login...")
    login_info, future = session.login_oauth()
    print(f"\nOpen this URL in your browser:\n{login_info.verification_uri_complete}\n")
    print("Waiting for you to complete login in browser...")

    future.result()  # Blocks until login completes

    if session.check_login():
        session.save_session_to_file(SESSION_FILE)
        print(f"Logged in (user id: {session.user.id})")
        return session
    else:
        raise Exception("Login failed")


def explore_mixes(session: tidalapi.Session):
    """Fetch and display user's mixes."""
    print("\n--- Fetching mixes ---")

    try:
        mixes_page = session.mixes()
        print(f"Page title: {mixes_page.title if hasattr(mixes_page, 'title') else 'N/A'}")

        # Iterate through categories on the page
        for i, category in enumerate(mixes_page.categories):
            print(f"\nCategory {i}: {type(category).__name__}")
            if hasattr(category, "title"):
                print(f"  Title: {category.title}")

            # Try to get items from this category
            if hasattr(category, "items"):
                for j, item in enumerate(category.items):
                    print(f"  [{j}] {type(item).__name__}: ", end="")
                    if hasattr(item, "title"):
                        print(f"{item.title}", end="")
                    if hasattr(item, "sub_title"):
                        print(f" - {item.sub_title}", end="")
                    if hasattr(item, "id"):
                        print(f" (id: {item.id})", end="")
                    print()

                    # If this looks like Daily Discovery, show tracks
                    title = getattr(item, "title", "").lower()
                    if "daily" in title or "discovery" in title:
                        print(f"\n  !!! Found potential Daily Discovery: {item.title}")
                        if hasattr(item, "items"):
                            tracks = item.items()
                            print(f"  Tracks ({len(tracks)}):")
                            for t in tracks[:5]:  # First 5
                                print(f"    - {t.artist.name} - {t.name}")
                            if len(tracks) > 5:
                                print(f"    ... and {len(tracks) - 5} more")

    except Exception as e:
        print(f"Error fetching mixes: {e}")
        import traceback
        traceback.print_exc()


def test_create_playlist(session: tidalapi.Session):
    """Quick test: create a playlist from Daily Discovery and favorite it."""
    print("\n--- Testing playlist creation ---")

    # Get Daily Discovery
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
        print("Could not find Daily Discovery")
        return

    tracks = daily_discovery.items()
    print(f"Creating playlist with {len(tracks)} tracks...")

    playlist = session.user.create_playlist(
        "Test Daily Discovery",
        "Testing if this shows up in Roon"
    )
    playlist.add([t.id for t in tracks])
    session.user.favorites.add_playlist(playlist.id)

    print(f"Created and favorited playlist")
    print("Check if it appears in Roon!")


def main():
    session = login()
    test_create_playlist(session)


if __name__ == "__main__":
    main()
