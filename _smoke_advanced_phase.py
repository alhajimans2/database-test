import os
from pathlib import Path
from io import BytesIO

from werkzeug.security import generate_password_hash

from titapp import create_app
from titapp.extensions import db
from titapp.models import User, Student, AuditLog, StudentPayment, InstallmentPlan, NotificationLog


smoke_db = Path("smoke_test.db")
if smoke_db.exists():
    smoke_db.unlink()
os.environ["DATABASE_URL"] = "sqlite:///smoke_test.db"


app = create_app()
app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

with app.app_context():
    db.create_all()

    user = User.query.filter_by(username="smoke_admin").first()
    if not user:
        user = User(
            full_name="Smoke Admin",
            username="smoke_admin",
            email="smoke_admin@example.com",
            role="admin",
            password_hash=generate_password_hash("pass1234"),
        )
        db.session.add(user)
        db.session.commit()

    viewer = User.query.filter_by(username="smoke_viewer").first()
    if not viewer:
        viewer = User(
            full_name="Smoke Viewer",
            username="smoke_viewer",
            email="smoke_viewer@example.com",
            role="viewer",
            password_hash=generate_password_hash("pass1234"),
        )
        db.session.add(viewer)
        db.session.commit()

    client = app.test_client()

    login_response = client.post(
        "/login",
        data={"username": "smoke_admin", "password": "pass1234"},
        follow_redirects=True,
    )
    assert login_response.status_code == 200, "Login failed"

    health_response = client.get("/healthz")
    assert health_response.status_code == 200, "Health endpoint failed"
    assert health_response.headers.get("X-Request-ID"), "X-Request-ID header missing"

    students_response = client.get("/students")
    assert students_response.status_code == 200, "Students list failed"

    reports_response = client.get("/reports")
    assert reports_response.status_code == 200, "Reports dashboard failed"

    recycle_bin_response = client.get("/students/recycle-bin")
    assert recycle_bin_response.status_code == 200, "Recycle bin page failed"

    audit_page_response = client.get("/governance/audit-logs")
    assert audit_page_response.status_code == 200, "Audit logs page failed"

    import_page_response = client.get("/students/import")
    assert import_page_response.status_code == 200, "Import page failed"

    export_response = client.get("/students/export")
    assert export_response.status_code == 200, "Export CSV failed"

    csv_data = "first_name,last_name,date_of_birth,gender,nationality,phone,address\nJane,Doe,2001-05-10,Female,Zimbabwe,+263771234567,Harare\n"
    import_submit_response = client.post(
        "/students/import",
        data={"csv_file": (BytesIO(csv_data.encode("utf-8")), "students.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert import_submit_response.status_code == 200, "Import CSV submit failed"

    imported_student = Student.query.filter_by(first_name="Jane", last_name="Doe").first()
    assert imported_student is not None, "Imported student not found"

    student = Student.query.filter_by(deleted_at=None).first()
    if student:
        stage_response = client.post(
            f"/students/{student.id}/stage",
            data={"next_stage": "Screening", "notes": "Smoke transition"},
            follow_redirects=True,
        )
        assert stage_response.status_code == 200, "Workflow stage transition failed"

        payment_response = client.post(
            f"/students/{student.id}/payments/add",
            data={"amount": "120", "payment_method": "Cash", "notes": "Smoke payment"},
            follow_redirects=True,
        )
        assert payment_response.status_code == 200, "Payment recording failed"

        installment_response = client.post(
            f"/students/{student.id}/installments/add",
            data={"due_date": "2026-12-31", "amount": "80", "notes": "Smoke installment"},
            follow_redirects=True,
        )
        assert installment_response.status_code == 200, "Installment creation failed"

        reminder_response = client.post(
            f"/students/{student.id}/reminder/send",
            data={"channel": "sms", "message": "Smoke reminder"},
            follow_redirects=True,
        )
        assert reminder_response.status_code == 200, "Reminder dispatch failed"

        delete_response = client.post(f"/students/{student.id}/delete", follow_redirects=True)
        assert delete_response.status_code == 200, "Soft delete failed"
        db.session.refresh(student)
        assert student.deleted_at is not None, "deleted_at not set"

        restore_response = client.post(f"/students/{student.id}/restore", follow_redirects=True)
        assert restore_response.status_code == 200, "Restore failed"

    logout_response = client.get("/logout", follow_redirects=True)
    assert logout_response.status_code == 200, "Logout failed"

    viewer_login_response = client.post(
        "/login",
        data={"username": "smoke_viewer", "password": "pass1234"},
        follow_redirects=True,
    )
    assert viewer_login_response.status_code == 200, "Viewer login failed"

    viewer_import_response = client.get("/students/import")
    assert viewer_import_response.status_code == 403, "Role permission failed for import"

    viewer_export_response = client.get("/students/export")
    assert viewer_export_response.status_code == 403, "Role permission failed for export"

    audit_rows = AuditLog.query.all()
    assert len(audit_rows) > 0, "No audit logs were created"

    assert StudentPayment.query.count() > 0, "No payment ledger rows were created"
    assert InstallmentPlan.query.count() > 0, "No installment rows were created"
    assert NotificationLog.query.count() > 0, "No reminder logs were created"

    app_js = Path("static/js/app.js").read_text(encoding="utf-8")
    assert "setupDraftAutosave" in app_js, "Draft autosave UX hook missing"

print("ADVANCED_PHASE_SMOKE_OK")
