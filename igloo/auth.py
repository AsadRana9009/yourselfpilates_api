import os
import base64
import requests
from datetime import datetime, timedelta

IGLOO_AUTH_URL = "https://auth.igloohome.co/oauth2/token"


# Module-level singleton for IglooAuth
class IglooAuth:
    _instance = None

    def __new__(cls, client_id=None, client_secret=None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
        
    def __init__(self, client_id=None, client_secret=None):
        if getattr(self, '_initialized', False):
            return
        self.client_id = client_id or os.getenv("IGLOO_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("IGLOO_CLIENT_SECRET")
        self.token = None
        self.token_expiry = None
        self._initialized = True

    def _encode_credentials(self):
        creds = f"{self.client_id}:{self.client_secret}"
        return base64.b64encode(creds.encode()).decode()

    def get_token(self, scope=None):
        # All bridge management scopes for full rights
        all_scopes = (
            "igloohomeapi/lock-bridge-proxied-job "
            "igloohomeapi/unlock-bridge-proxied-job "
            "igloohomeapi/create-pin-bridge-proxied-job "
            "igloohomeapi/delete-pin-bridge-proxied-job "
            "igloohomeapi/get-device-status-bridge-proxied-job "
            "igloohomeapi/get-battery-level-bridge-proxied-job "
            "igloohomeapi/get-activity-logs-bridge-proxied-job"
        )
        use_scope = scope or all_scopes
        if self.token and self.token_expiry and datetime.utcnow() < self.token_expiry:
            return self.token
        headers = {
            "Authorization": f"Basic {self._encode_credentials()}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "grant_type": "client_credentials",
            "scope": use_scope,
        }
        response = requests.post(IGLOO_AUTH_URL, headers=headers, data=data)
        if response.status_code == 200:
            resp_json = response.json()
            self.token = resp_json["access_token"]
            self.token_expiry = datetime.utcnow() + timedelta(seconds=resp_json["expires_in"]) - timedelta(minutes=5)
            return self.token
        else:
            raise Exception(f"Failed to get Igloo token: {response.status_code} {response.text}")
