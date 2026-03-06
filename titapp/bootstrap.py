import os
from .extensions import db
from .models import User


def _reconcile_sqlite_schema():
    database_uri = str(db.engine.url)
    if not database_uri.startswith('sqlite'):
        return

    tables = {
        row[0] for row in db.session.execute(
            db.text("SELECT name FROM sqlite_master WHERE type='table'")
        ).fetchall()
    }
    if 'student' not in tables:
        return

    columns = {
        row[1] for row in db.session.execute(
            db.text('PRAGMA table_info(student)')
        ).fetchall()
    }

    if 'deleted_at' not in columns:
        db.session.execute(db.text('ALTER TABLE student ADD COLUMN deleted_at DATETIME'))
    if 'deleted_by' not in columns:
        db.session.execute(db.text('ALTER TABLE student ADD COLUMN deleted_by INTEGER'))
    if 'finance_amount_paid' not in columns:
        db.session.execute(db.text('ALTER TABLE student ADD COLUMN finance_amount_paid FLOAT DEFAULT 0'))
    if 'finance_tuition_fee' not in columns:
        db.session.execute(db.text('ALTER TABLE student ADD COLUMN finance_tuition_fee FLOAT DEFAULT 0'))
    if 'finance_registration_fee' not in columns:
        db.session.execute(db.text('ALTER TABLE student ADD COLUMN finance_registration_fee FLOAT DEFAULT 0'))
    if 'finance_exam_fee' not in columns:
        db.session.execute(db.text('ALTER TABLE student ADD COLUMN finance_exam_fee FLOAT DEFAULT 0'))
    if 'finance_library_ict_fee' not in columns:
        db.session.execute(db.text('ALTER TABLE student ADD COLUMN finance_library_ict_fee FLOAT DEFAULT 0'))
    if 'finance_lab_practical_fee' not in columns:
        db.session.execute(db.text('ALTER TABLE student ADD COLUMN finance_lab_practical_fee FLOAT DEFAULT 0'))
    if 'finance_accommodation_fee' not in columns:
        db.session.execute(db.text('ALTER TABLE student ADD COLUMN finance_accommodation_fee FLOAT DEFAULT 0'))
    if 'finance_miscellaneous_fee' not in columns:
        db.session.execute(db.text('ALTER TABLE student ADD COLUMN finance_miscellaneous_fee FLOAT DEFAULT 0'))
    if 'finance_scholarship_discount' not in columns:
        db.session.execute(db.text('ALTER TABLE student ADD COLUMN finance_scholarship_discount FLOAT DEFAULT 0'))
    if 'finance_full_cost' not in columns:
        db.session.execute(db.text('ALTER TABLE student ADD COLUMN finance_full_cost FLOAT DEFAULT 0'))
    if 'finance_other_commitments' not in columns:
        db.session.execute(db.text('ALTER TABLE student ADD COLUMN finance_other_commitments FLOAT DEFAULT 0'))
    if 'finance_outstanding' not in columns:
        db.session.execute(db.text('ALTER TABLE student ADD COLUMN finance_outstanding FLOAT DEFAULT 0'))
    if 'workflow_stage' not in columns:
        db.session.execute(db.text("ALTER TABLE student ADD COLUMN workflow_stage VARCHAR(30) DEFAULT 'Applied'"))
    if 'stage_updated_at' not in columns:
        db.session.execute(db.text('ALTER TABLE student ADD COLUMN stage_updated_at DATETIME'))
    if 'approved_by' not in columns:
        db.session.execute(db.text('ALTER TABLE student ADD COLUMN approved_by INTEGER'))
    if 'approved_at' not in columns:
        db.session.execute(db.text('ALTER TABLE student ADD COLUMN approved_at DATETIME'))

    if 'saved_filter_preset' not in tables:
        db.session.execute(db.text('''
            CREATE TABLE saved_filter_preset (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                name VARCHAR(80) NOT NULL,
                search VARCHAR(120) DEFAULT '',
                status VARCHAR(30) DEFAULT '',
                department VARCHAR(150) DEFAULT '',
                workflow VARCHAR(30) DEFAULT '',
                sort VARCHAR(20) DEFAULT 'newest',
                include_deleted BOOLEAN DEFAULT 0,
                created_at DATETIME
            )
        '''))
    else:
        preset_columns = {
            row[1] for row in db.session.execute(
                db.text('PRAGMA table_info(saved_filter_preset)')
            ).fetchall()
        }
        if 'workflow' not in preset_columns:
            db.session.execute(db.text("ALTER TABLE saved_filter_preset ADD COLUMN workflow VARCHAR(30) DEFAULT ''"))

    if 'student_payment' not in tables:
        db.session.execute(db.text('''
            CREATE TABLE student_payment (
                id INTEGER PRIMARY KEY,
                student_id INTEGER NOT NULL,
                receipt_number VARCHAR(40) NOT NULL UNIQUE,
                amount FLOAT NOT NULL DEFAULT 0,
                payment_method VARCHAR(40) DEFAULT 'Cash',
                notes VARCHAR(255),
                paid_at DATETIME,
                recorded_by INTEGER
            )
        '''))

    if 'installment_plan' not in tables:
        db.session.execute(db.text('''
            CREATE TABLE installment_plan (
                id INTEGER PRIMARY KEY,
                student_id INTEGER NOT NULL,
                due_date DATE NOT NULL,
                amount FLOAT NOT NULL DEFAULT 0,
                is_paid BOOLEAN DEFAULT 0,
                paid_at DATETIME,
                notes VARCHAR(255),
                created_at DATETIME
            )
        '''))

    if 'student_stage_history' not in tables:
        db.session.execute(db.text('''
            CREATE TABLE student_stage_history (
                id INTEGER PRIMARY KEY,
                student_id INTEGER NOT NULL,
                from_stage VARCHAR(30),
                to_stage VARCHAR(30) NOT NULL,
                changed_by INTEGER,
                changed_at DATETIME,
                notes VARCHAR(255)
            )
        '''))

    if 'notification_log' not in tables:
        db.session.execute(db.text('''
            CREATE TABLE notification_log (
                id INTEGER PRIMARY KEY,
                student_id INTEGER NOT NULL,
                channel VARCHAR(30) DEFAULT 'email',
                recipient VARCHAR(120),
                message TEXT,
                status VARCHAR(20) DEFAULT 'queued',
                sent_at DATETIME,
                sent_by INTEGER
            )
        '''))

    if 'two_factor_token' not in tables:
        db.session.execute(db.text('''
            CREATE TABLE two_factor_token (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                purpose VARCHAR(40) NOT NULL,
                code_hash VARCHAR(256) NOT NULL,
                payload_hash VARCHAR(256),
                expires_at DATETIME NOT NULL,
                consumed_at DATETIME,
                attempts INTEGER DEFAULT 0,
                created_at DATETIME
            )
        '''))

    db.session.commit()


def bootstrap_data(app):
    with app.app_context():
        auto_create = os.getenv('AUTO_CREATE_DB', 'true').lower() == 'true'
        if auto_create:
            db.create_all()
            _reconcile_sqlite_schema()

        create_default_admin = os.getenv('CREATE_DEFAULT_ADMIN', 'false').lower() == 'true'
        if create_default_admin:
            default_admin_user = os.getenv('DEFAULT_ADMIN_USERNAME', 'titadmin')
            default_admin_email = os.getenv('DEFAULT_ADMIN_EMAIL', 'admin@tit.ac.zw')
            default_admin_password = os.getenv('DEFAULT_ADMIN_PASSWORD', 'TITAdmin@2026!')

            admin = User.query.filter_by(username=default_admin_user).first()
            if not admin:
                admin = User(
                    username=default_admin_user,
                    email=default_admin_email,
                    full_name='System Administrator',
                    role='admin'
                )
                db.session.add(admin)
            else:
                admin.email = default_admin_email
                admin.role = 'admin'

            admin.set_password(default_admin_password)
            db.session.commit()
            app.logger.warning('Default admin created via bootstrap. Disable CREATE_DEFAULT_ADMIN after first deploy.')
