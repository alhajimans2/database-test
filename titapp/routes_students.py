import csv
import os
import uuid
from io import StringIO
from collections import Counter
from datetime import datetime, date
from flask import Blueprint, render_template, request, redirect, url_for, flash, Response, current_app
from flask_login import login_required, current_user
from .extensions import db
from .models import (
    Student,
    EducationHistory,
    WorkExperience,
    ParentGuardian,
    UserPreference,
    StudentPayment,
    InstallmentPlan,
    StudentStageHistory,
    NotificationLog,
    SavedFilterPreset,
    AuditLog,
)
from .audit import log_audit
from .authz import role_required


students_bp = Blueprint('students', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
WORKFLOW_STAGES = ['Applied', 'Screening', 'Interview', 'Approved', 'Registered', 'Active', 'Suspended', 'Graduated', 'Alumni']


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def generate_student_id():
    year = datetime.now().year
    last = Student.query.order_by(Student.id.desc()).first()
    seq = (last.id + 1) if last else 1
    return f"TIT{year}{seq:04d}"


def parse_money(value):
    try:
        if value is None:
            return 0.0
        return max(float(str(value).strip() or 0), 0.0)
    except (TypeError, ValueError):
        return 0.0


def calculate_outstanding(full_cost, amount_paid, other_commitments):
    total_due = parse_money(full_cost) + parse_money(other_commitments)
    paid = parse_money(amount_paid)
    return round(max(total_due - paid, 0.0), 2)


def calculate_full_cost(fees):
    gross_total = (
        parse_money(fees.get('finance_tuition_fee'))
        + parse_money(fees.get('finance_registration_fee'))
        + parse_money(fees.get('finance_exam_fee'))
        + parse_money(fees.get('finance_library_ict_fee'))
        + parse_money(fees.get('finance_lab_practical_fee'))
        + parse_money(fees.get('finance_accommodation_fee'))
        + parse_money(fees.get('finance_miscellaneous_fee'))
    )
    discount = parse_money(fees.get('finance_scholarship_discount'))
    return round(max(gross_total - discount, 0.0), 2)


def generate_receipt_number():
    stamp = datetime.utcnow().strftime('%Y%m%d')
    sequence = StudentPayment.query.count() + 1
    return f"RCT-{stamp}-{sequence:05d}"


def recalculate_student_finance(student):
    student.finance_full_cost = calculate_full_cost({
        'finance_tuition_fee': student.finance_tuition_fee,
        'finance_registration_fee': student.finance_registration_fee,
        'finance_exam_fee': student.finance_exam_fee,
        'finance_library_ict_fee': student.finance_library_ict_fee,
        'finance_lab_practical_fee': student.finance_lab_practical_fee,
        'finance_accommodation_fee': student.finance_accommodation_fee,
        'finance_miscellaneous_fee': student.finance_miscellaneous_fee,
        'finance_scholarship_discount': student.finance_scholarship_discount,
    })

    ledger_total_paid = db.session.query(db.func.coalesce(db.func.sum(StudentPayment.amount), 0.0)).filter_by(student_id=student.id).scalar() or 0.0
    baseline_paid = parse_money(student.finance_amount_paid)
    student.finance_amount_paid = round(max(baseline_paid, ledger_total_paid), 2)
    student.finance_outstanding = calculate_outstanding(
        student.finance_full_cost,
        student.finance_amount_paid,
        student.finance_other_commitments,
    )


def get_sort_expression(sort_by):
    sort_options = {
        'newest': Student.created_at.desc(),
        'oldest': Student.created_at.asc(),
        'name_asc': Student.first_name.asc(),
        'name_desc': Student.first_name.desc(),
        'id_asc': Student.student_id.asc(),
        'id_desc': Student.student_id.desc(),
    }
    return sort_options.get(sort_by, Student.created_at.desc())


def apply_student_filters(base_query, search, status_filter, dept_filter, workflow_filter='', include_deleted=False):
    query = base_query
    if not include_deleted:
        query = query.filter(Student.deleted_at.is_(None))
    if search:
        like = f'%{search}%'
        query = query.filter(
            db.or_(
                Student.first_name.ilike(like),
                Student.last_name.ilike(like),
                Student.student_id.ilike(like),
                Student.email.ilike(like),
                Student.phone.ilike(like),
            )
        )
    if status_filter:
        query = query.filter_by(status=status_filter)
    if dept_filter:
        query = query.filter_by(department=dept_filter)
    if workflow_filter:
        query = query.filter_by(workflow_stage=workflow_filter)
    return query


@students_bp.route('/students')
@login_required
def student_list():
    search = request.args.get('search', '')
    status_filter = request.args.get('status', '')
    dept_filter = request.args.get('department', '')
    workflow_filter = request.args.get('workflow', '')
    sort_by = request.args.get('sort', 'newest')
    page = max(int(request.args.get('page', 1) or 1), 1)
    preferred_per_page = 10
    preference = UserPreference.query.filter_by(user_id=current_user.id).first()
    if preference and preference.students_per_page in [10, 25, 50, 100]:
        preferred_per_page = preference.students_per_page

    per_page = int(request.args.get('per_page', preferred_per_page) or preferred_per_page)
    include_deleted = request.args.get('include_deleted', '') == '1'
    per_page = per_page if per_page in [10, 25, 50, 100] else 10

    query = apply_student_filters(Student.query, search, status_filter, dept_filter, workflow_filter, include_deleted)

    query = query.order_by(get_sort_expression(sort_by))

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    students = pagination.items
    departments = db.session.query(Student.department).distinct().all()
    presets = SavedFilterPreset.query.filter_by(user_id=current_user.id).order_by(SavedFilterPreset.created_at.desc()).all()

    return render_template(
        'students.html',
        students=students,
        departments=departments,
        search=search,
        status_filter=status_filter,
        dept_filter=dept_filter,
        workflow_filter=workflow_filter,
        workflow_stages=WORKFLOW_STAGES,
        sort_by=sort_by,
        per_page=per_page,
        include_deleted=include_deleted,
        pagination=pagination,
        presets=presets,
    )


@students_bp.route('/students/export')
@login_required
@role_required('admin', 'registrar', 'hod')
def export_students_csv():
    search = request.args.get('search', '')
    status_filter = request.args.get('status', '')
    dept_filter = request.args.get('department', '')
    workflow_filter = request.args.get('workflow', '')
    sort_by = request.args.get('sort', 'newest')
    include_deleted = request.args.get('include_deleted', '') == '1'

    query = apply_student_filters(Student.query, search, status_filter, dept_filter, workflow_filter, include_deleted)

    students = query.order_by(get_sort_expression(sort_by)).all()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Student ID', 'Full Name', 'Gender', 'Programme', 'Department',
        'Phone', 'Email', 'Status', 'Completeness (%)',
        'Tuition Fee', 'Registration Fee', 'Exam Fee', 'Library/ICT Fee',
        'Lab/Practical Fee', 'Accommodation Fee', 'Misc Fee', 'Scholarship/Discount',
        'Net Programme Cost', 'Amount Paid', 'Other Commitments', 'Outstanding',
        'Workflow Stage',
        'Created At'
    ])
    for student in students:
        writer.writerow([
            student.student_id,
            student.full_name,
            student.gender or '',
            student.programme or '',
            student.department or '',
            student.phone or '',
            student.email or '',
            student.status or '',
            student.completeness_score,
            f"{(student.finance_tuition_fee or 0):.2f}",
            f"{(student.finance_registration_fee or 0):.2f}",
            f"{(student.finance_exam_fee or 0):.2f}",
            f"{(student.finance_library_ict_fee or 0):.2f}",
            f"{(student.finance_lab_practical_fee or 0):.2f}",
            f"{(student.finance_accommodation_fee or 0):.2f}",
            f"{(student.finance_miscellaneous_fee or 0):.2f}",
            f"{(student.finance_scholarship_discount or 0):.2f}",
            f"{(student.finance_full_cost or 0):.2f}",
            f"{(student.finance_amount_paid or 0):.2f}",
            f"{(student.finance_other_commitments or 0):.2f}",
            f"{(student.finance_outstanding or 0):.2f}",
            student.workflow_stage or '',
            student.created_at.strftime('%Y-%m-%d %H:%M:%S') if student.created_at else '',
        ])

    csv_data = output.getvalue()
    output.close()
    filename = f"tit_students_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    log_audit('export', 'student', metadata={'format': 'csv', 'count': len(students)})
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@students_bp.route('/students/import', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'registrar')
def import_students_csv():
    report = []
    imported_count = 0

    if request.method == 'POST':
        upload = request.files.get('csv_file')
        if not upload or not upload.filename:
            flash('Please select a CSV file to import.', 'warning')
            return render_template('students_import.html', report=report, imported_count=imported_count)

        try:
            content = upload.read().decode('utf-8-sig')
            reader = csv.DictReader(StringIO(content))
            required_fields = ['first_name', 'last_name', 'date_of_birth', 'gender', 'nationality', 'phone', 'address']

            for line_number, row in enumerate(reader, start=2):
                missing = [field for field in required_fields if not (row.get(field) or '').strip()]
                if missing:
                    report.append({'line': line_number, 'error': f"Missing required fields: {', '.join(missing)}", 'row': row})
                    continue

                try:
                    dob = datetime.strptime((row.get('date_of_birth') or '').strip(), '%Y-%m-%d').date()
                except ValueError:
                    report.append({'line': line_number, 'error': 'Invalid date_of_birth format (use YYYY-MM-DD).', 'row': row})
                    continue

                student = Student(
                    student_id=generate_student_id(),
                    first_name=(row.get('first_name') or '').strip(),
                    middle_name=(row.get('middle_name') or '').strip(),
                    last_name=(row.get('last_name') or '').strip(),
                    date_of_birth=dob,
                    gender=(row.get('gender') or '').strip(),
                    nationality=(row.get('nationality') or '').strip(),
                    national_id=(row.get('national_id') or '').strip(),
                    marital_status=(row.get('marital_status') or '').strip(),
                    religion=(row.get('religion') or '').strip(),
                    blood_group=(row.get('blood_group') or '').strip(),
                    disability=(row.get('disability') or '').strip(),
                    email=(row.get('email') or '').strip(),
                    phone=(row.get('phone') or '').strip(),
                    alt_phone=(row.get('alt_phone') or '').strip(),
                    address=(row.get('address') or '').strip(),
                    city=(row.get('city') or '').strip(),
                    state_province=(row.get('state_province') or '').strip(),
                    postal_code=(row.get('postal_code') or '').strip(),
                    country=(row.get('country') or '').strip(),
                    programme=(row.get('programme') or '').strip(),
                    department=(row.get('department') or '').strip(),
                    intake_year=int((row.get('intake_year') or datetime.now().year)),
                    intake_semester=(row.get('intake_semester') or '').strip(),
                    mode_of_study=(row.get('mode_of_study') or '').strip(),
                    emergency_name=(row.get('emergency_name') or '').strip(),
                    emergency_relationship=(row.get('emergency_relationship') or '').strip(),
                    emergency_phone=(row.get('emergency_phone') or '').strip(),
                    emergency_email=(row.get('emergency_email') or '').strip(),
                    emergency_address=(row.get('emergency_address') or '').strip(),
                    medical_conditions=(row.get('medical_conditions') or '').strip(),
                    allergies=(row.get('allergies') or '').strip(),
                    finance_tuition_fee=parse_money(row.get('finance_tuition_fee')),
                    finance_registration_fee=parse_money(row.get('finance_registration_fee')),
                    finance_exam_fee=parse_money(row.get('finance_exam_fee')),
                    finance_library_ict_fee=parse_money(row.get('finance_library_ict_fee')),
                    finance_lab_practical_fee=parse_money(row.get('finance_lab_practical_fee')),
                    finance_accommodation_fee=parse_money(row.get('finance_accommodation_fee')),
                    finance_miscellaneous_fee=parse_money(row.get('finance_miscellaneous_fee')),
                    finance_scholarship_discount=parse_money(row.get('finance_scholarship_discount')),
                    finance_amount_paid=parse_money(row.get('finance_amount_paid')),
                    finance_full_cost=0,
                    finance_other_commitments=parse_money(row.get('finance_other_commitments')),
                    finance_outstanding=0,
                    status=(row.get('status') or 'Active').strip(),
                    workflow_stage=(row.get('workflow_stage') or 'Applied').strip() if (row.get('workflow_stage') or 'Applied').strip() in WORKFLOW_STAGES else 'Applied',
                    stage_updated_at=datetime.utcnow(),
                )
                calculated_full_cost = calculate_full_cost({
                    'finance_tuition_fee': student.finance_tuition_fee,
                    'finance_registration_fee': student.finance_registration_fee,
                    'finance_exam_fee': student.finance_exam_fee,
                    'finance_library_ict_fee': student.finance_library_ict_fee,
                    'finance_lab_practical_fee': student.finance_lab_practical_fee,
                    'finance_accommodation_fee': student.finance_accommodation_fee,
                    'finance_miscellaneous_fee': student.finance_miscellaneous_fee,
                    'finance_scholarship_discount': student.finance_scholarship_discount,
                })
                if calculated_full_cost == 0:
                    calculated_full_cost = parse_money(row.get('finance_full_cost'))
                student.finance_full_cost = calculated_full_cost
                recalculate_student_finance(student)
                db.session.add(student)
                imported_count += 1

            db.session.commit()
            log_audit('import', 'student', metadata={'format': 'csv', 'imported': imported_count, 'failed': len(report)})
            flash(f'Import completed. Imported: {imported_count}, Failed: {len(report)}.', 'success' if imported_count else 'warning')
        except Exception as error:
            db.session.rollback()
            flash(f'Import failed: {str(error)}', 'danger')

    return render_template('students_import.html', report=report, imported_count=imported_count)


@students_bp.route('/students/add', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'registrar')
def add_student():
    if request.method == 'POST':
        try:
            finance_tuition_fee = parse_money(request.form.get('finance_tuition_fee'))
            finance_registration_fee = parse_money(request.form.get('finance_registration_fee'))
            finance_exam_fee = parse_money(request.form.get('finance_exam_fee'))
            finance_library_ict_fee = parse_money(request.form.get('finance_library_ict_fee'))
            finance_lab_practical_fee = parse_money(request.form.get('finance_lab_practical_fee'))
            finance_accommodation_fee = parse_money(request.form.get('finance_accommodation_fee'))
            finance_miscellaneous_fee = parse_money(request.form.get('finance_miscellaneous_fee'))
            finance_scholarship_discount = parse_money(request.form.get('finance_scholarship_discount'))
            finance_amount_paid = parse_money(request.form.get('finance_amount_paid'))
            finance_other_commitments = parse_money(request.form.get('finance_other_commitments'))
            finance_full_cost = calculate_full_cost({
                'finance_tuition_fee': finance_tuition_fee,
                'finance_registration_fee': finance_registration_fee,
                'finance_exam_fee': finance_exam_fee,
                'finance_library_ict_fee': finance_library_ict_fee,
                'finance_lab_practical_fee': finance_lab_practical_fee,
                'finance_accommodation_fee': finance_accommodation_fee,
                'finance_miscellaneous_fee': finance_miscellaneous_fee,
                'finance_scholarship_discount': finance_scholarship_discount,
            })

            student = Student(
                student_id=generate_student_id(),
                first_name=request.form['first_name'],
                middle_name=request.form.get('middle_name', ''),
                last_name=request.form['last_name'],
                date_of_birth=datetime.strptime(request.form['date_of_birth'], '%Y-%m-%d').date(),
                gender=request.form['gender'],
                nationality=request.form['nationality'],
                national_id=request.form.get('national_id', ''),
                marital_status=request.form.get('marital_status', ''),
                religion=request.form.get('religion', ''),
                blood_group=request.form.get('blood_group', ''),
                disability=request.form.get('disability', ''),
                email=request.form.get('email', ''),
                phone=request.form['phone'],
                alt_phone=request.form.get('alt_phone', ''),
                address=request.form['address'],
                city=request.form.get('city', ''),
                state_province=request.form.get('state_province', ''),
                postal_code=request.form.get('postal_code', ''),
                country=request.form.get('country', ''),
                programme=request.form.get('programme', ''),
                department=request.form.get('department', ''),
                intake_year=int(request.form.get('intake_year') or datetime.now().year),
                intake_semester=request.form.get('intake_semester', ''),
                mode_of_study=request.form.get('mode_of_study', ''),
                emergency_name=request.form.get('emergency_name', ''),
                emergency_relationship=request.form.get('emergency_relationship', ''),
                emergency_phone=request.form.get('emergency_phone', ''),
                emergency_email=request.form.get('emergency_email', ''),
                emergency_address=request.form.get('emergency_address', ''),
                medical_conditions=request.form.get('medical_conditions', ''),
                allergies=request.form.get('allergies', ''),
                finance_tuition_fee=finance_tuition_fee,
                finance_registration_fee=finance_registration_fee,
                finance_exam_fee=finance_exam_fee,
                finance_library_ict_fee=finance_library_ict_fee,
                finance_lab_practical_fee=finance_lab_practical_fee,
                finance_accommodation_fee=finance_accommodation_fee,
                finance_miscellaneous_fee=finance_miscellaneous_fee,
                finance_scholarship_discount=finance_scholarship_discount,
                finance_amount_paid=finance_amount_paid,
                finance_full_cost=finance_full_cost,
                finance_other_commitments=finance_other_commitments,
                finance_outstanding=calculate_outstanding(finance_full_cost, finance_amount_paid, finance_other_commitments),
                workflow_stage='Applied',
                stage_updated_at=datetime.utcnow(),
            )

            if 'photo' in request.files:
                photo = request.files['photo']
                if photo and photo.filename and allowed_file(photo.filename):
                    ext = photo.filename.rsplit('.', 1)[1].lower()
                    filename = f"{uuid.uuid4().hex}.{ext}"
                    photo.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
                    student.photo_filename = filename

            db.session.add(student)
            db.session.flush()
            recalculate_student_finance(student)
            db.session.add(StudentStageHistory(
                student_id=student.id,
                from_stage=None,
                to_stage=student.workflow_stage,
                changed_by=current_user.id,
                notes='Initial stage on registration',
            ))

            edu_institutions = request.form.getlist('edu_institution[]')
            edu_levels = request.form.getlist('edu_level[]')
            edu_qualifications = request.form.getlist('edu_qualification[]')
            edu_fields = request.form.getlist('edu_field[]')
            edu_starts = request.form.getlist('edu_start[]')
            edu_ends = request.form.getlist('edu_end[]')
            edu_grades = request.form.getlist('edu_grade[]')
            edu_countries = request.form.getlist('edu_country[]')

            for i in range(len(edu_institutions)):
                if edu_institutions[i].strip():
                    db.session.add(EducationHistory(
                        student_id=student.id,
                        institution_name=edu_institutions[i],
                        level=edu_levels[i] if i < len(edu_levels) else '',
                        qualification=edu_qualifications[i] if i < len(edu_qualifications) else '',
                        field_of_study=edu_fields[i] if i < len(edu_fields) else '',
                        start_date=datetime.strptime(edu_starts[i], '%Y-%m-%d').date() if i < len(edu_starts) and edu_starts[i] else None,
                        end_date=datetime.strptime(edu_ends[i], '%Y-%m-%d').date() if i < len(edu_ends) and edu_ends[i] else None,
                        grade=edu_grades[i] if i < len(edu_grades) else '',
                        country=edu_countries[i] if i < len(edu_countries) else '',
                    ))

            work_companies = request.form.getlist('work_company[]')
            work_titles = request.form.getlist('work_title[]')
            work_types = request.form.getlist('work_type[]')
            work_starts = request.form.getlist('work_start[]')
            work_ends = request.form.getlist('work_end[]')
            work_responsibilities = request.form.getlist('work_responsibilities[]')
            work_countries = request.form.getlist('work_country[]')

            for i in range(len(work_companies)):
                if work_companies[i].strip():
                    db.session.add(WorkExperience(
                        student_id=student.id,
                        company_name=work_companies[i],
                        job_title=work_titles[i] if i < len(work_titles) else '',
                        employment_type=work_types[i] if i < len(work_types) else '',
                        start_date=datetime.strptime(work_starts[i], '%Y-%m-%d').date() if i < len(work_starts) and work_starts[i] else None,
                        end_date=datetime.strptime(work_ends[i], '%Y-%m-%d').date() if i < len(work_ends) and work_ends[i] else None,
                        responsibilities=work_responsibilities[i] if i < len(work_responsibilities) else '',
                        country=work_countries[i] if i < len(work_countries) else '',
                    ))

            parent_rels = request.form.getlist('parent_relationship[]')
            parent_fnames = request.form.getlist('parent_first_name[]')
            parent_lnames = request.form.getlist('parent_last_name[]')
            parent_occupations = request.form.getlist('parent_occupation[]')
            parent_employers = request.form.getlist('parent_employer[]')
            parent_phones = request.form.getlist('parent_phone[]')
            parent_emails = request.form.getlist('parent_email[]')
            parent_addresses = request.form.getlist('parent_address[]')
            parent_nids = request.form.getlist('parent_national_id[]')

            for i in range(len(parent_fnames)):
                if parent_fnames[i].strip():
                    db.session.add(ParentGuardian(
                        student_id=student.id,
                        relationship=parent_rels[i] if i < len(parent_rels) else '',
                        first_name=parent_fnames[i],
                        last_name=parent_lnames[i] if i < len(parent_lnames) else '',
                        occupation=parent_occupations[i] if i < len(parent_occupations) else '',
                        employer=parent_employers[i] if i < len(parent_employers) else '',
                        phone=parent_phones[i] if i < len(parent_phones) else '',
                        email=parent_emails[i] if i < len(parent_emails) else '',
                        address=parent_addresses[i] if i < len(parent_addresses) else '',
                        national_id=parent_nids[i] if i < len(parent_nids) else '',
                    ))

            db.session.commit()
            log_audit('create', 'student', entity_id=student.id, metadata={'student_id': student.student_id})
            flash(f'Student {student.student_id} registered successfully!', 'success')
            return redirect(url_for('students.view_student', student_id=student.id))
        except Exception as error:
            db.session.rollback()
            flash(f'Error: {str(error)}', 'danger')

    return render_template('add_student.html')


@students_bp.route('/students/<int:student_id>')
@login_required
def view_student(student_id):
    student = Student.query.filter(Student.deleted_at.is_(None), Student.id == student_id).first_or_404()

    timeline_events = []

    if student.created_at:
        timeline_events.append({
            'when': student.created_at,
            'icon': 'fa-user-plus',
            'title': 'Student Registered',
            'description': f"Record created with ID {student.student_id}.",
        })

    for history in student.stage_history or []:
        if history.changed_at:
            timeline_events.append({
                'when': history.changed_at,
                'icon': 'fa-diagram-project',
                'title': f"Workflow: {history.from_stage or '—'} → {history.to_stage}",
                'description': history.notes or 'Workflow stage updated.',
            })

    for payment in student.payments or []:
        if payment.paid_at:
            timeline_events.append({
                'when': payment.paid_at,
                'icon': 'fa-receipt',
                'title': f"Payment Recorded ({payment.receipt_number})",
                'description': f"Leones {parse_money(payment.amount):.2f} via {payment.payment_method or 'N/A'}.",
            })

    for installment in student.installments or []:
        if installment.created_at:
            timeline_events.append({
                'when': installment.created_at,
                'icon': 'fa-calendar-plus',
                'title': 'Installment Scheduled',
                'description': f"Due {installment.due_date.strftime('%d %b %Y') if installment.due_date else '—'} for Leones {parse_money(installment.amount):.2f}.",
            })

    reminders = NotificationLog.query.filter_by(student_id=student.id).order_by(NotificationLog.sent_at.desc()).limit(20).all()
    for reminder in reminders:
        if reminder.sent_at:
            timeline_events.append({
                'when': reminder.sent_at,
                'icon': 'fa-paper-plane',
                'title': f"Reminder Sent ({(reminder.channel or 'email').upper()})",
                'description': f"To {reminder.recipient or 'N/A'} • Status: {reminder.status or 'queued'}",
            })

    timeline_events.sort(key=lambda item: item['when'], reverse=True)

    return render_template('view_student.html', student=student, activity_timeline=timeline_events[:50])


@students_bp.route('/students/bulk-actions', methods=['POST'])
@login_required
@role_required('admin', 'registrar', 'hod', 'finance')
def bulk_actions():
    selected_ids = request.form.getlist('selected_ids')
    action = (request.form.get('bulk_action') or '').strip()
    redirect_url = url_for(
        'students.student_list',
        search=request.form.get('search', ''),
        status=request.form.get('status', ''),
        department=request.form.get('department', ''),
        workflow=request.form.get('workflow', ''),
        sort=request.form.get('sort', 'newest'),
        per_page=request.form.get('per_page', '10'),
        include_deleted='1' if request.form.get('include_deleted') == '1' else '',
        page=request.form.get('page', '1'),
    )

    if not selected_ids:
        flash('Select at least one student for bulk action.', 'warning')
        return redirect(redirect_url)

    try:
        ids = [int(sid) for sid in selected_ids]
    except ValueError:
        flash('Invalid selection provided.', 'danger')
        return redirect(redirect_url)

    students = Student.query.filter(Student.id.in_(ids)).all()
    if not students:
        flash('No matching students found for selected IDs.', 'warning')
        return redirect(redirect_url)

    changed_count = 0
    reminder_message = (request.form.get('bulk_message') or '').strip()

    if action.startswith('stage:'):
        if current_user.role not in ['admin', 'registrar', 'hod']:
            flash('You are not authorized to bulk update workflow stages.', 'danger')
            return redirect(redirect_url)

        next_stage = action.split(':', 1)[1]
        if next_stage not in WORKFLOW_STAGES:
            flash('Invalid bulk stage selected.', 'danger')
            return redirect(redirect_url)

        for student in students:
            if student.deleted_at is not None:
                continue
            old_stage = student.workflow_stage or 'Applied'
            if old_stage == next_stage:
                continue
            student.workflow_stage = next_stage
            student.stage_updated_at = datetime.utcnow()
            db.session.add(StudentStageHistory(
                student_id=student.id,
                from_stage=old_stage,
                to_stage=next_stage,
                changed_by=current_user.id,
                notes='Bulk stage update',
            ))
            changed_count += 1

    elif action == 'archive':
        if current_user.role not in ['admin', 'registrar']:
            flash('You are not authorized to bulk archive students.', 'danger')
            return redirect(redirect_url)

        for student in students:
            if student.deleted_at is not None:
                continue
            student.deleted_at = datetime.utcnow()
            student.deleted_by = current_user.id
            student.status = 'Inactive'
            changed_count += 1

    elif action == 'restore':
        if current_user.role not in ['admin', 'registrar']:
            flash('You are not authorized to bulk restore students.', 'danger')
            return redirect(redirect_url)

        for student in students:
            if student.deleted_at is None:
                continue
            student.deleted_at = None
            student.deleted_by = None
            if student.status == 'Inactive':
                student.status = 'Active'
            changed_count += 1

    elif action in ['remind:email', 'remind:sms']:
        channel = action.split(':', 1)[1]
        for student in students:
            if student.deleted_at is not None:
                continue

            recipient = student.email if channel == 'email' else student.phone
            if not recipient:
                continue

            message = reminder_message or (
                f'Dear {student.full_name}, your outstanding balance is Leones {parse_money(student.finance_outstanding):.2f}. Please clear dues promptly.'
            )

            db.session.add(NotificationLog(
                student_id=student.id,
                channel=channel,
                recipient=recipient,
                message=message,
                status='queued',
                sent_at=datetime.utcnow(),
                sent_by=current_user.id,
            ))
            changed_count += 1

    else:
        flash('Please choose a valid bulk action.', 'warning')
        return redirect(redirect_url)

    if changed_count:
        db.session.commit()
        log_audit('bulk_action', 'student', metadata={'action': action, 'count': changed_count})
        flash(f'Bulk action applied to {changed_count} student(s).', 'success')
    else:
        flash('No records were changed by the selected bulk action.', 'info')

    return redirect(redirect_url)


@students_bp.route('/students/<int:student_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'registrar')
def edit_student(student_id):
    student = Student.query.filter(Student.deleted_at.is_(None), Student.id == student_id).first_or_404()

    if request.method == 'POST':
        try:
            finance_tuition_fee = parse_money(request.form.get('finance_tuition_fee'))
            finance_registration_fee = parse_money(request.form.get('finance_registration_fee'))
            finance_exam_fee = parse_money(request.form.get('finance_exam_fee'))
            finance_library_ict_fee = parse_money(request.form.get('finance_library_ict_fee'))
            finance_lab_practical_fee = parse_money(request.form.get('finance_lab_practical_fee'))
            finance_accommodation_fee = parse_money(request.form.get('finance_accommodation_fee'))
            finance_miscellaneous_fee = parse_money(request.form.get('finance_miscellaneous_fee'))
            finance_scholarship_discount = parse_money(request.form.get('finance_scholarship_discount'))
            finance_amount_paid = parse_money(request.form.get('finance_amount_paid'))
            finance_other_commitments = parse_money(request.form.get('finance_other_commitments'))
            finance_full_cost = calculate_full_cost({
                'finance_tuition_fee': finance_tuition_fee,
                'finance_registration_fee': finance_registration_fee,
                'finance_exam_fee': finance_exam_fee,
                'finance_library_ict_fee': finance_library_ict_fee,
                'finance_lab_practical_fee': finance_lab_practical_fee,
                'finance_accommodation_fee': finance_accommodation_fee,
                'finance_miscellaneous_fee': finance_miscellaneous_fee,
                'finance_scholarship_discount': finance_scholarship_discount,
            })

            student.first_name = request.form['first_name']
            student.middle_name = request.form.get('middle_name', '')
            student.last_name = request.form['last_name']
            student.date_of_birth = datetime.strptime(request.form['date_of_birth'], '%Y-%m-%d').date()
            student.gender = request.form['gender']
            student.nationality = request.form['nationality']
            student.national_id = request.form.get('national_id', '')
            student.marital_status = request.form.get('marital_status', '')
            student.religion = request.form.get('religion', '')
            student.blood_group = request.form.get('blood_group', '')
            student.disability = request.form.get('disability', '')
            student.email = request.form.get('email', '')
            student.phone = request.form['phone']
            student.alt_phone = request.form.get('alt_phone', '')
            student.address = request.form['address']
            student.city = request.form.get('city', '')
            student.state_province = request.form.get('state_province', '')
            student.postal_code = request.form.get('postal_code', '')
            student.country = request.form.get('country', '')
            student.programme = request.form.get('programme', '')
            student.department = request.form.get('department', '')
            student.intake_year = int(request.form.get('intake_year') or datetime.now().year)
            student.intake_semester = request.form.get('intake_semester', '')
            student.mode_of_study = request.form.get('mode_of_study', '')
            student.emergency_name = request.form.get('emergency_name', '')
            student.emergency_relationship = request.form.get('emergency_relationship', '')
            student.emergency_phone = request.form.get('emergency_phone', '')
            student.emergency_email = request.form.get('emergency_email', '')
            student.emergency_address = request.form.get('emergency_address', '')
            student.medical_conditions = request.form.get('medical_conditions', '')
            student.allergies = request.form.get('allergies', '')
            student.finance_tuition_fee = finance_tuition_fee
            student.finance_registration_fee = finance_registration_fee
            student.finance_exam_fee = finance_exam_fee
            student.finance_library_ict_fee = finance_library_ict_fee
            student.finance_lab_practical_fee = finance_lab_practical_fee
            student.finance_accommodation_fee = finance_accommodation_fee
            student.finance_miscellaneous_fee = finance_miscellaneous_fee
            student.finance_scholarship_discount = finance_scholarship_discount
            student.finance_amount_paid = finance_amount_paid
            student.finance_full_cost = finance_full_cost
            student.finance_other_commitments = finance_other_commitments
            recalculate_student_finance(student)
            student.status = request.form.get('status', 'Active')
            submitted_workflow = request.form.get('workflow_stage', student.workflow_stage or 'Applied')
            if submitted_workflow not in WORKFLOW_STAGES:
                submitted_workflow = student.workflow_stage or 'Applied'
            if submitted_workflow != (student.workflow_stage or 'Applied'):
                db.session.add(StudentStageHistory(
                    student_id=student.id,
                    from_stage=student.workflow_stage,
                    to_stage=submitted_workflow,
                    changed_by=current_user.id,
                    notes='Updated from student edit form',
                ))
                student.workflow_stage = submitted_workflow
                student.stage_updated_at = datetime.utcnow()

            if 'photo' in request.files:
                photo = request.files['photo']
                if photo and photo.filename and allowed_file(photo.filename):
                    ext = photo.filename.rsplit('.', 1)[1].lower()
                    filename = f"{uuid.uuid4().hex}.{ext}"
                    photo.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
                    student.photo_filename = filename

            db.session.commit()
            log_audit('update', 'student', entity_id=student.id, metadata={'student_id': student.student_id})
            flash('Student record updated successfully!', 'success')
            return redirect(url_for('students.view_student', student_id=student.id))
        except Exception as error:
            db.session.rollback()
            flash(f'Error: {str(error)}', 'danger')

    return render_template('edit_student.html', student=student)


@students_bp.route('/students/<int:student_id>/delete', methods=['POST'])
@login_required
@role_required('admin', 'registrar')
def delete_student(student_id):
    student = Student.query.get_or_404(student_id)
    student.deleted_at = datetime.utcnow()
    student.deleted_by = current_user.id
    student.status = 'Inactive'
    log_audit('soft_delete', 'student', entity_id=student.id, metadata={'student_id': student.student_id})
    db.session.commit()
    flash('Student record archived.', 'warning')
    return redirect(url_for('students.student_list'))


@students_bp.route('/students/<int:student_id>/restore', methods=['POST'])
@login_required
@role_required('admin', 'registrar')
def restore_student(student_id):
    student = Student.query.get_or_404(student_id)
    student.deleted_at = None
    student.deleted_by = None
    if student.status == 'Inactive':
        student.status = 'Active'
    log_audit('restore', 'student', entity_id=student.id, metadata={'student_id': student.student_id})
    db.session.commit()
    flash('Student record restored.', 'success')
    return redirect(url_for('students.student_list', include_deleted='1'))


@students_bp.route('/students/<int:student_id>/print')
@login_required
def print_student_profile(student_id):
    student = Student.query.filter(Student.deleted_at.is_(None), Student.id == student_id).first_or_404()
    return render_template('student_profile_print.html', student=student)


@students_bp.route('/students/<int:student_id>/finance-statement')
@login_required
def print_finance_statement(student_id):
    student = Student.query.filter(Student.deleted_at.is_(None), Student.id == student_id).first_or_404()
    return render_template('finance_statement_print.html', student=student)


@students_bp.route('/students/print')
@login_required
@role_required('admin', 'registrar', 'hod')
def print_students_list():
    search = request.args.get('search', '')
    status_filter = request.args.get('status', '')
    dept_filter = request.args.get('department', '')
    workflow_filter = request.args.get('workflow', '')
    sort_by = request.args.get('sort', 'newest')
    include_deleted = request.args.get('include_deleted', '') == '1'

    query = apply_student_filters(Student.query, search, status_filter, dept_filter, workflow_filter, include_deleted)
    students = query.order_by(get_sort_expression(sort_by)).all()

    return render_template(
        'students_print.html',
        students=students,
        search=search,
        status_filter=status_filter,
        dept_filter=dept_filter,
        workflow_filter=workflow_filter,
        include_deleted=include_deleted,
    )


@students_bp.route('/students/filters/save', methods=['POST'])
@login_required
def save_filter_preset():
    name = (request.form.get('preset_name') or '').strip()
    if not name:
        flash('Preset name is required.', 'warning')
        return redirect(url_for('students.student_list'))

    preset = SavedFilterPreset(
        user_id=current_user.id,
        name=name,
        search=request.form.get('search', ''),
        status=request.form.get('status', ''),
        department=request.form.get('department', ''),
        workflow=request.form.get('workflow', ''),
        sort=request.form.get('sort', 'newest'),
        include_deleted=request.form.get('include_deleted', '') == '1',
    )
    db.session.add(preset)
    db.session.commit()
    flash('Filter preset saved.', 'success')
    return redirect(url_for('students.student_list'))


@students_bp.route('/students/filters/<int:preset_id>/delete', methods=['POST'])
@login_required
def delete_filter_preset(preset_id):
    preset = SavedFilterPreset.query.filter_by(id=preset_id, user_id=current_user.id).first_or_404()
    db.session.delete(preset)
    db.session.commit()
    flash('Filter preset deleted.', 'info')
    return redirect(url_for('students.student_list'))


@students_bp.route('/students/<int:student_id>/stage', methods=['POST'])
@login_required
@role_required('admin', 'registrar', 'hod')
def update_student_stage(student_id):
    student = Student.query.filter(Student.deleted_at.is_(None), Student.id == student_id).first_or_404()
    next_stage = (request.form.get('next_stage') or '').strip()
    if next_stage not in WORKFLOW_STAGES:
        flash('Invalid workflow stage selected.', 'warning')
        return redirect(url_for('students.view_student', student_id=student.id))

    if next_stage == (student.workflow_stage or 'Applied'):
        flash('Student is already in that stage.', 'info')
        return redirect(url_for('students.view_student', student_id=student.id))

    old_stage = student.workflow_stage or 'Applied'
    student.workflow_stage = next_stage
    student.stage_updated_at = datetime.utcnow()

    db.session.add(StudentStageHistory(
        student_id=student.id,
        from_stage=old_stage,
        to_stage=next_stage,
        changed_by=current_user.id,
        notes=(request.form.get('notes') or '').strip()[:255],
    ))
    db.session.commit()
    log_audit('stage_transition', 'student', entity_id=student.id, metadata={'from': old_stage, 'to': next_stage})
    flash('Workflow stage updated successfully.', 'success')
    return redirect(url_for('students.view_student', student_id=student.id))


@students_bp.route('/students/<int:student_id>/approve', methods=['POST'])
@login_required
@role_required('admin', 'hod')
def approve_student(student_id):
    student = Student.query.filter(Student.deleted_at.is_(None), Student.id == student_id).first_or_404()
    old_stage = student.workflow_stage or 'Applied'
    student.workflow_stage = 'Approved'
    student.stage_updated_at = datetime.utcnow()
    student.approved_by = current_user.id
    student.approved_at = datetime.utcnow()
    if student.status in ['Inactive', 'Suspended']:
        student.status = 'Active'

    db.session.add(StudentStageHistory(
        student_id=student.id,
        from_stage=old_stage,
        to_stage='Approved',
        changed_by=current_user.id,
        notes='Approved by authorized officer',
    ))
    db.session.commit()
    log_audit('approve', 'student', entity_id=student.id, metadata={'from': old_stage, 'to': 'Approved'})
    flash('Student approved successfully.', 'success')
    return redirect(url_for('students.view_student', student_id=student.id))


@students_bp.route('/students/<int:student_id>/payments/add', methods=['POST'])
@login_required
@role_required('admin', 'registrar', 'finance', 'hod')
def add_student_payment(student_id):
    student = Student.query.filter(Student.deleted_at.is_(None), Student.id == student_id).first_or_404()
    amount = parse_money(request.form.get('amount'))
    if amount <= 0:
        flash('Payment amount must be greater than zero.', 'warning')
        return redirect(url_for('students.view_student', student_id=student.id))

    payment = StudentPayment(
        student_id=student.id,
        receipt_number=generate_receipt_number(),
        amount=amount,
        payment_method=(request.form.get('payment_method') or 'Cash')[:40],
        notes=(request.form.get('notes') or '').strip()[:255],
        paid_at=datetime.utcnow(),
        recorded_by=current_user.id,
    )
    db.session.add(payment)
    recalculate_student_finance(student)

    due_installment = InstallmentPlan.query.filter_by(student_id=student.id, is_paid=False).order_by(InstallmentPlan.due_date.asc()).first()
    if due_installment and amount >= (due_installment.amount or 0):
        due_installment.is_paid = True
        due_installment.paid_at = datetime.utcnow()

    db.session.commit()
    log_audit('record_payment', 'student', entity_id=student.id, metadata={'receipt': payment.receipt_number, 'amount': amount})
    flash(f'Payment recorded. Receipt: {payment.receipt_number}', 'success')
    return redirect(url_for('students.view_student', student_id=student.id, tab='finance'))


@students_bp.route('/students/<int:student_id>/installments/add', methods=['POST'])
@login_required
@role_required('admin', 'registrar', 'finance', 'hod')
def add_installment(student_id):
    student = Student.query.filter(Student.deleted_at.is_(None), Student.id == student_id).first_or_404()
    amount = parse_money(request.form.get('amount'))
    due_date_raw = (request.form.get('due_date') or '').strip()

    if amount <= 0 or not due_date_raw:
        flash('Installment due date and amount are required.', 'warning')
        return redirect(url_for('students.view_student', student_id=student.id, tab='finance'))

    try:
        due_date = datetime.strptime(due_date_raw, '%Y-%m-%d').date()
    except ValueError:
        flash('Installment date format must be YYYY-MM-DD.', 'warning')
        return redirect(url_for('students.view_student', student_id=student.id, tab='finance'))

    plan = InstallmentPlan(
        student_id=student.id,
        due_date=due_date,
        amount=amount,
        notes=(request.form.get('notes') or '').strip()[:255],
    )
    db.session.add(plan)
    db.session.commit()
    log_audit('create_installment', 'student', entity_id=student.id, metadata={'due_date': due_date_raw, 'amount': amount})
    flash('Installment plan entry added.', 'success')
    return redirect(url_for('students.view_student', student_id=student.id, tab='finance'))


@students_bp.route('/students/<int:student_id>/reminder/send', methods=['POST'])
@login_required
@role_required('admin', 'registrar', 'finance', 'hod')
def send_due_reminder(student_id):
    student = Student.query.filter(Student.deleted_at.is_(None), Student.id == student_id).first_or_404()
    channel = (request.form.get('channel') or 'email').lower()
    if channel not in ['email', 'sms']:
        channel = 'email'

    recipient = student.email if channel == 'email' else student.phone
    if not recipient:
        flash(f'No {channel.upper()} recipient found on student profile.', 'warning')
        return redirect(url_for('students.view_student', student_id=student.id, tab='finance'))

    message = request.form.get(
        'message',
        f'Dear {student.full_name}, your outstanding balance is Leones {student.finance_outstanding or 0:.2f}. Please clear dues promptly.'
    )

    notification = NotificationLog(
        student_id=student.id,
        channel=channel,
        recipient=recipient,
        message=message,
        status='sent',
        sent_at=datetime.utcnow(),
        sent_by=current_user.id,
    )
    db.session.add(notification)
    db.session.commit()

    log_audit('send_reminder', 'student', entity_id=student.id, metadata={'channel': channel, 'recipient': recipient})
    flash(f'{channel.upper()} reminder logged and marked as sent.', 'success')
    return redirect(url_for('students.view_student', student_id=student.id, tab='finance'))


@students_bp.route('/students/recycle-bin')
@login_required
@role_required('admin', 'registrar', 'hod')
def recycle_bin():
    archived_students = Student.query.filter(Student.deleted_at.isnot(None)).order_by(Student.deleted_at.desc()).all()
    return render_template('students_recycle_bin.html', students=archived_students)


@students_bp.route('/governance/audit-logs')
@login_required
@role_required('admin', 'hod')
def audit_logs_view():
    page = max(int(request.args.get('page', 1) or 1), 1)
    pagination = AuditLog.query.order_by(AuditLog.created_at.desc()).paginate(page=page, per_page=30, error_out=False)
    return render_template('audit_logs.html', logs=pagination.items, pagination=pagination)


@students_bp.route('/reports')
@login_required
@role_required('admin', 'registrar', 'hod', 'finance')
def reports_dashboard():
    active_students = Student.query.filter(Student.deleted_at.is_(None)).all()
    total_students = len(active_students)
    total_outstanding = round(sum(parse_money(s.finance_outstanding) for s in active_students), 2)
    total_collected = round(sum(parse_money(s.finance_amount_paid) for s in active_students), 2)
    defaulters = [s for s in active_students if parse_money(s.finance_outstanding) > 0]

    aging_buckets = {'0-30': 0, '31-60': 0, '61-90': 0, '90+': 0}
    today = date.today()
    for item in InstallmentPlan.query.filter_by(is_paid=False).all():
        days_overdue = (today - item.due_date).days
        if days_overdue <= 30:
            aging_buckets['0-30'] += 1
        elif days_overdue <= 60:
            aging_buckets['31-60'] += 1
        elif days_overdue <= 90:
            aging_buckets['61-90'] += 1
        else:
            aging_buckets['90+'] += 1

    department_snapshot = db.session.query(
        Student.department,
        db.func.count(Student.id),
        db.func.sum(Student.finance_outstanding),
    ).filter(Student.deleted_at.is_(None)).group_by(Student.department).all()

    monthly_counter = Counter(s.created_at.strftime('%Y-%m') for s in active_students if s.created_at)
    monthly_rows = sorted(monthly_counter.items(), key=lambda item: item[0])

    return render_template(
        'reports.html',
        total_students=total_students,
        total_outstanding=total_outstanding,
        total_collected=total_collected,
        defaulters=defaulters,
        aging_buckets=aging_buckets,
        department_snapshot=department_snapshot,
        monthly_rows=monthly_rows,
    )


@students_bp.route('/reports/defaulters.csv')
@login_required
@role_required('admin', 'registrar', 'hod', 'finance')
def export_defaulters_csv():
    rows = Student.query.filter(Student.deleted_at.is_(None), Student.finance_outstanding > 0).order_by(Student.finance_outstanding.desc()).all()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Student ID', 'Name', 'Programme', 'Department', 'Outstanding', 'Phone', 'Email'])
    for student in rows:
        writer.writerow([
            student.student_id,
            student.full_name,
            student.programme or '',
            student.department or '',
            f"{parse_money(student.finance_outstanding):.2f}",
            student.phone or '',
            student.email or '',
        ])

    response = Response(output.getvalue(), mimetype='text/csv')
    response.headers['Content-Disposition'] = f"attachment; filename=defaulters_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return response
