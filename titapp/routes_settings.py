from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from .extensions import db
from .models import UserPreference
from .audit import log_audit


settings_bp = Blueprint('settings', __name__)


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

    return render_template('settings.html', preference=preference)
