def validate_user(user):
    return user is not None


class PaymentService:
    def charge(self, user, amount):
        validate_user(user)
        return amount
