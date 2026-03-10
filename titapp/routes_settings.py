from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from .extensions import db
from .models import UserPreference, User
from .audit import log_audit
from .authz import role_required


settings_bp = Blueprint('settings', __name__)

ALLOWED_USER_ROLES = ['admin', 'registrar', 'hod', 'finance', 'viewer']


def get_or_create_user_preference(user_id):
    preference = UserPreference.query.filter_by(user_id=user_id).first()
    if preference:
        return preference

    preference = UserPreference(user_id=user_id)
    db.session.add(preference)
    db.session.flush()
    return preference


@settings_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings_page():
    preference = get_or_create_user_preference(current_user.id)
    is_admin_user = str(current_user.role or '').strip().lower() == 'admin'

    if request.method == 'POST':
        try:
            preference.theme = request.form.get('theme', 'system')
            if preference.theme not in ['system', 'light', 'dark']:
                preference.theme = 'system'

            per_page = int(request.form.get('students_per_page', 10) or 10)
            preference.students_per_page = per_page if per_page in [10, 25, 50, 100] else 10
            preference.compact_tables = request.form.get('compact_tables') == '1'

            db.session.flush()
            log_audit(
                'update_settings',
                'user_preference',
                entity_id=preference.id,
                metadata={
                    'theme': preference.theme,
                    'students_per_page': preference.students_per_page,
                    'compact_tables': preference.compact_tables,
                },
            )
            db.session.commit()
            flash('Settings saved successfully.', 'success')
            return redirect(url_for('settings.settings_page'))
        except Exception as error:
            db.session.rollback()
            flash(f'Failed to save settings: {str(error)}', 'danger')

    return render_template('settings.html', preference=preference, is_admin_user=is_admin_user)


@settings_bp.route('/settings/users/create', methods=['POST'])
@login_required
@role_required('admin')
def create_user_from_settings():
    full_name = (request.form.get('full_name') or '').strip()
    username = (request.form.get('username') or '').strip()
    email = (request.form.get('email') or '').strip().lower()
    role = (request.form.get('role') or '').strip().lower()
    temp_password = request.form.get('temporary_password') or ''

    if len(full_name) < 3:
        flash('Full name must be at least 3 characters.', 'warning')
        return redirect(url_for('settings.settings_page'))

    if len(username) < 3:
        flash('Username must be at least 3 characters.', 'warning')
        return redirect(url_for('settings.settings_page'))

    if '@' not in email or '.' not in email:
        flash('A valid email address is required.', 'warning')
        return redirect(url_for('settings.settings_page'))

    if role not in ALLOWED_USER_ROLES:
        flash('Please select a valid role.', 'warning')
        return redirect(url_for('settings.settings_page'))

    if len(temp_password) < 8:
        flash('Temporary password must be at least 8 characters.', 'warning')
        return redirect(url_for('settings.settings_page'))

    existing_username = User.query.filter(db.func.lower(User.username) == username.lower()).first()
    if existing_username:
        flash('Username already exists. Choose another one.', 'danger')
        return redirect(url_for('settings.settings_page'))

    existing_email = User.query.filter(db.func.lower(User.email) == email.lower()).first()
    if existing_email:
        flash('Email already exists. Use a different email.', 'danger')
        return redirect(url_for('settings.settings_page'))

    try:
        new_user = User(
            full_name=full_name,
            username=username,
            email=email,
            role=role,
        )
        new_user.set_password(temp_password)
        db.session.add(new_user)
        db.session.flush()

        log_audit(
            'create_user',
            'user',
            entity_id=new_user.id,
            metadata={
                'username': new_user.username,
                'email': new_user.email,
                'role': new_user.role,
                'created_by': current_user.id,
            },
        )
        db.session.commit()
        flash(f'User {new_user.username} created successfully.', 'success')
    except Exception as error:
        db.session.rollback()
        flash(f'Failed to create user: {str(error)}', 'danger')

    return redirect(url_for('settings.settings_page'))
