"""State token manager for OIDC CSRF protection."""


class StateManager:
    def __init__(self):
        self._states = {}

    def create_state(self, data):
        import secrets
        from datetime import datetime, timezone, timedelta

        # Generate random state token
        state_token = secrets.token_urlsafe(32)

        # Store state data with expiration (5 minutes)
        self._states[state_token] = {
            "data": data,
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
        }

        return state_token

    def validate_state(self, state_token):
        from datetime import datetime, timezone

        # Check if state token exists
        if state_token not in self._states:
            return None

        state_entry = self._states[state_token]

        # Check if expired
        if datetime.now(timezone.utc) > state_entry["expires_at"]:
            # Clean up expired token
            del self._states[state_token]
            return None

        # Return data and delete token (one-time use)
        data = state_entry["data"]
        del self._states[state_token]

        return data
