class BaseMiddleware:
    def reject(self, reason):
        return {"ok": False, "reason": reason}

    def accept(self, user):
        return {"ok": True, "user": user}
