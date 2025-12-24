import tidalapi
from tidalapi.session import LinkLogin
import json

def handler(pd: "pipedream"):
    data_store = pd.inputs["data_store"]

    # 1. Check for existing tokens
    if "tidal_tokens" in data_store:
        tokens = json.loads(data_store["tidal_tokens"])
        session = tidalapi.Session()
        if session.load_oauth_session(
            tokens["token_type"],
            tokens["access_token"],
            tokens.get("refresh_token")
        ):
            pd.respond({
                "status": 200,
                "headers": {"Content-Type": "text/html"},
                "body": "<h1>Already authenticated!</h1><p>Daily sync is active.</p>"
            })
            return

    session = tidalapi.Session()

    # 2. Check for pending auth from previous visit
    if "pending_auth" in data_store:
        pending = json.loads(data_store["pending_auth"])
        # Reconstruct LinkLogin from saved data (tidalapi expects camelCase)
        link_login = LinkLogin({
            "deviceCode": pending["device_code"],
            "userCode": pending["user_code"],
            "verificationUri": pending["verification_uri"],
            "verificationUriComplete": pending["verification_uri_complete"],
            "expiresIn": 300,
            "interval": 2
        })

        try:
            # Single check (not polling)
            result = session._check_link_login(link_login, until_expiry=False)
            # If we get here, auth succeeded
            session.process_auth_token(result)
            if session.check_login():
                # Save tokens, clear pending
                tokens = {
                    "token_type": session.token_type,
                    "access_token": session.access_token,
                    "refresh_token": session.refresh_token
                }
                data_store["tidal_tokens"] = json.dumps(tokens)
                del data_store["pending_auth"]
                pd.respond({
                    "status": 200,
                    "headers": {"Content-Type": "text/html"},
                    "body": "<h1>Success!</h1><p>Tidal connected. Daily sync is now active.</p>"
                })
                return
        except Exception:
            # Auth not completed yet or expired, will generate new link below
            del data_store["pending_auth"]

    # 3. Start new OAuth flow
    login_info, future = session.login_oauth()
    future.cancel()  # Don't poll - we'll check on refresh

    # Save pending auth
    pending = {
        "device_code": login_info.device_code,
        "user_code": login_info.user_code,
        "verification_uri": login_info.verification_uri,
        "verification_uri_complete": login_info.verification_uri_complete
    }
    data_store["pending_auth"] = json.dumps(pending)

    link = login_info.verification_uri_complete
    pd.respond({
        "status": 200,
        "headers": {"Content-Type": "text/html"},
        "body": f"""<h1>Connect Tidal</h1>
<p>1. <a href='https://{link}' target='_blank'>Click here to login to Tidal</a></p>
<p>2. Complete login on Tidal</p>
<p>3. <a href=''>Click here when done</a></p>"""
    })
