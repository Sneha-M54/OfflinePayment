# OfflinePay

An educational offline-first payment demo. Synthetic data only.
**This is not a real payment system and must not be used with real money.**

## Live URLs
- Frontend: https://YOUR-NETLIFY-URL.netlify.app
- Backend:  https://YOUR-RENDER-URL.onrender.com
- API docs: https://YOUR-RENDER-URL.onrender.com/docs

## Repository
https://github.com/Sneha-M54/OfflinePayment

## Demo credentials
| Role     | Username | Password    |
|----------|----------|-------------|
| Customer | alice    | alice123    |
| Customer | bob      | bob123      |
| Merchant | merchant | shop123     |
| Analyst  | analyst  | analyst123  |

## Run locally
Backend:
    cd backend
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1     # Windows
    pip install -r requirements.txt
    uvicorn app:app --reload --host 127.0.0.1 --port 8000

Frontend (separate terminal):
    python -m http.server 5500 --directory frontend
    # open http://127.0.0.1:5500

## Docker
    docker compose up --build
    # API on http://localhost:8000

## Reset demo data
    curl -X POST https://YOUR-RENDER-URL.onrender.com/api/demo/reset
(Only works when ALLOW_DEMO_RESET=1. Must be 0 on any public deployment.)

## Tests
    cd backend
    python -m pytest -q
    # 4 passed

## Security limitations
This is an assignment prototype. Passwords are seeded in plain text, API
identity uses an X-User header rather than real sessions, and device private
keys live in browser localStorage. The reset endpoint is demo-only. On
Render's free tier the SQLite database and bank signing key are lost on every
restart. Not suitable for real money, real personal data, or production use.
