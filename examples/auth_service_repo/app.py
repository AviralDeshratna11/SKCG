from auth.middleware import AuthenticationMiddleware


def handle_request(token):
    middleware = AuthenticationMiddleware("secret")
    return middleware.validate(token)
