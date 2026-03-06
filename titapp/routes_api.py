from datetime import datetime
from flask import Blueprint, jsonify
from flask_login import login_required
from .extensions import db
from .models import Student


api_bp = Blueprint('api', __name__)


@api_bp.route('/api/stats')
@login_required
def api_stats():
    base_query = Student.query.filter(Student.deleted_at.is_(None))
    total = base_query.count()
    active = base_query.filter_by(status='Active').count()
    male = base_query.filter_by(gender='Male').count()
    female = base_query.filter_by(gender='Female').count()

    depts = db.session.query(Student.department, db.func.count(Student.id)).filter(Student.deleted_at.is_(None)).group_by(Student.department).all()
    progs = db.session.query(Student.programme, db.func.count(Student.id)).filter(Student.deleted_at.is_(None)).group_by(Student.programme).all()

    return jsonify({
        'total': total,
        'active': active,
        'male': male,
        'female': female,
        'departments': {d[0] or 'Unassigned': d[1] for d in depts},
        'programmes': {p[0] or 'Unassigned': p[1] for p in progs},
    })


@api_bp.route('/healthz')
def healthz():
    return jsonify({
        'status': 'ok',
        'service': 'tit-dbms',
        'time': datetime.utcnow().isoformat() + 'Z'
    })
