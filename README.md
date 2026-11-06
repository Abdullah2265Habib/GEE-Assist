# GEE-Assist

Desktop app (PyQt6) for querying and analysing Google Earth Engine data.

## Running the app

1. Start the authentication server ([GEE-Assist-Backend](https://github.com/Abdullah2265Habib/GEE-Assist-Backend)),
   by default on `http://localhost:8000`:

   ```bash
   cd GEE-Assist-Backend
   .venv\Scripts\activate
   uvicorn app.main:app
   ```

2. Install and run the desktop app:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   copy .env.example .env      # set GEMINI_API_KEY; AUTH_API_URL if the server is not on localhost:8000
   python main.py
   ```

Run the tests with `python -m pytest`.

## Start-up and sign-in

- The intro video (`assets/starting_video/start.mp4`) plays centred on a white screen, then fades out.
  Click or press Esc / Space / Enter to skip it.
- The sign-in screen offers username/password sign-in, sign-up and Google sign-in.
- New accounts must verify their email. The app waits on a "Check your email" screen (resend,
  change email) and signs the user in as soon as the link is opened.
- **Keep me signed in** (ticked by default) stores the refresh token in the Windows Credential
  Manager (via `keyring`), so the next launch goes straight to the dashboard. The saved session
  lasts `SESSION_DURATION` from `.env` (e.g. `7d`, `12h`, `2m`), counted from signing in; after that
  the app asks to sign in again.
- After signing in the app opens on the **dashboard**. Its **Query Input** card opens the parameter
  form (with the "Chat with Gemini" assistant); **Dashboard** in the header returns to it.
- Administrators get a **Manage users** window (list users, change roles, enable / disable accounts).

### Where the code is

| Layer | Files |
|---|---|
| HTTP client for the auth server | `backend/data/clients/auth_api_client.py` |
| Saved session (credential store) | `backend/data/session_store.py` |
| Business logic (tokens, refresh, flows) | `backend/business/user/user_service.py` |
| Sign-up rules checked in the app | `backend/business/user/signup_validation.py` |
| UI entry point (`IBusinessFacade`) | `backend/business/facade/` |
| Intro video | `frontend/views/splash_view.py`, `frontend/views/startup_window.py` |
| Sign-in / sign-up screens | `frontend/views/auth/` |
| Theme (colours, fonts, styles) | `frontend/theme.py` |
| Admin user management | `frontend/views/user_admin_view.py` |
| Dashboard and signed-in window | `frontend/views/dashboard_view.py`, `frontend/views/home_window.py` |
| Query input (parameter form, Gemini assistant) | `frontend/views/main_window.py`, `frontend/views/parameter_form_view.py` |
