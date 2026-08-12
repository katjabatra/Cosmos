from fastapi import FastAPI, HTTPException, Query, Request
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
from datetime import date

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/app", StaticFiles(directory="../frontend", html=True), name="frontend")

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
    con.execute("""
        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT NOT NULL,
            track_id TEXT NOT NULL,
            vote_date TEXT NOT NULL,
            created_at INTEGER NOT NULL
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
        cache_path=None,
        open_browser=False,
    )

def get_spotify_client():
    token_info = load_token()
    if not token_info:
        return None
    oauth = get_spotify_oauth()
    if oauth.is_token_expired(token_info):
        token_info = oauth.refresh_access_token(token_info["refresh_token"])
        save_token(token_info)
    return spotipy.Spotify(auth=token_info["access_token"])

def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host

# ── Auth routes ──────────────────────────────────────────────────────────────

@app.get("/login")
def login():
    oauth = get_spotify_oauth()
    auth_url = oauth.get_authorize_url()
    return RedirectResponse(auth_url)

@app.get("/callback")
def callback(code: str = Query(...)):
    oauth = get_spotify_oauth()
    token_info = oauth.get_access_token(code, as_dict=True)
    save_token(token_info)
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

    # Attach vote counts and original position
    vote_counts = get_vote_counts()
    for i, song in enumerate(queue):
        song["votes"] = vote_counts.get(song["id"], 0)
        song["original_position"] = i  # preserve Spotify queue order

    # Sort: primary = votes descending, secondary = original position ascending (FIFO on tie)
    queue.sort(key=lambda x: (-x["votes"], x["original_position"]))

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

# ── Voting routes ─────────────────────────────────────────────────────────────

MAX_VOTES_PER_DAY = 3

def get_vote_counts() -> dict:
    """Returns {track_id: vote_count} for today."""
    today = str(date.today())
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        "SELECT track_id, COUNT(*) FROM votes WHERE vote_date = ? GROUP BY track_id",
        (today,)
    ).fetchall()
    con.close()
    return {row[0]: row[1] for row in rows}

def get_votes_used_today(ip: str) -> int:
    today = str(date.today())
    con = sqlite3.connect(DB_PATH)
    count = con.execute(
        "SELECT COUNT(*) FROM votes WHERE ip = ? AND vote_date = ?",
        (ip, today)
    ).fetchone()[0]
    con.close()
    return count

def has_voted_for_track_today(ip: str, track_id: str) -> bool:
    today = str(date.today())
    con = sqlite3.connect(DB_PATH)
    count = con.execute(
        "SELECT COUNT(*) FROM votes WHERE ip = ? AND track_id = ? AND vote_date = ?",
        (ip, track_id, today)
    ).fetchone()[0]
    con.close()
    return count > 0

@app.get("/votes/status")
def votes_status(request: Request):
    """How many votes does this IP have left today?"""
    ip = get_client_ip(request)
    used = get_votes_used_today(ip)
    remaining = max(0, MAX_VOTES_PER_DAY - used)
    vote_counts = get_vote_counts()
    return {
        "votes_remaining": remaining,
        "votes_used": used,
        "max_votes": MAX_VOTES_PER_DAY,
        "vote_counts": vote_counts
    }

class VoteRequest(BaseModel):
    track_id: str

@app.post("/votes/cast")
def cast_vote(body: VoteRequest, request: Request):
    ip = get_client_ip(request)
    today = str(date.today())

    used = get_votes_used_today(ip)
    if used >= MAX_VOTES_PER_DAY:
        raise HTTPException(status_code=429, detail="No votes left for today")

    if has_voted_for_track_today(ip, body.track_id):
        raise HTTPException(status_code=409, detail="Already voted for this song today")

    con = sqlite3.connect(DB_PATH)
    con.execute(
        "INSERT INTO votes (ip, track_id, vote_date, created_at) VALUES (?, ?, ?, ?)",
        (ip, body.track_id, today, int(time.time()))
    )
    con.commit()
    con.close()

    remaining = MAX_VOTES_PER_DAY - used - 1
    return {"success": True, "votes_remaining": remaining}
