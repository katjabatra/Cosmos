# 🎵 Cosmos Queue

Guest-facing song queue app powered by Spotify.

---

## Local Setup

### 1. Spotify Developer App
1. https://developer.spotify.com/dashboard → Create App
2. Redirect URI: `http://127.0.0.1:8000/callback`
3. Copy Client ID + Client Secret

### 2. Configure .env
```
SPOTIFY_CLIENT_ID=your_id
SPOTIFY_CLIENT_SECRET=your_secret
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8000/callback
```

### 3. Run locally
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 4. Connect Spotify (once)
Open: `http://127.0.0.1:8000/login`

### 5. Guest app
Open: `http://127.0.0.1:8000/app`

---

## Deploy to Railway

### 1. Push to GitHub first
```bash
git init
git add .
git commit -m "initial commit"
# create repo on github.com, then:
git remote add origin https://github.com/YOURNAME/cosmos-queue.git
git push -u origin main
```

### 2. Railway setup
1. Go to railway.app → New Project → Deploy from GitHub
2. Select your repo
3. Go to Variables tab, add:
   - `SPOTIFY_CLIENT_ID`
   - `SPOTIFY_CLIENT_SECRET`  
   - `SPOTIFY_REDIRECT_URI` = `https://your-app.railway.app/callback`

### 3. Update Spotify Dashboard
Add the Railway URL as Redirect URI:
`https://your-app.railway.app/callback`

### 4. Connect Costa's Spotify
Open: `https://your-app.railway.app/login`
→ Costa logs in with his Spotify account → done!

### 5. Share with guests
`https://your-app.railway.app/app`
→ Generate a QR code pointing to this URL and put it on the bar!

---

## Routes
| Route | Who | What |
|---|---|---|
| `/login` | Costa (once) | Connect Spotify |
| `/callback` | Spotify (auto) | Save token to DB |
| `/auth-status` | Frontend | Check connection |
| `/queue` | Guests | Now playing + upcoming |
| `/queue/add` | Guests | Add a song |
| `/search?q=...` | Guests | Search Spotify |

---

## Next steps (v2)
- [ ] Rate limiting (1 free song per guest per hour)
- [ ] Stripe payments (push song up for 50ct)
- [ ] Admin panel for Costa
- [ ] QR code generator
