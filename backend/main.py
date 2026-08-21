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
import psycopg2
import psycopg2.extras
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

#def get_db():
 #   return psycopg2.connect(os.getenv("DATABASE_URL"), sslmode="require")


def get_db():
    return psycopg2.connect(
        os.getenv("DATABASE_URL"), 
        sslmode="require", 
        cursor_factory=psycopg2.extras.RealDictCursor
    )

def init_db():
    con = get_db()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tokens (
            id INTEGER PRIMARY KEY,
            token_json TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS votes (
            id SERIAL PRIMARY KEY,
            ip TEXT NOT NULL,
            track_id TEXT NOT NULL,
            vote_date TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS song_plays (
            id SERIAL PRIMARY KEY,
            track_id TEXT NOT NULL,
            track_name TEXT NOT NULL,
            track_artist TEXT NOT NULL,
            play_date TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS genre_clicks (
            id SERIAL PRIMARY KEY,
            genre TEXT NOT NULL,
            click_date TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS add_limits (
            id SERIAL PRIMARY KEY,
            ip TEXT NOT NULL,
            track_id TEXT NOT NULL,
            add_date TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
    """)
    con.commit()
    cur.close()
    con.close()

init_db()

def save_token(token_info: dict):
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT id FROM tokens WHERE id = 1")
    existing = cur.fetchone()
    if existing:
        cur.execute(
            "UPDATE tokens SET token_json = %s, updated_at = %s WHERE id = 1",
            (json.dumps(token_info), int(time.time()))
        )
    else:
        cur.execute(
            "INSERT INTO tokens (id, token_json, updated_at) VALUES (1, %s, %s)",
            (json.dumps(token_info), int(time.time()))
        )
    con.commit()
    cur.close()
    con.close()

def load_token() -> dict | None:
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT token_json FROM tokens WHERE id = 1")
    row = cur.fetchone()
    cur.close()
    con.close()
    if row:
        return json.loads(row["token_json"])
    return None

# ── Spotify setup ─────────────────────────────────────────────────────────────

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

# ── Auth routes ───────────────────────────────────────────────────────────────

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
        <html><body style="font-family:sans-serif;text-align:center;padding:60px;background:#0d0a14;color:white">
        <h2 style="color:#c97ef5">✅ Cosmos Jukebox mit Spotify verbunden!</h2>
        <p style="color:#9988bb">Du kannst diesen Tab schließen.</p>
        </body></html>
    """)

@app.get("/auth-status")
def auth_status():
    sp = get_spotify_client()
    if not sp:
        return {"authenticated": False}
    user = sp.current_user()
    return {"authenticated": True, "display_name": user["display_name"]}

# ── Queue routes ──────────────────────────────────────────────────────────────

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

    vote_counts = get_vote_counts()
    for i, song in enumerate(queue):
        song["votes"] = vote_counts.get(song["id"], 0)
        song["original_position"] = i

    queue.sort(key=lambda x: (-x["votes"], x["original_position"]))

    return {"now_playing": now_playing, "queue": queue}


class AddSongRequest(BaseModel):
    track_id: str
    track_name: str = ""
    track_artist: str = ""

# NEU: Prüft wie viele Songs eine IP heute schon hinzugefügt hat
def get_adds_today(ip: str) -> int:
    today = str(date.today())
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM add_limits WHERE ip = %s AND add_date = %s", (ip, today))
    row = cur.fetchone()
    cur.close()
    con.close()
    return row["cnt"] if row else 0

MAX_ADDS_PER_DAY = 3  # Jeder Gast darf max 3 Songs pro Tag hinzufügen

@app.post("/queue/add")
def add_to_queue(body: AddSongRequest, request: Request):
    sp = get_spotify_client()
    if not sp:
        raise HTTPException(status_code=401, detail="Spotify not connected")

    # NEU: 3-Song-Limit pro IP pro Tag prüfen
    ip = get_client_ip(request)
    adds_today = get_adds_today(ip)
    if adds_today >= MAX_ADDS_PER_DAY:
        raise HTTPException(status_code=429, detail="Song limit reached for today")

    track_uri = f"spotify:track:{body.track_id}"
    sp.add_to_queue(track_uri)

    today = str(date.today())

    # NEU: Add-Limit tracken
    con = get_db()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO add_limits (ip, track_id, add_date, created_at) VALUES (%s, %s, %s, %s)",
        (ip, body.track_id, today, int(time.time()))
    )
    cur.execute(
        "INSERT INTO song_plays (track_id, track_name, track_artist, play_date, created_at) VALUES (%s, %s, %s, %s, %s)",
        (body.track_id, body.track_name, body.track_artist, today, int(time.time()))
    )
    con.commit()
    cur.close()
    con.close()

    remaining_adds = MAX_ADDS_PER_DAY - adds_today - 1
    return {"success": True, "adds_remaining": remaining_adds}

@app.get("/search")
def search_tracks(q: str = Query(..., min_length=2)):
    sp = get_spotify_client()
    if not sp:
        raise HTTPException(status_code=401, detail="Spotify not connected")
    results = sp.search(q=q, type="track", limit=10)
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

# ── Stats routes ──────────────────────────────────────────────────────────────

# NEU: Gibt den meistgespielten Song heute zurück (All Time Favorite des Tages)
@app.get("/stats/top-song")
def get_top_song():
    today = str(date.today())
    con = get_db()
    cur = con.cursor()
    cur.execute("""
        SELECT track_id, track_name, track_artist, COUNT(*) as cnt
        FROM song_plays
        WHERE play_date = %s
        GROUP BY track_id, track_name, track_artist
        ORDER BY cnt DESC
        LIMIT 1
    """, (today,))
    row = cur.fetchone()
    cur.close()
    con.close()
    if not row:
        return {"top_song": None}
    return {"top_song": {"id": row["track_id"], "name": row["track_name"], "artist": row["track_artist"], "count": row["cnt"]}}

# NEU: Speichert einen Genre-Klick
class GenreClickRequest(BaseModel):
    genre: str

@app.post("/genre/click")
def genre_click(body: GenreClickRequest):
    today = str(date.today())
    con = get_db()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO genre_clicks (genre, click_date, created_at) VALUES (%s, %s, %s)",
        (body.genre, today, int(time.time()))
    )
    con.commit()
    cur.close()
    con.close()
    return {"success": True}

# NEU: Gibt die Top 3 Genres heute zurück (für Treppchen)
@app.get("/stats/top-genres")
def get_top_genres():
    today = str(date.today())
    con = get_db()
    cur = con.cursor()
    cur.execute("""
        SELECT genre, COUNT(*) as cnt
        FROM genre_clicks
        WHERE click_date = %s
        GROUP BY genre
        ORDER BY cnt DESC
        LIMIT 3
    """, (today,))
    rows = cur.fetchall()
    cur.close()
    con.close()
    return {"top_genres": [{"genre": r["genre"], "count": r["cnt"]} for r in rows]}

# NEU: Gibt zurück wie viele Songs eine IP heute noch hinzufügen darf
@app.get("/adds/status")
def adds_status(request: Request):
    ip = get_client_ip(request)
    used = get_adds_today(ip)
    remaining = max(0, MAX_ADDS_PER_DAY - used)
    return {"adds_remaining": remaining, "adds_used": used, "max_adds": MAX_ADDS_PER_DAY}

# ── Voting routes ─────────────────────────────────────────────────────────────

MAX_VOTES_PER_DAY = 3

def get_vote_counts() -> dict:
    today = str(date.today())
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT track_id, COUNT(*) as cnt FROM votes WHERE vote_date = %s GROUP BY track_id", (today,))
    rows = cur.fetchall()
    cur.close()
    con.close()
    return {row["track_id"]: row["cnt"] for row in rows}

def get_votes_used_today(ip: str) -> int:
    today = str(date.today())
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM votes WHERE ip = %s AND vote_date = %s", (ip, today))
    row = cur.fetchone()
    cur.close()
    con.close()
    return row["cnt"] if row else 0

def has_voted_for_track_today(ip: str, track_id: str) -> bool:
    today = str(date.today())
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM votes WHERE ip = %s AND track_id = %s AND vote_date = %s", (ip, track_id, today))
    row = cur.fetchone()
    cur.close()
    con.close()
    return (row["cnt"] > 0) if row else False

@app.get("/votes/status")
def votes_status(request: Request):
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

    con = get_db()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO votes (ip, track_id, vote_date, created_at) VALUES (%s, %s, %s, %s)",
        (ip, body.track_id, today, int(time.time()))
    )
    con.commit()
    cur.close()
    con.close()

    remaining = MAX_VOTES_PER_DAY - used - 1
    return {"success": True, "votes_remaining": remaining}






# 21.8 Änderungen Admin Dashboard 

# 1. KPIs
@app.get("/api/stats/kpis")
def get_kpis():
    conn = get_db()
    cur = conn.cursor()
    
    now = int(time.time())
    today_start = now - (now % 86400)
    week_start = now - (7 * 86400)

    cur.execute("""
        SELECT 
            COUNT(CASE WHEN created_at >= %s THEN 1 END) as scans_today,
            COUNT(CASE WHEN created_at >= %s THEN 1 END) as scans_this_week
        FROM votes;
    """, (today_start, week_start))
    
    stats = cur.fetchone()
    cur.close()
    conn.close()
    return stats

# 2. Peak-Zeiten
@app.get("/api/stats/hourly")
def get_hourly_stats():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT 
            TO_CHAR(to_timestamp(created_at), 'HH24:00') as hour, 
            COUNT(*) as scans
        FROM votes
        GROUP BY hour
        ORDER BY hour ASC;
    """)
    
    hourly_data = cur.fetchall()
    cur.close()
    conn.close()
    return hourly_data

# 3. Top 5 Songs
# 3. Top 5 Songs
@app.get("/api/stats/top-songs")
def get_top_songs():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT 
            track_name as title, 
            track_artist as artist, 
            COUNT(*) as scans
        FROM song_plays
        GROUP BY track_name, track_artist
        ORDER BY scans DESC
        LIMIT 5;
    """)
    
    top_songs = cur.fetchall()
    cur.close()
    conn.close()
    return top_songs