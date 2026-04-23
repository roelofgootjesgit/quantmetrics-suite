# cTrader Open API Auth Setup

This guide gets `openapi` smoke tests working with real demo credentials.

## Important Difference

- cTrader login password is **not** the same as Open API access token.
- QuantBridge Open API mode needs:
  - `CTRADER_ACCOUNT_ID` (numeric ctid account id)
  - `CTRADER_ACCESS_TOKEN` (OAuth access token)
  - optional `CTRADER_CLIENT_ID` and `CTRADER_CLIENT_SECRET` (recommended)

## Step 1 - Register/Open API App

1. Open cTrader Open API app page (Spotware Connect).
2. Create an app and note:
   - `client_id`
   - `client_secret`
   - redirect URI

## Step 2 - Get OAuth Access Token

1. Open auth URL for your app.
2. Login and approve account access.
3. Capture `code` from redirect URL.
4. Exchange `code` for `accessToken` (and `refreshToken`).

Reference docs:
- https://spotware.github.io/OpenApiPy/authentication/
- https://help.ctrader.com/open-api/python-SDK/python-sdk-index/

## Step 3 - Fill `.env`

Use this local file in project root:

```env
CTRADER_MODE=openapi
CTRADER_ACCOUNT_ID=your_numeric_ctid_account
CTRADER_ACCESS_TOKEN=your_oauth_access_token
CTRADER_CLIENT_ID=your_app_client_id
CTRADER_CLIENT_SECRET=your_app_client_secret
```

## Step 4 - Run Smoke Test

```bash
python scripts/ctrader_smoke.py --config configs/ctrader_icmarkets_demo.yaml --mode openapi
```

Success means:
- connect
- health
- price
- place order
- sync positions
- close order

## If It Fails

- `auth_failed`: token/account mismatch, expired token, or wrong token type
- `timeout` during bootstrap: often missing app creds or invalid token scope
- `invalid_symbol`: broker symbol mapping mismatch
