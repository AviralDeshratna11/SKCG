class RefreshTokenValidator:
    def __init__(self, signing_key):
        self.signing_key = signing_key

    def validate(self, token):
        if not token.startswith("refresh:"):
            return False
        return self._verify_signature(token)

    def _verify_signature(self, token):
        return self.signing_key in token


def extract_user_id(token):
    return token.split(":")[1]
