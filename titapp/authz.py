from functools import wraps
from flask import abort
from flask_login import current_user


def role_required(*roles):
    allowed = {role.lower() for role in roles}

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            role = (current_user.role or '').lower()
            if role not in allowed:
                abort(403)
            return func(*args, **kwargs)
        return wrapper
    return decorator
