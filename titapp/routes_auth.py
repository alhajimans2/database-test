from datetime import datetime, timedelta
import secrets

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash

from .extensions import db
from .models import User, TwoFactorToken
from .audit import log_audit
from .email_utils import send_email_message


auth_bp = Blueprint('auth', __name__)


def _generate_otp_code() -> str:
    return f"{secrets.randbelow(1000000):06d}"


def _is_admin_user(user: User | None) -> bool:
    if not user:
        return False
    return str(user.role or '').strip().lower() == 'admin'


def _admin_otp_enabled() -> bool:
    return bool(current_app.config.get('ADMIN_OTP_ENABLED', False))


def _otp_cooldown_remaining(session_key: str) -> int:
    cooldown = int(current_app.config.get('OTP_RESEND_COOLDOWN_SECONDS', 60))
    last_sent = int(session.get(session_key, 0) or 0)
    now_ts = int(datetime.utcnow().timestamp())
    return max(0, cooldown - (now_ts - last_sent))


def _mark_otp_sent(session_key: str):
    session[session_key] = int(datetime.utcnow().timestamp())


def _create_otp_token(user_id: int, purpose: str, payload_hash: str | None = None) -> tuple[TwoFactorToken, str]:
    now = datetime.utcnow()
    ttl = int(current_app.config.get('OTP_TTL_SECONDS', 300))
    code = _generate_otp_code()

    TwoFactorToken.query.filter(
        TwoFactorToken.user_id == user_id,
        TwoFactorToken.purpose == purpose,
        TwoFactorToken.consumed_at.is_(None),
        TwoFactorToken.expires_at > now,
    ).update({'consumed_at': now})

    token = TwoFactorToken(
        user_id=user_id,
        purpose=purpose,
        code_hash=generate_password_hash(code),
        payload_hash=payload_hash,
        expires_at=now + timedelta(seconds=ttl),
        created_at=now,
    )
    db.session.add(token)
    db.session.flush()
    return token, code


def _send_admin_otp(user: User, code: str, purpose_label: str) -> tuple[bool, str]:
    subject = f"TIT Security Code – {purpose_label}"
    body = (
        f"Hello {user.full_name},\n\n"
        f"Your verification code for {purpose_label} is: {code}\n"
        f"This code expires in {int(current_app.config.get('OTP_TTL_SECONDS', 300)) // 60} minutes.\n\n"
        "If you did not request this, please contact system support immediately.\n"
    )
    sent, message = send_email_message(user.email, subject, body)
    return sent, message


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            if _is_admin_user(user) and _admin_otp_enabled():
                token, code = _create_otp_token(user.id, 'admin_login')
                sent, send_message = _send_admin_otp(user, code, 'admin login')
                if not sent:
                    app_env = (current_app.config.get('APP_ENV') or 'development').lower()
                    if app_env == 'production':
                        db.session.rollback()
                        flash('Unable to send verification code email. Check mail configuration and retry.', 'danger')
                        return render_template('login.html')

                    flash(f'Email delivery unavailable ({send_message}). Use this dev OTP: {code}', 'warning')

                db.session.commit()
                session['pending_admin_login_user_id'] = user.id
                session['pending_admin_login_token_id'] = token.id
                _mark_otp_sent('pending_admin_login_otp_sent_at')
                flash('A verification code has been sent to your admin email.', 'info')
                return redirect(url_for('auth.verify_admin_login_otp'))

            login_user(user)
            try:
                log_audit('login_success', 'auth', entity_id=user.id, metadata={'username': user.username})
                db.session.commit()
            except Exception:
                db.session.rollback()
            flash('Welcome back!', 'success')
            return redirect(url_for('main.dashboard'))
        try:
            log_audit('login_failed', 'auth', metadata={'username': username})
            db.session.commit()
        except Exception:
            db.session.rollback()
        flash('Invalid username or password.', 'danger')

    return render_template('login.html')


@auth_bp.route('/login/verify-otp', methods=['GET', 'POST'])
def verify_admin_login_otp():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    pending_user_id = session.get('pending_admin_login_user_id')
    pending_token_id = session.get('pending_admin_login_token_id')
    if not pending_user_id or not pending_token_id:
        flash('Login session expired. Please sign in again.', 'warning')
        return redirect(url_for('auth.login'))

    user = User.query.get(pending_user_id)
    token = TwoFactorToken.query.get(pending_token_id)
    if not user or not token or token.user_id != user.id or token.purpose != 'admin_login':
        session.pop('pending_admin_login_user_id', None)
        session.pop('pending_admin_login_token_id', None)
        flash('Invalid verification session. Please sign in again.', 'danger')
        return redirect(url_for('auth.login'))

    now = datetime.utcnow()
    if token.consumed_at or token.expires_at <= now:
        session.pop('pending_admin_login_user_id', None)
        session.pop('pending_admin_login_token_id', None)
        flash('Verification code expired. Please sign in again.', 'warning')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        otp = (request.form.get('otp_code') or '').strip()
        if not otp:
            flash('Verification code is required.', 'warning')
            return render_template(
                'verify_otp.html',
                flow='login',
                resend_endpoint='auth.resend_admin_login_otp',
                cooldown_remaining=_otp_cooldown_remaining('pending_admin_login_otp_sent_at'),
            )

        if not check_password_hash(token.code_hash, otp):
            token.attempts = int(token.attempts or 0) + 1
            if token.attempts >= 5:
                token.consumed_at = now
                db.session.commit()
                session.pop('pending_admin_login_user_id', None)
                session.pop('pending_admin_login_token_id', None)
                flash('Too many invalid attempts. Please sign in again.', 'danger')
                return redirect(url_for('auth.login'))

            db.session.commit()
            flash('Invalid verification code.', 'danger')
            return render_template(
                'verify_otp.html',
                flow='login',
                resend_endpoint='auth.resend_admin_login_otp',
                cooldown_remaining=_otp_cooldown_remaining('pending_admin_login_otp_sent_at'),
            )

        token.consumed_at = now
        db.session.commit()
        session.pop('pending_admin_login_user_id', None)
        session.pop('pending_admin_login_token_id', None)

        login_user(user)
        try:
            log_audit('login_success_2fa', 'auth', entity_id=user.id, metadata={'username': user.username})
            db.session.commit()
        except Exception:
            db.session.rollback()

        flash('Welcome back! 2FA verification successful.', 'success')
        return redirect(url_for('main.dashboard'))

    return render_template(
        'verify_otp.html',
        flow='login',
        resend_endpoint='auth.resend_admin_login_otp',
        cooldown_remaining=_otp_cooldown_remaining('pending_admin_login_otp_sent_at'),
    )


@auth_bp.route('/login/resend-otp', methods=['POST'])
def resend_admin_login_otp():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    pending_user_id = session.get('pending_admin_login_user_id')
    if not pending_user_id:
        flash('Login session expired. Please sign in again.', 'warning')
        return redirect(url_for('auth.login'))

    remaining = _otp_cooldown_remaining('pending_admin_login_otp_sent_at')
    if remaining > 0:
        flash(f'Please wait {remaining}s before requesting another code.', 'warning')
        return redirect(url_for('auth.verify_admin_login_otp'))

    user = User.query.get(pending_user_id)
    if not user or not _is_admin_user(user):
        flash('Invalid verification session. Please sign in again.', 'danger')
        return redirect(url_for('auth.login'))

    token, code = _create_otp_token(user.id, 'admin_login')
    sent, send_message = _send_admin_otp(user, code, 'admin login')
    if not sent:
        app_env = (current_app.config.get('APP_ENV') or 'development').lower()
        if app_env == 'production':
            db.session.rollback()
            flash('Unable to resend verification code email. Check mail configuration.', 'danger')
            return redirect(url_for('auth.verify_admin_login_otp'))
        flash(f'Email delivery unavailable ({send_message}). Use this dev OTP: {code}', 'warning')

    db.session.commit()
    session['pending_admin_login_token_id'] = token.id
    _mark_otp_sent('pending_admin_login_otp_sent_at')
    flash('A new verification code was sent.', 'info')
    return redirect(url_for('auth.verify_admin_login_otp'))


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not current_user.check_password(current_password):
            flash('Current password is incorrect.', 'danger')
            return render_template('change_password.html')

        if len(new_password) < 8:
            flash('New password must be at least 8 characters.', 'warning')
            return render_template('change_password.html')

        if new_password != confirm_password:
            flash('New password and confirmation do not match.', 'warning')
            return render_template('change_password.html')

        if _is_admin_user(current_user) and _admin_otp_enabled():
            payload_hash = generate_password_hash(new_password)
            token, code = _create_otp_token(current_user.id, 'admin_password_change', payload_hash=payload_hash)
            sent, send_message = _send_admin_otp(current_user, code, 'admin password change')
            if not sent:
                app_env = (current_app.config.get('APP_ENV') or 'development').lower()
                if app_env == 'production':
                    db.session.rollback()
                    flash('Unable to send verification code email. Check mail configuration and retry.', 'danger')
                    return render_template('change_password.html')

                flash(f'Email delivery unavailable ({send_message}). Use this dev OTP: {code}', 'warning')

            db.session.commit()
            session['pending_password_change_token_id'] = token.id
            _mark_otp_sent('pending_password_change_otp_sent_at')
            flash('A verification code was sent to your admin email to confirm password change.', 'info')
            return redirect(url_for('auth.verify_password_change_otp'))

        current_user.set_password(new_password)
        db.session.commit()
        flash('Password updated successfully.', 'success')
        return redirect(url_for('settings.settings_page'))

    return render_template('change_password.html')


@auth_bp.route('/change-password/verify-otp', methods=['GET', 'POST'])
@login_required
def verify_password_change_otp():
    token_id = session.get('pending_password_change_token_id')
    if not token_id:
        flash('No password change verification session found.', 'warning')
        return redirect(url_for('auth.change_password'))

    token = TwoFactorToken.query.get(token_id)
    now = datetime.utcnow()

    if not token or token.user_id != current_user.id or token.purpose != 'admin_password_change':
        session.pop('pending_password_change_token_id', None)
        flash('Invalid verification session.', 'danger')
        return redirect(url_for('auth.change_password'))

    if token.consumed_at or token.expires_at <= now:
        session.pop('pending_password_change_token_id', None)
        flash('Verification code expired. Restart password change.', 'warning')
        return redirect(url_for('auth.change_password'))

    if request.method == 'POST':
        otp = (request.form.get('otp_code') or '').strip()
        if not otp:
            flash('Verification code is required.', 'warning')
            return render_template(
                'verify_otp.html',
                flow='password',
                resend_endpoint='auth.resend_password_change_otp',
                cooldown_remaining=_otp_cooldown_remaining('pending_password_change_otp_sent_at'),
            )

        if not check_password_hash(token.code_hash, otp):
            token.attempts = int(token.attempts or 0) + 1
            if token.attempts >= 5:
                token.consumed_at = now
                db.session.commit()
                session.pop('pending_password_change_token_id', None)
                flash('Too many invalid attempts. Restart password change.', 'danger')
                return redirect(url_for('auth.change_password'))

            db.session.commit()
            flash('Invalid verification code.', 'danger')
            return render_template(
                'verify_otp.html',
                flow='password',
                resend_endpoint='auth.resend_password_change_otp',
                cooldown_remaining=_otp_cooldown_remaining('pending_password_change_otp_sent_at'),
            )

        if not token.payload_hash:
            token.consumed_at = now
            db.session.commit()
            session.pop('pending_password_change_token_id', None)
            flash('Password update payload missing. Restart password change.', 'danger')
            return redirect(url_for('auth.change_password'))

        current_user.password_hash = token.payload_hash
        token.consumed_at = now
        db.session.commit()
        session.pop('pending_password_change_token_id', None)

        try:
            log_audit('password_change_2fa', 'auth', entity_id=current_user.id, metadata={'username': current_user.username})
            db.session.commit()
        except Exception:
            db.session.rollback()

        flash('Password changed successfully with 2FA verification.', 'success')
        return redirect(url_for('settings.settings_page'))

    return render_template(
        'verify_otp.html',
        flow='password',
        resend_endpoint='auth.resend_password_change_otp',
        cooldown_remaining=_otp_cooldown_remaining('pending_password_change_otp_sent_at'),
    )


@auth_bp.route('/change-password/resend-otp', methods=['POST'])
@login_required
def resend_password_change_otp():
    token_id = session.get('pending_password_change_token_id')
    if not token_id:
        flash('No active password verification session.', 'warning')
        return redirect(url_for('auth.change_password'))

    remaining = _otp_cooldown_remaining('pending_password_change_otp_sent_at')
    if remaining > 0:
        flash(f'Please wait {remaining}s before requesting another code.', 'warning')
        return redirect(url_for('auth.verify_password_change_otp'))

    existing_token = TwoFactorToken.query.get(token_id)
    if not existing_token or existing_token.user_id != current_user.id or existing_token.purpose != 'admin_password_change':
        session.pop('pending_password_change_token_id', None)
        flash('Invalid verification session. Restart password change.', 'danger')
        return redirect(url_for('auth.change_password'))

    payload_hash = existing_token.payload_hash
    token, code = _create_otp_token(current_user.id, 'admin_password_change', payload_hash=payload_hash)
    sent, send_message = _send_admin_otp(current_user, code, 'admin password change')
    if not sent:
        app_env = (current_app.config.get('APP_ENV') or 'development').lower()
        if app_env == 'production':
            db.session.rollback()
            flash('Unable to resend verification code email. Check mail configuration.', 'danger')
            return redirect(url_for('auth.verify_password_change_otp'))
        flash(f'Email delivery unavailable ({send_message}). Use this dev OTP: {code}', 'warning')

    db.session.commit()
    session['pending_password_change_token_id'] = token.id
    _mark_otp_sent('pending_password_change_otp_sent_at')
    flash('A new verification code was sent.', 'info')
    return redirect(url_for('auth.verify_password_change_otp'))


@auth_bp.route('/logout')
@login_required
def logout():
    try:
        log_audit('logout', 'auth', entity_id=current_user.id, metadata={'username': current_user.username})
        db.session.commit()
    except Exception:
        db.session.rollback()
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))
