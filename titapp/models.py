from datetime import datetime
from flask_login import UserMixin
from .extensions import db, login_manager


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(30), default='admin')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    preference = db.relationship('UserPreference', backref='user', uselist=False, cascade='all, delete-orphan')

    def set_password(self, password):
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, password)


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), unique=True, nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    middle_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=False)
    gender = db.Column(db.String(10), nullable=False)
    nationality = db.Column(db.String(60), nullable=False)
    national_id = db.Column(db.String(30))
    marital_status = db.Column(db.String(20))
    religion = db.Column(db.String(50))
    blood_group = db.Column(db.String(5))
    disability = db.Column(db.String(200))
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20), nullable=False)
    alt_phone = db.Column(db.String(20))
    address = db.Column(db.Text, nullable=False)
    city = db.Column(db.String(60))
    state_province = db.Column(db.String(60))
    postal_code = db.Column(db.String(15))
    country = db.Column(db.String(60))
    programme = db.Column(db.String(150))
    department = db.Column(db.String(150))
    intake_year = db.Column(db.Integer)
    intake_semester = db.Column(db.String(20))
    mode_of_study = db.Column(db.String(30))
    photo_filename = db.Column(db.String(255))
    emergency_name = db.Column(db.String(150))
    emergency_relationship = db.Column(db.String(50))
    emergency_phone = db.Column(db.String(20))
    emergency_email = db.Column(db.String(120))
    emergency_address = db.Column(db.Text)
    medical_conditions = db.Column(db.Text)
    allergies = db.Column(db.Text)
    finance_tuition_fee = db.Column(db.Float, default=0.0)
    finance_registration_fee = db.Column(db.Float, default=0.0)
    finance_exam_fee = db.Column(db.Float, default=0.0)
    finance_library_ict_fee = db.Column(db.Float, default=0.0)
    finance_lab_practical_fee = db.Column(db.Float, default=0.0)
    finance_accommodation_fee = db.Column(db.Float, default=0.0)
    finance_miscellaneous_fee = db.Column(db.Float, default=0.0)
    finance_scholarship_discount = db.Column(db.Float, default=0.0)
    finance_amount_paid = db.Column(db.Float, default=0.0)
    finance_full_cost = db.Column(db.Float, default=0.0)
    finance_other_commitments = db.Column(db.Float, default=0.0)
    finance_outstanding = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default='Active')
    workflow_stage = db.Column(db.String(30), default='Applied')
    stage_updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    approved_at = db.Column(db.DateTime)
    deleted_at = db.Column(db.DateTime)
    deleted_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    education_history = db.relationship('EducationHistory', backref='student', lazy=True, cascade='all, delete-orphan')
    work_experience = db.relationship('WorkExperience', backref='student', lazy=True, cascade='all, delete-orphan')
    parents = db.relationship('ParentGuardian', backref='student', lazy=True, cascade='all, delete-orphan')
    documents = db.relationship('Document', backref='student', lazy=True, cascade='all, delete-orphan')
    payments = db.relationship('StudentPayment', backref='student', lazy=True, cascade='all, delete-orphan')
    installments = db.relationship('InstallmentPlan', backref='student', lazy=True, cascade='all, delete-orphan')
    stage_history = db.relationship('StudentStageHistory', backref='student', lazy=True, cascade='all, delete-orphan')

    @property
    def full_name(self):
        names = [self.first_name or '', self.middle_name or '', self.last_name or '']
        return ' '.join([name for name in names if name]).strip()

    @property
    def completeness_score(self):
        checks = [
            bool(self.first_name), bool(self.last_name), bool(self.date_of_birth), bool(self.gender),
            bool(self.nationality), bool(self.phone), bool(self.address), bool(self.programme),
            bool(self.department), bool(self.photo_filename), bool(self.email), bool(self.country),
            bool(self.emergency_name), bool(self.emergency_phone), bool(self.education_history), bool(self.parents),
        ]
        return int(round((sum(1 for item in checks if item) / len(checks)) * 100))

    @property
    def completeness_tier(self):
        score = self.completeness_score
        if score >= 80:
            return 'high'
        if score >= 50:
            return 'medium'
        return 'low'


class EducationHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    institution_name = db.Column(db.String(200), nullable=False)
    level = db.Column(db.String(80))
    qualification = db.Column(db.String(150))
    field_of_study = db.Column(db.String(150))
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    grade = db.Column(db.String(30))
    country = db.Column(db.String(60))


class WorkExperience(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    company_name = db.Column(db.String(200), nullable=False)
    job_title = db.Column(db.String(150))
    employment_type = db.Column(db.String(30))
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    responsibilities = db.Column(db.Text)
    country = db.Column(db.String(60))


class ParentGuardian(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    relationship = db.Column(db.String(30), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    occupation = db.Column(db.String(150))
    employer = db.Column(db.String(200))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    address = db.Column(db.Text)
    national_id = db.Column(db.String(30))


class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    doc_type = db.Column(db.String(80))
    filename = db.Column(db.String(255))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    action = db.Column(db.String(80), nullable=False)
    entity = db.Column(db.String(80), nullable=False)
    entity_id = db.Column(db.String(80))
    metadata_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class UserPreference(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    theme = db.Column(db.String(20), default='system')
    students_per_page = db.Column(db.Integer, default=10)
    compact_tables = db.Column(db.Boolean, default=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class StudentPayment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    receipt_number = db.Column(db.String(40), unique=True, nullable=False)
    amount = db.Column(db.Float, nullable=False, default=0.0)
    payment_method = db.Column(db.String(40), default='Cash')
    notes = db.Column(db.String(255))
    paid_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    recorded_by = db.Column(db.Integer, db.ForeignKey('user.id'))


class InstallmentPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Float, nullable=False, default=0.0)
    is_paid = db.Column(db.Boolean, default=False)
    paid_at = db.Column(db.DateTime)
    notes = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class StudentStageHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    from_stage = db.Column(db.String(30))
    to_stage = db.Column(db.String(30), nullable=False)
    changed_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    changed_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.String(255))


class NotificationLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    channel = db.Column(db.String(30), default='email')
    recipient = db.Column(db.String(120))
    message = db.Column(db.Text)
    status = db.Column(db.String(20), default='queued')
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    sent_by = db.Column(db.Integer, db.ForeignKey('user.id'))


class SavedFilterPreset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    search = db.Column(db.String(120), default='')
    status = db.Column(db.String(30), default='')
    department = db.Column(db.String(150), default='')
    workflow = db.Column(db.String(30), default='')
    sort = db.Column(db.String(20), default='newest')
    include_deleted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class TwoFactorToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    purpose = db.Column(db.String(40), nullable=False, index=True)
    code_hash = db.Column(db.String(256), nullable=False)
    payload_hash = db.Column(db.String(256))
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    consumed_at = db.Column(db.DateTime)
    attempts = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
