class UserRepository:
    def __init__(self):
        self.users = {"42": {"id": "42", "active": True}}

    def get_active_user(self, user_id):
        user = self.users.get(user_id)
        if not user:
            return None
        if not user["active"]:
            return None
        return user
