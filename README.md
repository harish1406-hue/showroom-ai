# ShowroomAI local MVP

## Requirements
- Python 3.11 or newer
- Chrome or Edge
- OpenAI API key

## Windows setup
```powershell
cd showroom-ai
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```
Open `.env` and replace `your_key_here`.

Run:
```powershell
uvicorn app:app --reload
```

Open:
- Customer screen: http://127.0.0.1:8000
- Admin dashboard: http://127.0.0.1:8000/admin

## Demo flow
1. Configure the company, products, and managers in `/admin`.
2. Open `/` in Chrome.
3. Click Start conversation and allow camera access.
4. Click Speak, or type for reliable testing.
5. Ask for a product, give a budget, browse by saying next/previous, and choose one.
6. When the AI completes the handoff, the lead appears in `/admin`.

## Notes
- The API key stays on the Python server and is never exposed to the browser.
- Browser speech recognition support varies. Typed input is included as a fallback.
- This first version stores data in `data/showroom.db`.
- Netlify cannot host this complete Python + SQLite server as-is. Keep it local for the demo, or later deploy the backend to Render/Railway/Fly.io and the frontend separately.
