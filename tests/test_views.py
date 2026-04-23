import json
import pytest
from django.urls import reverse
from django.contrib.messages import get_messages


@pytest.mark.django_db
class TestLoginView:
    def test_login_GET(self, client):
        response = client.get(reverse("login"))
        assert response.status_code == 200

    def test_login_redirects_authenticated_user(self, authenticated_client):
        response = authenticated_client.get(reverse("login"))
        assert response.status_code == 302

    def test_login_success(self, client, test_user):
        response = client.post(
            reverse("login"),
            {"username": "testuser", "password": "testpass123"},
        )
        assert response.status_code == 302
        assert response.url == "/dashboard/"

    def test_login_failure(self, client):
        response = client.post(
            reverse("login"),
            {"username": "wronguser", "password": "wrongpass"},
        )
        assert response.status_code == 200
        assert "Invalid username or password" in str(response.content)


@pytest.mark.django_db
class TestRegisterView:
    def test_register_GET(self, client):
        response = client.get(reverse("register"))
        assert response.status_code == 200

    def test_register_redirects_authenticated_user(self, authenticated_client):
        response = authenticated_client.get(reverse("register"))
        assert response.status_code == 302

    def test_register_success(self, client):
        response = client.post(
            reverse("register"),
            {
                "username": "newuser",
                "email": "newuser@test.com",
                "password1": "SecurePassword123!",
                "password2": "SecurePassword123!",
            },
        )
        assert response.status_code == 302
        assert response.url == "/login/"

    def test_register_password_mismatch(self, client):
        response = client.post(
            reverse("register"),
            {
                "username": "newuser",
                "email": "newuser@test.com",
                "password1": "Password123!",
                "password2": "DifferentPassword!",
            },
        )
        assert response.status_code == 200
        assert "password2" in str(response.content)


@pytest.mark.django_db
class TestLogoutView:
    def test_logout_redirects(self, authenticated_client):
        response = authenticated_client.post(reverse("logout"))
        assert response.status_code == 302
        assert response.url == "/login/"


@pytest.mark.django_db
class TestDashboardView:
    def test_dashboard_requires_login(self, client):
        response = client.get(reverse("dashboard"))
        assert response.status_code == 302

    def test_dashboard_shows_user_files(self, authenticated_client, test_uploaded_file):
        response = authenticated_client.get(reverse("dashboard"))
        assert response.status_code == 200
        assert "files" in response.context

    def test_dashboard_admin_sees_all_files(self, admin_client, test_uploaded_file):
        response = admin_client.get(reverse("dashboard"))
        assert response.status_code == 200

    def test_dashboard_counts(self, authenticated_client, test_uploaded_file):
        response = authenticated_client.get(reverse("dashboard"))
        assert "processed_count" in response.context
        assert "pending_count" in response.context


@pytest.mark.django_db
class TestAdminDashboardView:
    def test_admin_dashboard_requires_login(self, client):
        response = client.get(reverse("admin_dashboard"))
        assert response.status_code == 302

    def test_admin_dashboard_shows_stats(self, admin_client, test_template, test_user):
        response = admin_client.get(reverse("admin_dashboard"))
        assert response.status_code == 200
        assert "domain_count" in response.context
        assert "rule_count" in response.context
        assert "files_processed" in response.context
        assert "user_count" in response.context


@pytest.mark.django_db
class TestManageTemplatesView:
    def test_manage_templates_requires_login(self, client):
        response = client.get(reverse("manage_templates"))
        assert response.status_code == 302

    def test_manage_templates_shows_templates(
        self, authenticated_client, test_template
    ):
        response = authenticated_client.get(reverse("manage_templates"))
        assert response.status_code == 200
        assert "templates" in response.context


@pytest.mark.django_db
class TestUploadFileView:
    def test_upload_requires_login(self, client):
        response = client.get(reverse("upload_file"))
        assert response.status_code == 302

    def test_upload_GET(self, authenticated_client, test_template):
        response = authenticated_client.get(reverse("upload_file"))
        assert response.status_code == 200
        assert "domains" in response.context

    def test_upload_POST_no_domain(self, authenticated_client):
        response = authenticated_client.post(reverse("upload_file"), {"file": ""})
        assert response.status_code == 302
        messages = list(get_messages(response.wsgi_request))
        assert any("select a domain" in str(m) for m in messages)

    def test_upload_POST_no_files(self, authenticated_client, test_template):
        response = authenticated_client.post(
            reverse("upload_file"),
            {"domain": test_template.domain_type},
        )
        assert response.status_code == 302


@pytest.mark.django_db
class TestUploadHistoryView:
    def test_history_requires_login(self, client):
        response = client.get(reverse("upload_history"))
        assert response.status_code == 302

    def test_history_user_sees_own_files(
        self, authenticated_client, test_uploaded_file
    ):
        response = authenticated_client.get(reverse("upload_history"))
        assert response.status_code == 200
        assert "files" in response.context

    def test_history_admin_sees_all(self, admin_client, test_uploaded_file):
        response = admin_client.get(reverse("upload_history"))
        assert response.status_code == 200


@pytest.mark.django_db
class TestValidationReportView:
    def test_report_requires_login(self, client):
        response = client.get(reverse("validation_report", args=[1]))
        assert response.status_code == 302

    def test_report_shows_file(self, authenticated_client, test_uploaded_file):
        response = authenticated_client.get(
            reverse("validation_report", args=[test_uploaded_file.id])
        )
        assert response.status_code == 200

    def test_report_404_for_other_user(
        self, authenticated_client, test_uploaded_file, test_user, db
    ):
        from django.contrib.auth.models import User

        other_user = User.objects.create_user(username="other", password="pass123")
        other_file = test_uploaded_file
        other_file.user = other_user
        other_file.save()
        response = authenticated_client.get(
            reverse("validation_report", args=[other_file.id])
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestAiExplainView:
    def test_ai_explain_requires_login(self, client):
        response = client.post(reverse("ai_explain"), {"result_id": 1})
        assert response.status_code == 302

    def test_ai_explain_returns_json(
        self, authenticated_client, test_validation_result, remove_api_key
    ):
        response = authenticated_client.post(
            reverse("ai_explain"),
            {"result_id": test_validation_result.id},
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.json()
        assert "explanation" in data
        assert len(data["explanation"]) > 0

    def test_ai_explain_invalid_result(self, authenticated_client):
        response = authenticated_client.post(
            reverse("ai_explain"),
            {"result_id": 99999},
            content_type="application/json",
        )
        assert response.status_code == 404

    def test_ai_explain_get_not_allowed(self, authenticated_client):
        response = authenticated_client.get(reverse("ai_explain"))
        assert response.status_code == 405

    def test_ai_explain_invalid_json(self, authenticated_client):
        response = authenticated_client.post(
            reverse("ai_explain"),
            data=b"not valid json",
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_ai_explain_missing_result_id(self, authenticated_client):
        response = authenticated_client.post(
            reverse("ai_explain"),
            json.dumps({}),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_ai_explain_with_formula(
        self,
        authenticated_client,
        test_validation_result,
        test_formula_rule,
        remove_api_key,
    ):
        response = authenticated_client.post(
            reverse("ai_explain"),
            json.dumps({"result_id": test_validation_result.id}),
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.json()
        assert "explanation" in data
        assert "ai_used" in data


@pytest.mark.django_db
class TestDownloadExcelView:
    def test_download_requires_login(self, client):
        response = client.get(reverse("download_excel", args=[1]))
        assert response.status_code == 302

    def test_download_own_file(
        self, authenticated_client, test_uploaded_file_with_file
    ):
        response = authenticated_client.get(
            reverse("download_excel", args=[test_uploaded_file_with_file.id])
        )
        assert response.status_code == 200
        assert (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            in response["Content-Type"]
        )

    def test_download_rejects_pdf(
        self, authenticated_client, test_user, test_template, db
    ):
        from django.core.files.uploadedfile import SimpleUploadedFile

        pdf_file = SimpleUploadedFile(
            "test.pdf", b"pdf content", content_type="application/pdf"
        )
        from automation.models import UploadedFile

        upl = UploadedFile.objects.create(
            user=test_user, template=test_template, file=pdf_file, status="Completed"
        )
        response = authenticated_client.get(reverse("download_excel", args=[upl.id]))
        assert response.status_code == 200
        assert b"Download not available" in response.content


@pytest.mark.django_db
class TestPreviewExcelView:
    def test_preview_requires_login(self, client):
        response = client.get(reverse("preview_excel", args=[1]))
        assert response.status_code == 302

    def test_preview_returns_json(
        self, authenticated_client, test_uploaded_file_with_file
    ):
        response = authenticated_client.get(
            reverse("preview_excel", args=[test_uploaded_file_with_file.id])
        )
        assert response.status_code == 200
        data = response.json()
        assert "table" in data


@pytest.mark.django_db
class TestWorkbookListView:
    def test_workbook_list_requires_login(self, client):
        response = client.get(reverse("workbook_list"))
        assert response.status_code == 302

    def test_workbook_list_shows_files(self, authenticated_client, test_uploaded_file):
        response = authenticated_client.get(reverse("workbook_list"))
        assert response.status_code == 200
        assert "original_files" in response.context


@pytest.mark.django_db
class TestWorkbookEditorView:
    def test_workbook_editor_requires_login(self, client):
        response = client.get(reverse("workbook_editor", args=[1]))
        assert response.status_code == 302

    def test_workbook_editor_loads_file(
        self, authenticated_client, test_uploaded_file_with_file
    ):
        response = authenticated_client.get(
            reverse("workbook_editor", args=[test_uploaded_file_with_file.id])
        )
        assert response.status_code == 200
        assert "file" in response.context

    def test_workbook_editor_404_for_other_user(
        self, authenticated_client, test_user, test_template, db
    ):
        from django.contrib.auth.models import User

        other_user = User.objects.create_user(username="other2", password="pass123")
        from django.core.files.uploadedfile import SimpleUploadedFile

        csv_file = SimpleUploadedFile(
            "test.csv", b"Name,Score\nAlice,85\n", content_type="text/csv"
        )
        from automation.models import UploadedFile

        upl = UploadedFile.objects.create(
            user=other_user, template=test_template, file=csv_file, status="Completed"
        )
        response = authenticated_client.get(reverse("workbook_editor", args=[upl.id]))
        assert response.status_code == 404


@pytest.mark.django_db
class TestSaveWorkbookData:
    def test_save_requires_login(self, client):
        response = client.post(reverse("save_workbook", args=[1]))
        assert response.status_code == 302

    def test_save_non_post_returns_400(self, authenticated_client, test_uploaded_file):
        response = authenticated_client.get(
            reverse("save_workbook", args=[test_uploaded_file.id])
        )
        assert response.status_code == 400

    def test_save_valid_data(self, authenticated_client, test_uploaded_file):
        data = {
            "headers": ["Name", "Score"],
            "rows": [
                [{"value": "Alice"}, {"value": 85}],
                [{"value": "Bob"}, {"value": 90}],
            ],
            "mappings": {},
        }
        response = authenticated_client.post(
            reverse("save_workbook", args=[test_uploaded_file.id]),
            data=json.dumps(data),
            content_type="application/json",
        )
        assert response.status_code == 200
        result = response.json()
        assert result.get("status") == "success"
        assert "new_file_id" in result

    def test_save_duplicate_headers_renamed(
        self, authenticated_client, test_uploaded_file
    ):
        data = {
            "headers": ["Name", "Name", "Score"],
            "rows": [
                [{"value": "Alice"}, {"value": "Alice"}, {"value": 85}],
            ],
            "mappings": {},
        }
        response = authenticated_client.post(
            reverse("save_workbook", args=[test_uploaded_file.id]),
            data=json.dumps(data),
            content_type="application/json",
        )
        assert response.status_code == 200
        result = response.json()
        assert result.get("status") == "success"


@pytest.mark.django_db
class TestAccessControl:
    def test_user_cannot_access_others_files_report(
        self, authenticated_client, test_user, test_template, db
    ):
        from django.contrib.auth.models import User

        other = User.objects.create_user(username="other3", password="pass123")
        from django.core.files.uploadedfile import SimpleUploadedFile

        csv_file = SimpleUploadedFile(
            "test.csv", b"Name\nAlice\n", content_type="text/csv"
        )
        from automation.models import UploadedFile

        upl = UploadedFile.objects.create(
            user=other, template=test_template, file=csv_file, status="Completed"
        )
        response = authenticated_client.get(reverse("validation_report", args=[upl.id]))
        assert response.status_code == 404

    def test_user_cannot_access_others_files_download(
        self, authenticated_client, test_user, test_template, db
    ):
        from django.contrib.auth.models import User

        other = User.objects.create_user(username="other4", password="pass123")
        from django.core.files.uploadedfile import SimpleUploadedFile

        csv_file = SimpleUploadedFile(
            "test.csv", b"Name\nAlice\n", content_type="text/csv"
        )
        from automation.models import UploadedFile

        upl = UploadedFile.objects.create(
            user=other, template=test_template, file=csv_file, status="Completed"
        )
        response = authenticated_client.get(reverse("download_excel", args=[upl.id]))
        assert response.status_code == 404

    def test_admin_can_access_any_file(
        self, admin_client, test_user, test_template, db
    ):
        from django.core.files.uploadedfile import SimpleUploadedFile

        csv_file = SimpleUploadedFile(
            "test.csv", b"Name\nAlice\n", content_type="text/csv"
        )
        from automation.models import UploadedFile

        upl = UploadedFile.objects.create(
            user=test_user, template=test_template, file=csv_file, status="Completed"
        )
        response = admin_client.get(reverse("validation_report", args=[upl.id]))
        assert response.status_code == 200


@pytest.mark.django_db
class TestAuditLogsView:
    def test_audit_logs_requires_login(self, client):
        response = client.get(reverse("audit_logs"))
        assert response.status_code == 302

    def test_audit_logs_requires_admin(self, authenticated_client):
        response = authenticated_client.get(reverse("audit_logs"))
        assert response.status_code == 302

    def test_audit_logs_accessible_by_admin(self, admin_client):
        response = admin_client.get(reverse("audit_logs"))
        assert response.status_code == 200
        assert "logs" in response.context
        assert "action_types" in response.context

    def test_audit_logs_shows_logs(self, admin_client, test_audit_log):
        response = admin_client.get(reverse("audit_logs"))
        assert response.status_code == 200
        assert "logs" in response.context

    def test_audit_logs_filter_by_user(self, admin_client, test_audit_log, db):
        from django.contrib.auth.models import User
        user2 = User.objects.create_user(username="otheruser", password="pass123")
        from automation.models import AuditLog
        AuditLog.objects.create(user=user2, action_type="Login", details="Logged in")
        response = admin_client.get(reverse("audit_logs") + "?user=testuser")
        assert response.status_code == 200
        assert all(
            log.user.username == "testuser" for log in response.context["logs"]
        )

    def test_audit_logs_filter_by_action_type(self, admin_client, test_audit_log, db):
        from automation.models import AuditLog
        AuditLog.objects.create(
            user=test_audit_log.user,
            action_type="Login",
            details="User logged in",
        )
        response = admin_client.get(
            reverse("audit_logs") + "?action_type=Login"
        )
        assert response.status_code == 200
        assert all(
            log.action_type == "Login" for log in response.context["logs"]
        )

    def test_audit_logs_search(self, admin_client, test_audit_log):
        response = admin_client.get(
            reverse("audit_logs") + "?search=successfully"
        )
        assert response.status_code == 200
        assert len(response.context["logs"]) > 0

    def test_audit_logs_pagination(self, admin_client, test_admin, db):
        from django.contrib.auth.models import User
        user = User.objects.get(username="admin")
        from automation.models import AuditLog
        for i in range(25):
            AuditLog.objects.create(
                user=user,
                action_type="Test Action",
                details=f"Test log entry {i}",
            )
        response = admin_client.get(reverse("audit_logs"))
        assert response.status_code == 200
        assert len(response.context["logs"]) == 20
        assert response.context["logs"].has_other_pages

    def test_audit_logs_pagination_page2(self, admin_client, test_admin, db):
        from django.contrib.auth.models import User
        user = User.objects.get(username="admin")
        from automation.models import AuditLog
        for i in range(25):
            AuditLog.objects.create(
                user=user,
                action_type="Test Action",
                details=f"Test log entry {i}",
            )
        response = admin_client.get(reverse("audit_logs") + "?page=2")
        assert response.status_code == 200
        assert len(response.context["logs"]) == 5

    def test_audit_logs_empty_state(self, admin_client, db):
        response = admin_client.get(reverse("audit_logs"))
        assert response.status_code == 200
        assert len(response.context["logs"]) == 0
