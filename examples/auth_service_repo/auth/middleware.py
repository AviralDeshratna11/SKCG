from auth.base import BaseMiddleware
from auth.tokens import RefreshTokenValidator, extract_user_id
from auth.users import UserRepository


class AuthenticationMiddleware(BaseMiddleware):
    def __init__(self, signing_key):
        self.validator = RefreshTokenValidator(signing_key)
        self.users = UserRepository()

    def validate(self, token):
        if not self.validator.validate(token):
            return self.reject("invalid refresh token")
        user_id = extract_user_id(token)
        user = self.users.get_active_user(user_id)
        if not user:
            return self.reject("inactive user")
        return self.accept(user)
