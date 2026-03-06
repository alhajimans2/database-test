from collections import Counter
from datetime import datetime
from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user, login_required
from .extensions import db
from .models import Student


main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))


@main_bp.route('/dashboard')
@login_required
def dashboard():
    base_query = Student.query.filter(Student.deleted_at.is_(None))

    total_students = base_query.count()
    active_students = base_query.filter_by(status='Active').count()
    male_students = base_query.filter_by(gender='Male').count()
    female_students = base_query.filter_by(gender='Female').count()
    recent_students = base_query.order_by(Student.created_at.desc()).limit(8).all()

    programmes = db.session.query(Student.programme, db.func.count(Student.id)).filter(Student.deleted_at.is_(None)).group_by(Student.programme).all()
    departments = db.session.query(Student.department, db.func.count(Student.id)).filter(Student.deleted_at.is_(None)).group_by(Student.department).all()

    now = datetime.utcnow()
    month_keys = []
    month_labels = []
    for index in range(5, -1, -1):
        month = (now.month - index - 1) % 12 + 1
        year = now.year + ((now.month - index - 1) // 12)
        month_keys.append(f"{year:04d}-{month:02d}")
        month_labels.append(datetime(year=year, month=month, day=1).strftime('%b %Y'))

    students_for_trend = Student.query.with_entities(Student.created_at).filter(Student.created_at.isnot(None), Student.deleted_at.is_(None)).all()
    monthly_counter = Counter(item.created_at.strftime('%Y-%m') for item in students_for_trend if item.created_at)
    monthly_admissions = [monthly_counter.get(key, 0) for key in month_keys]

    all_students = base_query.all()
    average_completeness = int(round(sum(student.completeness_score for student in all_students) / len(all_students))) if all_students else 0

    return render_template(
        'dashboard.html',
        total_students=total_students,
        active_students=active_students,
        male_students=male_students,
        female_students=female_students,
        recent_students=recent_students,
        programmes=programmes,
        departments=departments,
        monthly_labels=month_labels,
        monthly_admissions=monthly_admissions,
        average_completeness=average_completeness,
    )
