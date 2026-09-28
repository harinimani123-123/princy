# LegalEase - AI-Powered Legal Document Generator

LegalEase is an AI-assisted legal document drafting tool. You choose a document type, enter the
parties, terms and effective date, and the app asks **Google Gemini** to draft a professional
document. You can edit the draft in the browser and download it as **TXT**, **DOCX** or **PDF**.

> **Legal disclaimer:** LegalEase produces *AI-assisted drafts only*. They are not legal advice and
> are not guaranteed to be valid, complete or enforceable in any jurisdiction. Always have a
> qualified legal professional review a document before real-world use.

---

## 1. Features

- Document types: Employment Contract, Lease Agreement, NDA, Employment Offer Letter, Freelance
  Work Contract, Service Agreement, and **Custom Agreement** (you type the name).
- Inputs: parties, terms and conditions (semicolon- or line-separated), effective date.
- FastAPI backend with input validation (empty, whitespace-only and over-long input is rejected).
- Gemini prompt that forbids inventing names, addresses, amounts, laws, courts or registration
  numbers. Missing details appear as `[MISSING INFORMATION]` and are listed at the end.
- Every document ends with the standard **REVIEW NOTICE**.
- Editable preview (edits are kept in Streamlit session state; editing never re-generates).
- Downloads: TXT (UTF-8), DOCX (python-docx: logo, headings, key-terms table, footer with page
  numbers) and PDF (ReportLab: A4, logo, headings, key-terms table, footer with page numbers).
- Clear error messages: missing API key, Gemini errors, backend offline, timeouts, bad responses.
- Automated tests (pytest) that never call the real Gemini API.

## 2. Architecture

```
User -> Streamlit frontend (frontend/app.py)
            | HTTP POST /generate (requests)
            v
        FastAPI backend (backend/main.py, routes.py, models.py)
            | Pydantic validation
            v
        GeminiDocumentGenerator (backend/ai_core/gemini_generator.py)
            | google-genai SDK
            v
        Google Gemini API  -->  generated text
            |
            v
        Streamlit session state (editable preview)
            |
            v
        document_formatter.py -> TXT / DOCX / PDF downloads
```

The API key lives only in the backend's `.env` file. The frontend never sees it. The frontend
imports the formatter functions from `backend/utils` directly to build downloads locally, so
generated documents are not stored anywhere on the server.

## 3. Folder structure

```
LegalEase/
├── backend/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app, CORS, GET / and GET /health
│   ├── models.py                # DocumentRequest / DocumentResponse (Pydantic)
│   ├── routes.py                # POST /generate + error handling
│   ├── ai_core/
│   │   ├── __init__.py
│   │   └── gemini_generator.py  # GeminiDocumentGenerator, prompt, Gemini errors
│   └── utils/
│       ├── __init__.py
│       ├── text_utils.py        # whitespace, quotes, dashes, term splitting, ...
│       └── document_formatter.py# format_txt / format_docx / format_pdf
├── frontend/
│   ├── __init__.py
│   └── app.py                   # Streamlit UI
├── assets/
│   └── logo.png                 # used in the DOCX/PDF exports (optional)
├── tests/
│   ├── __init__.py
│   ├── test_api.py
│   └── test_utils.py
├── .env                         # your local settings (never commit)
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
└── run_backend.bat
```

## 4. Prerequisites

- Windows 10/11
- **Python 3.11 or newer** (3.12 is fine)
- **Visual Studio Code** with the *Python* extension
- A **Gemini API key** (free to create in Google AI Studio)
- Internet access (for installing packages and calling Gemini)

## 5. Install Python

1. Download Python from <https://www.python.org/downloads/windows/>.
2. In the installer, tick **"Add python.exe to PATH"**, then click *Install Now*.
3. Open a new terminal and check:

```powershell
python --version
```

It should print `Python 3.11.x` or higher. (If `python` is not found, try `py --version`, and use
`py` instead of `python` in the commands below.)

## 6. Open the project in VS Code

1. Extract `LegalEase.zip` (right-click -> *Extract All...*).
2. In VS Code choose **File -> Open Folder...** and select the extracted `LegalEase` folder
   (the folder that contains `backend`, `frontend` and `requirements.txt`).
3. Open a terminal: **Terminal -> New Terminal** (PowerShell). All commands below are run from
   the project root.

## 7. Create the virtual environment and install dependencies

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell blocks the activation script ("running scripts is disabled"), run this once and
try again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

When the environment is active, your prompt starts with `(.venv)`. In VS Code press
`Ctrl+Shift+P` -> **Python: Select Interpreter** -> choose the one inside `.venv`.

## 8. Gemini API key setup

1. Go to <https://aistudio.google.com/apikey> and create an API key.
2. Open the `.env` file in the project root and paste the key after the equals sign:

```env
GEMINI_API_KEY=paste_your_key_here
GEMINI_MODEL=gemini-2.5-flash
BACKEND_URL=http://127.0.0.1:8000
```

| Variable | Meaning |
|---|---|
| `GEMINI_API_KEY` | Your Gemini API key. Used **only** by the backend. No quotes or spaces. |
| `GEMINI_MODEL` | Gemini model name. Default `gemini-2.5-flash`. If Google retires a model, pick a current one from Google's model list and change it here. |
| `BACKEND_URL` | Where the Streamlit frontend finds the FastAPI backend. |

`.env` is listed in `.gitignore`, so it is never committed. Restart the backend after changing
`.env`. `.env.example` is a template you can copy if `.env` is ever lost.

## 9. Start the backend (Terminal 1)

```powershell
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Or double-click `run_backend.bat` (it activates `.venv`, checks the environment and starts
Uvicorn, showing a helpful message if something is missing).

You should see `Uvicorn running on http://127.0.0.1:8000`. Leave this terminal open.

## 10. Start the frontend (Terminal 2)

Open a **second** terminal (**Terminal -> New Terminal**) and run:

```powershell
.venv\Scripts\Activate.ps1
streamlit run frontend/app.py
```

The app opens at <http://localhost:8501>. (If Streamlit asks for an email on first launch, just
press Enter.)

## 11. Test the API

With the backend running, open these URLs in a browser:

| URL | What you should see |
|---|---|
| <http://127.0.0.1:8000/> | `{"application":"LegalEase","status":"running","api_docs":"/docs"}` |
| <http://127.0.0.1:8000/health> | `{"status":"healthy"}` |
| <http://127.0.0.1:8000/docs> | Swagger UI (try `POST /generate` with **Try it out**) |
| <http://127.0.0.1:8000/redoc> | ReDoc documentation |

Or test `POST /generate` from PowerShell:

```powershell
$body = @{
  document_type = "Freelance Work Contract"
  parties       = "Jane Doe (Service Provider), TechNova Inc. (Client)"
  terms         = "Work delivered by May 15, 2025; Payment within 7 days of invoice"
  dates         = "April 15, 2025"
} | ConvertTo-Json

Invoke-RestMethod -Uri http://127.0.0.1:8000/generate -Method Post -Body $body -ContentType "application/json"
```

A request with an empty field returns **HTTP 422** with an explanation. A missing API key returns
**HTTP 503**.

## 12. Test the application (manual walk-through)

1. Open <http://localhost:8501>.
2. Click **Load example** (or fill in the form yourself).
3. Click **Generate Document** and wait while the spinner runs.
4. Check the preview, edit some text, and confirm the text area keeps your edits.
5. Click **Download TXT**, **Download DOCX** and **Download PDF** and open each file.
6. Choose **Custom Agreement** and confirm a custom-type field appears.
7. Leave a field blank and click Generate to see the validation message.
8. Stop the backend and click Generate to see the "cannot connect" message.

## 13. Automated tests

```powershell
pytest
```

The tests mock the AI layer, so no API key or internet connection is needed. They cover the
API endpoints and validation, error mapping, the Gemini generator (with a fake client), text
utilities, and TXT/DOCX/PDF generation.

## 14. Troubleshooting

| Problem | Fix |
|---|---|
| `uvicorn is not recognized` | The virtual environment is not active or dependencies are not installed. Run `.venv\Scripts\Activate.ps1`, then `pip install -r requirements.txt`. You can also use `python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000`. |
| `ModuleNotFoundError: No module named 'backend'` | Run commands from the **project root** (the folder containing `backend`). Do not `cd` into `backend` or `frontend`. |
| `ModuleNotFoundError` for `fastapi`, `docx`, `google`, ... | Activate `.venv` and run `pip install -r requirements.txt`. Make sure VS Code uses the `.venv` interpreter. |
| "GEMINI_API_KEY is missing" (HTTP 503) | Put your key in `.env` (no quotes), save the file, and restart the backend. |
| Gemini rejected the request (HTTP 400/403) | The API key is invalid or not enabled. Create a new key in Google AI Studio. |
| Gemini model not found (HTTP 404) | `GEMINI_MODEL` is wrong or retired. Set a current model name in `.env` and restart. |
| Rate limit / quota exceeded (HTTP 429) | Wait a minute and retry, or check your quota in Google AI Studio. |
| Port already in use (`[Errno 10048]`) | Another program uses port 8000. Close it, or start with `--port 8001` and set `BACKEND_URL=http://127.0.0.1:8001` in `.env`. Streamlit's port can be changed with `--server.port 8502`. |
| Frontend says it cannot connect to the backend | Start the backend first and check <http://127.0.0.1:8000/health>. Make sure `BACKEND_URL` in `.env` matches the backend address, then restart Streamlit. |
| Request times out | Gemini can be slow for long documents. Try again, or shorten the terms. |
| PDF generation fails | Make sure `reportlab` and `Pillow` are installed (`pip install -r requirements.txt`). If special characters look wrong, the PDF uses Arial (Windows) when available; scripts such as Tamil or Arabic are not supported by the built-in fonts. The error message on the page shows the exact cause. |
| Logo missing in exports | `assets/logo.png` is optional; exports still work without it. |
| `pytest` not found | Activate `.venv` and run `pip install -r requirements.txt`. |

## 15. Security considerations

- The Gemini API key is read from `.env` by the backend only. It is never hard-coded, printed,
  logged or sent to the browser. Error messages never contain it.
- `.env` is in `.gitignore`. Never commit or share it. If a key leaks, revoke it in Google AI
  Studio and create a new one.
- All input is validated (types, blank input, maximum lengths, control characters).
- Unexpected server errors return a generic message; details stay out of API responses.
- CORS allows only `http://localhost:8501` and `http://127.0.0.1:8501`.
- Generated documents are not stored on the server. They exist in your browser session until you
  close or clear them.
- The text you enter is sent to Google's Gemini API. Do not enter information you are not
  permitted to share with a third-party AI service.
- The backend is intended for local use. Before exposing it to a network, add authentication and
  rate limiting, and serve it over HTTPS.

## 16. Legal disclaimer

LegalEase is a drafting aid. It is not a law firm, does not provide legal advice, and does not
create a lawyer-client relationship. AI output may contain errors, omissions or clauses that are
unsuitable for your situation or jurisdiction. Every document must be reviewed by a qualified
legal professional before it is signed or relied upon. The authors accept no liability for any
use of generated documents.
