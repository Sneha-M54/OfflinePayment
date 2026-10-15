
# OfflinePay

An educational offline-first payment demo using synthetic data only.

**This is not a real payment system and must not be used with real money.**

## Live URLs

- **Frontend:** https://sneham-offlinepayment-static-site-sneha.onrender.com
- **Backend:** https://offlinepayment.onrender.com
- **API Documentation:** https://offlinepayment.onrender.com/docs
- **Health Check:** https://offlinepayment.onrender.com/api/health

## Repository

https://github.com/Sneha-M54/OfflinePayment

## Demo Credentials

| Role | Username | Password |
|---|---|---|
| Customer | alice | alice123 |
| Customer | bob | bob123 |
| Merchant | merchant | shop123 |
| Analyst | analyst | analyst123 |

## Run Locally

### Backend

Open a terminal in the project folder and run:

```bash
cd backend
python -m venv .venv
```

Activate the virtual environment on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the backend:

```bash
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

Local backend URL:

http://127.0.0.1:8000

Local API documentation:

http://127.0.0.1:8000/docs

### Frontend

Open a separate terminal in the project root and run:

```bash
python -m http.server 5500 --directory frontend
```

Open the frontend:

http://127.0.0.1:5500

## Docker

If Docker and Docker Compose are installed, run this command from the project root:

```bash
docker compose up --build
```

For the deployed application, use:

- Frontend: https://sneham-offlinepayment-static-site-sneha.onrender.com
- Backend: https://offlinepayment.onrender.com

## Reset Demo Data

The reset endpoint is disabled by default on public deployments.

To enable it for a controlled local demo, set the environment variable:

```bash
ALLOW_DEMO_RESET=1
```

Then send a POST request to:

```text
http://127.0.0.1:8000/api/demo/reset
```

**Security warning:** Keep `ALLOW_DEMO_RESET=0` on any public deployment.

## Tests

Run the backend tests:

```bash
cd backend
python -m pytest -q
```

Expected result, if all tests pass:

```text
4 passed
```

## Security Limitations

This project is an educational assignment prototype, not a production payment system.

- Demo passwords are seeded in plain text.
- API identity uses an `X-User` header rather than secure authentication sessions.
- Device private keys are stored in browser `localStorage`.
- The reset endpoint is intended only for controlled demonstrations.
- On Render's free tier, local SQLite data and locally stored bank signing keys may be lost when the service restarts or its instance is replaced.
- The demo does not provide the security, compliance, or reliability required for real financial transactions.

**Never use real money, real payment credentials, or sensitive personal information with this application.**
