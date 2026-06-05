from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os
import json
import sqlite3
import time

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/app", StaticFiles(directory="../frontend", html=True), name="frontend")

# ── Token storage in SQLite ──────────────────────────────────────────────────
# SQLite works on Railway as long as we don't need persistence across deploys.
# For v1 this is fine — Costa just runs /login once after each deploy.
# (v2 would use Postgres or Redis for true persistence)

DB_PATH = "cosmos.db"

def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS tokens (
            id INTEGER PRIMARY KEY,
            token_json TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        )
    """)
    con.commit()
    con.close()

init_db()

def save_token(token_info: dict):
    con = sqlite3.connect(DB_PATH)
    existing = con.execute("SELECT id FROM tokens WHERE id = 1").fetchone()
    if existing:
        con.execute(
            "UPDATE tokens SET token_json = ?, updated_at = ? WHERE id = 1",
            (json.dumps(token_info), int(time.time()))
        )
    else:
        con.execute(
            "INSERT INTO tokens (id, token_json, updated_at) VALUES (1, ?, ?)",
            (json.dumps(token_info), int(time.time()))
        )
    con.commit()
    con.close()

def load_token() -> dict | None:
    con = sqlite3.connect(DB_PATH)
    row = con.execute("SELECT token_json FROM tokens WHERE id = 1").fetchone()
    con.close()
    if row:
        return json.loads(row[0])
    return None

# ── Spotify setup ────────────────────────────────────────────────────────────

SCOPES = "user-read-playback-state user-modify-playback-state playlist-read-private"

def get_spotify_oauth():
    return SpotifyOAuth(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
        scope=SCOPES,
        cache_path=None,      # ← no file cache anymore
        open_browser=False,
    )

def get_spotify_client():
    """Returns an authenticated Spotipy client, or None if not logged in."""
    token_info = load_token()
    if not token_info:
        return None

    oauth = get_spotify_oauth()

    # Refresh if expired
    if oauth.is_token_expired(token_info):
        token_info = oauth.refresh_access_token(token_info["refresh_token"])
        save_token(token_info)  # save refreshed token back to DB

    return spotipy.Spotify(auth=token_info["access_token"])


# ── Auth routes ──────────────────────────────────────────────────────────────

@app.get("/login")
def login():
    """Redirect bar owner to Spotify login page."""
    oauth = get_spotify_oauth()
    auth_url = oauth.get_authorize_url()
    return RedirectResponse(auth_url)


@app.get("/callback")
def callback(code: str = Query(...)):
    """Spotify redirects here after owner approves."""
    oauth = get_spotify_oauth()
    token_info = oauth.get_access_token(code, as_dict=True)
    save_token(token_info)  # ← saved to DB, not file
    return HTMLResponse("""
        <html><body style="font-family:sans-serif;text-align:center;padding:60px;background:#0a0a0f;color:white">
        <h2 style="color:#b8ff57">✅ Cosmos Queue connected to Spotify!</h2>
        <p style="color:#9999bb">You can close this tab. The queue is live!</p>
        </body></html>
    """)


@app.get("/auth-status")
def auth_status():
    sp = get_spotify_client()
    if not sp:
        return {"authenticated": False}
    user = sp.current_user()
    return {"authenticated": True, "display_name": user["display_name"]}


# ── Queue routes ─────────────────────────────────────────────────────────────

@app.get("/queue")
def get_queue():
    sp = get_spotify_client()
    if not sp:
        raise HTTPException(status_code=401, detail="Spotify not connected")

    playback = sp.current_playback()
    if not playback or not playback.get("item"):
        return {"now_playing": None, "queue": []}

    current = playback["item"]
    now_playing = {
        "id": current["id"],
        "name": current["name"],
        "artist": ", ".join(a["name"] for a in current["artists"]),
        "album_art": current["album"]["images"][0]["url"] if current["album"]["images"] else None,
        "progress_ms": playback["progress_ms"],
        "duration_ms": current["duration_ms"],
    }

    queue_data = sp.queue()
    queue = [
        {
            "id": t["id"],
            "name": t["name"],
            "artist": ", ".join(a["name"] for a in t["artists"]),
            "album_art": t["album"]["images"][0]["url"] if t["album"]["images"] else None,
        }
        for t in queue_data.get("queue", [])[:10]
    ]

    return {"now_playing": now_playing, "queue": queue}


class AddSongRequest(BaseModel):
    track_id: str


@app.post("/queue/add")
def add_to_queue(body: AddSongRequest):
    sp = get_spotify_client()
    if not sp:
        raise HTTPException(status_code=401, detail="Spotify not connected")

    track_uri = f"spotify:track:{body.track_id}"
    sp.add_to_queue(track_uri)
    return {"success": True, "message": "Song added to queue!"}


@app.get("/search")
def search_tracks(q: str = Query(..., min_length=2)):
    sp = get_spotify_client()
    if not sp:
        raise HTTPException(status_code=401, detail="Spotify not connected")

    results = sp.search(q=q, type="track", limit=8)
    tracks = [
        {
            "id": t["id"],
            "name": t["name"],
            "artist": ", ".join(a["name"] for a in t["artists"]),
            "album": t["album"]["name"],
            "album_art": t["album"]["images"][-1]["url"] if t["album"]["images"] else None,
            "duration_ms": t["duration_ms"],
        }
        for t in results["tracks"]["items"]
    ]
    return {"tracks": tracks}
