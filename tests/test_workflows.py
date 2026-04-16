import pytest
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from automation.models import (
    UploadedFile,
    ValidationResult,
    DomainTemplate,
)
from automation.utils import calculate_quality_score, validate_excel_data


@pytest.mark.django_db
class TestFileUploadWorkflow:
    def test_upload_csv_success(
        self, authenticated_client, test_user, test_template, db
    ):
        csv_file = SimpleUploadedFile(
            "data.csv", b"Name,Score\nAlice,85\nBob,90\n", content_type="text/csv"
        )
        response = authenticated_client.post(
            reverse("upload_file"),
            {"domain": test_template.domain_type, "file": csv_file},
        )
        assert response.status_code == 302

    def test_upload_xlsx_success(
        self, authenticated_client, test_user, test_template, xlsx_file, db
    ):
        response = authenticated_client.post(
            reverse("upload_file"),
            {"domain": test_template.domain_type, "file": xlsx_file},
        )
        assert response.status_code == 302

    def test_upload_unsupported_file_type(
        self, authenticated_client, test_user, test_template, db
    ):
        unsupported_file = SimpleUploadedFile(
            "data.txt", b"some content", content_type="text/plain"
        )
        response = authenticated_client.post(
            reverse("upload_file"),
            {"domain": test_template.domain_type, "file": unsupported_file},
        )
        assert response.status_code == 302

    def test_upload_no_domain_selected(self, authenticated_client):
        csv_file = SimpleUploadedFile(
            "data.csv", b"Name,Score\nAlice,85\n", content_type="text/csv"
        )
        response = authenticated_client.post(reverse("upload_file"), {"file": csv_file})
        assert response.status_code == 302

    def test_upload_no_file_selected(self, authenticated_client, test_template):
        response = authenticated_client.post(
            reverse("upload_file"),
            {"domain": test_template.domain_type},
        )
        assert response.status_code == 302

    def test_upload_multiple_files(
        self, authenticated_client, test_user, test_template, db
    ):
        csv_file1 = SimpleUploadedFile(
            "data1.csv", b"Name,Score\nAlice,85\n", content_type="text/csv"
        )
        csv_file2 = SimpleUploadedFile(
            "data2.csv", b"Name,Score\nBob,90\n", content_type="text/csv"
        )
        response = authenticated_client.post(
            reverse("upload_file"),
            {"domain": test_template.domain_type, "file": [csv_file1, csv_file2]},
        )
        assert response.status_code == 302


@pytest.mark.django_db
class TestValidationWorkflow:
    def test_validation_creates_results_on_failure(
        self, test_user, test_template, test_validation_rule, db
    ):
        csv_file = SimpleUploadedFile(
            "data.csv", b"Name,Score\nAlice,150\n", content_type="text/csv"
        )
        upl = UploadedFile.objects.create(
            user=test_user, template=test_template, file=csv_file, status="Completed"
        )
        result = validate_excel_data(upl)
        assert result is True
        results = ValidationResult.objects.filter(file=upl, is_valid=False)
        assert results.count() > 0

    def test_validation_no_errors_when_valid(
        self, test_user, test_template, test_validation_rule, db
    ):
        csv_file = SimpleUploadedFile(
            "valid.csv",
            b"Name,Score\nAlice,50\n",
            content_type="text/csv",
        )
        upl = UploadedFile.objects.create(
            user=test_user, template=test_template, file=csv_file, status="Completed"
        )
        validate_excel_data(upl)
        results = ValidationResult.objects.filter(file=upl, is_valid=False)
        assert results.count() == 0

    def test_validation_boundary_check_lower(
        self, test_user, test_template, test_validation_rule, db
    ):
        csv_file = SimpleUploadedFile(
            "invalid.csv",
            b"Name,Score\nAlice,-10\n",
            content_type="text/csv",
        )
        upl = UploadedFile.objects.create(
            user=test_user, template=test_template, file=csv_file, status="Completed"
        )
        validate_excel_data(upl)
        results = ValidationResult.objects.filter(file=upl, is_valid=False)
        assert results.count() > 0
        assert "Score" in results.first().column_name

    def test_validation_boundary_check_upper(
        self, test_user, test_template, test_validation_rule, db
    ):
        csv_file = SimpleUploadedFile(
            "invalid.csv",
            b"Name,Score\nAlice,150\n",
            content_type="text/csv",
        )
        upl = UploadedFile.objects.create(
            user=test_user, template=test_template, file=csv_file, status="Completed"
        )
        validate_excel_data(upl)
        results = ValidationResult.objects.filter(file=upl, is_valid=False)
        assert results.count() > 0

    def test_formula_validation_detects_mismatch(
        self, test_user, test_template, test_formula_rule, db
    ):
        csv_file = SimpleUploadedFile(
            "invalid_formula.csv",
            b"Name,Score,Bonus,Total\nAlice,80,10,50\n",
            content_type="text/csv",
        )
        upl = UploadedFile.objects.create(
            user=test_user, template=test_template, file=csv_file, status="Completed"
        )
        validate_excel_data(upl)
        results = ValidationResult.objects.filter(
            file=upl, column_name__iexact="Total", is_valid=False
        )
        assert results.count() > 0


@pytest.mark.django_db
class TestQualityScoreCalculation:
    def test_zero_rows_returns_zero(self, test_uploaded_file):
        result = calculate_quality_score(test_uploaded_file, 0)
        assert result == 0

    def test_all_valid_returns_100(self, test_user, test_template, db):
        csv_file = SimpleUploadedFile(
            "valid.csv", b"Name,Score\nAlice,50\n", content_type="text/csv"
        )
        upl = UploadedFile.objects.create(
            user=test_user, template=test_template, file=csv_file, status="Completed"
        )
        result = calculate_quality_score(upl, 10)
        assert result == 100.0

    def test_all_invalid_returns_0(
        self, test_user, test_template, test_validation_rule, db
    ):
        csv_file = SimpleUploadedFile(
            "invalid.csv", b"Name,Score\nAlice,-10\n", content_type="text/csv"
        )
        upl = UploadedFile.objects.create(
            user=test_user, template=test_template, file=csv_file, status="Completed"
        )
        validate_excel_data(upl)
        result = calculate_quality_score(upl, 1)
        assert result == 0.0

    def test_partial_valid_returns_mid_score(
        self, test_user, test_template, test_validation_rule, db
    ):
        csv_file = SimpleUploadedFile(
            "partial.csv",
            b"Name,Score\nAlice,50\nBob,-10\n",
            content_type="text/csv",
        )
        upl = UploadedFile.objects.create(
            user=test_user, template=test_template, file=csv_file, status="Completed"
        )
        validate_excel_data(upl)
        result = calculate_quality_score(upl, 2)
        assert 0 < result < 100


@pytest.mark.django_db
class TestValidationReportWorkflow:
    def test_report_displays_quality_score(
        self, authenticated_client, test_uploaded_file, test_validation_result
    ):
        response = authenticated_client.get(
            reverse("validation_report", args=[test_uploaded_file.id])
        )
        assert response.status_code == 200
        assert "quality_score" in response.context

    def test_report_displays_recommendations(
        self, authenticated_client, test_uploaded_file, test_formula_rule
    ):
        response = authenticated_client.get(
            reverse("validation_report", args=[test_uploaded_file.id])
        )
        assert response.status_code == 200
        assert "recommendations" in response.context

    def test_report_shows_failed_validations(
        self, authenticated_client, test_uploaded_file, test_validation_result
    ):
        response = authenticated_client.get(
            reverse("validation_report", args=[test_uploaded_file.id])
        )
        assert response.status_code == 200
        results = response.context["results"]
        assert results.count() > 0

    def test_report_handles_missing_file_gracefully(
        self, authenticated_client, test_user, db
    ):
        response = authenticated_client.get(reverse("validation_report", args=[99999]))
        assert response.status_code == 404


@pytest.mark.django_db
class TestDownloadExcelWorkflow:
    def test_download_creates_xlsx(
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

    def test_download_includes_processed_filename(
        self, authenticated_client, test_uploaded_file_with_file
    ):
        response = authenticated_client.get(
            reverse("download_excel", args=[test_uploaded_file_with_file.id])
        )
        assert "processed" in response["Content-Disposition"].lower()

    def test_download_handles_pdf_gracefully(
        self, authenticated_client, test_user, test_template, db
    ):
        pdf_file = SimpleUploadedFile(
            "test.pdf", b"pdf content", content_type="application/pdf"
        )
        upl = UploadedFile.objects.create(
            user=test_user, template=test_template, file=pdf_file, status="Completed"
        )
        response = authenticated_client.get(reverse("download_excel", args=[upl.id]))
        assert response.status_code == 200
        assert b"Download not available" in response.content


@pytest.mark.django_db
class TestPreviewExcelWorkflow:
    def test_preview_returns_html_table(
        self, authenticated_client, test_uploaded_file_with_file
    ):
        response = authenticated_client.get(
            reverse("preview_excel", args=[test_uploaded_file_with_file.id])
        )
        assert response.status_code == 200
        data = response.json()
        assert "table" in data
        assert "<table" in data["table"]

    def test_preview_with_csv_file(
        self, authenticated_client, test_user, test_template
    ):
        csv_file = SimpleUploadedFile(
            "data.csv", b"Name,Score\nAlice,85\n", content_type="text/csv"
        )
        upl = UploadedFile.objects.create(
            user=test_user, template=test_template, file=csv_file, status="Completed"
        )
        response = authenticated_client.get(reverse("preview_excel", args=[upl.id]))
        assert response.status_code == 200
        data = response.json()
        assert "table" in data
        assert "<table" in data["table"]


@pytest.mark.django_db
class TestUploadHistoryWorkflow:
    def test_history_shows_user_files(self, authenticated_client, test_uploaded_file):
        response = authenticated_client.get(reverse("upload_history"))
        assert response.status_code == 200
        files = response.context["files"]
        assert test_uploaded_file in files

    def test_history_orders_by_upload_time(
        self, authenticated_client, test_user, test_template, db
    ):
        upl1 = UploadedFile.objects.create(
            user=test_user, template=test_template, status="Completed"
        )
        upl2 = UploadedFile.objects.create(
            user=test_user, template=test_template, status="Completed"
        )
        response = authenticated_client.get(reverse("upload_history"))
        files = list(response.context["files"])
        assert files[0] == upl2
        assert files[1] == upl1


@pytest.mark.django_db
class TestAdminDashboardWorkflow:
    def test_admin_dashboard_shows_all_users_files(
        self, admin_client, test_user, test_template, db
    ):
        UploadedFile.objects.create(
            user=test_user, template=test_template, status="Completed"
        )
        response = admin_client.get(reverse("admin_dashboard"))
        assert response.status_code == 200

    def test_admin_dashboard_shows_statistics(
        self, admin_client, test_user, test_template, db
    ):
        DomainTemplate.objects.create(
            template_name="Test", domain_type="test", created_by=test_user
        )
        response = admin_client.get(reverse("admin_dashboard"))
        assert "domain_count" in response.context
        assert "user_count" in response.context


@pytest.mark.django_db
class TestTemplateManagementWorkflow:
    def test_manage_templates_shows_all_templates(
        self, authenticated_client, test_template
    ):
        response = authenticated_client.get(reverse("manage_templates"))
        assert response.status_code == 200
        templates = response.context["templates"]
        assert test_template in templates

    def test_manage_templates_shows_rules_for_selected(
        self, authenticated_client, test_template, test_validation_rule
    ):
        response = authenticated_client.get(
            f"{reverse('manage_templates')}?template_id={test_template.id}"
        )
        assert response.status_code == 200
        assert "validation_rules" in response.context
