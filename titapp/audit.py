import json
from flask_login import current_user
from .extensions import db
from .models import AuditLog


def log_audit(action, entity, entity_id=None, metadata=None):
    user_id = None
    try:
        if current_user and current_user.is_authenticated:
            user_id = current_user.id
    except Exception:
        user_id = None

    entry = AuditLog(
        user_id=user_id,
        action=action,
        entity=entity,
        entity_id=str(entity_id) if entity_id is not None else None,
        metadata_json=json.dumps(metadata or {})
    )
    db.session.add(entry)
