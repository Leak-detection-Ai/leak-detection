# Mastodon OAuth setup

LeakGuard uses Mastodon's official OAuth authorization-code flow with PKCE (S256).

## 1. Create the application

On your Mastodon instance, create an application with:

- Redirect URI: `http://localhost:8000/api/oauth/mastodon/callback`
- Scopes: `read:accounts read:statuses`
- Website: `http://localhost:5173`

Copy the client ID and client secret into `.env`.

## 2. Start the backend and frontend

The browser visits:

`http://localhost:5173/accounts`

Choose **Connect Mastodon**. The backend creates a random OAuth state and PKCE verifier, stores both in short-lived HttpOnly cookies, and redirects to the configured Mastodon instance.

After consent, Mastodon returns to the callback. LeakGuard verifies state, exchanges the code with the PKCE verifier, verifies the account, encrypts the tokens and stores only the encrypted values.

## 3. Automatic monitoring

Once connected, the backend scheduler checks connected Mastodon accounts every 60 seconds. New statuses are normalized into `social_content`, analyzed once, and high/critical findings create incidents and alerts.

The frontend does not perform background synchronization, so closing the browser does not stop monitoring while the backend is running.

## Reconnection

If a refresh token is unavailable or refresh fails, the account is marked disconnected and the UI asks the user to reconnect. No provider credential is shown in API responses.
