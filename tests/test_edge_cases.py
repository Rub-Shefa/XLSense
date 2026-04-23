import pytest
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from automation.models import UploadedFile


@pytest.mark.django_db
class TestEdgeCases:
    def test_upload_pdf_file_creates_record(
        self, authenticated_client, test_user, test_template
    ):
        pdf_file = SimpleUploadedFile(
            "test.pdf", b"pdf content", content_type="application/pdf"
        )
        response = authenticated_client.post(
            reverse("upload_file"),
            {"domain": test_template.domain_type, "file": pdf_file},
        )
        assert response.status_code == 302
        upl = UploadedFile.objects.filter(user=test_user).first()
        assert upl is not None
        assert upl.status == "Completed"

    def test_upload_txt_file_creates_record(
        self, authenticated_client, test_user, test_template
    ):
        txt_file = SimpleUploadedFile(
            "test.txt", b"text content", content_type="text/plain"
        )
        response = authenticated_client.post(
            reverse("upload_file"),
            {"domain": test_template.domain_type, "file": txt_file},
        )
        assert response.status_code == 302
        upl = UploadedFile.objects.filter(user=test_user).first()
        assert upl is not None
        assert upl.status == "Completed"

    def test_upload_empty_csv_handled(
        self, authenticated_client, test_user, test_template
    ):
        empty_csv = SimpleUploadedFile("empty.csv", b"", content_type="text/csv")
        response = authenticated_client.post(
            reverse("upload_file"),
            {"domain": test_template.domain_type, "file": empty_csv},
        )
        assert response.status_code == 302


@pytest.mark.django_db
class TestValidationResultEdgeCases:
    def test_validation_result_str_with_missing_file(self, test_uploaded_file):
        from automation.models import ValidationResult

        result = ValidationResult.objects.create(
            file=test_uploaded_file,
            row_index=1,
            column_name="Test",
            error_details="Error",
        )
        result_str = str(result)
        assert "Row" in result_str


@pytest.mark.django_db
class TestUploadedFileEdgeCases:
    def test_uploaded_file_with_xlsx_extension(self, test_user, test_template):
        from django.core.files.uploadedfile import SimpleUploadedFile
        import io
        import pandas as pd

        df = pd.DataFrame({"Name": ["Alice"]})
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False, engine="openpyxl")
        buffer.seek(0)

        xlsx_file = SimpleUploadedFile(
            "test.xlsx",
            buffer.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        upl = UploadedFile.objects.create(
            user=test_user, template=test_template, file=xlsx_file, status="Completed"
        )
        assert "test" in upl.short_name.lower() and ".xlsx" in upl.short_name.lower()

    def test_uploaded_file_status_values(self, test_user, test_template):
        upl = UploadedFile.objects.create(user=test_user, template=test_template)
        assert upl.status == "Pending"
        upl.status = "Processing"
        upl.save()
        upl.refresh_from_db()
        assert upl.status == "Processing"


@pytest.mark.django_db
class TestDownloadEdgeCases:
    def test_download_csv_creates_xlsx(
        self, authenticated_client, test_user, test_template
    ):
        csv_file = SimpleUploadedFile(
            "data.csv", b"Name,Score\nAlice,85\n", content_type="text/csv"
        )
        upl = UploadedFile.objects.create(
            user=test_user, template=test_template, file=csv_file, status="Completed"
        )
        response = authenticated_client.get(reverse("download_excel", args=[upl.id]))
        assert response.status_code == 200
        assert "xlsx" in response["Content-Disposition"].lower()

    def test_download_with_style_param(
        self, authenticated_client, test_uploaded_file_with_file
    ):
        response = authenticated_client.get(
            reverse("download_excel", args=[test_uploaded_file_with_file.id])
            + "?style=medium"
        )
        assert response.status_code == 200


@pytest.mark.django_db
class TestPreviewEdgeCases:
    def test_preview_with_empty_rows(
        self, authenticated_client, test_user, test_template
    ):
        csv_file = SimpleUploadedFile(
            "data.csv", b"Name,Score\n,,\nAlice,85\n", content_type="text/csv"
        )
        upl = UploadedFile.objects.create(
            user=test_user, template=test_template, file=csv_file, status="Completed"
        )
        response = authenticated_client.get(reverse("preview_excel", args=[upl.id]))
        assert response.status_code == 200
        data = response.json()
        assert "table" in data


@pytest.mark.django_db
class TestEditorEdgeCases:
    def test_editor_with_saved_mappings(
        self, authenticated_client, test_uploaded_file_with_file
    ):
        test_uploaded_file_with_file.column_mappings = {"Name": "name_col"}
        test_uploaded_file_with_file.save()

        response = authenticated_client.get(
            reverse("workbook_editor", args=[test_uploaded_file_with_file.id])
        )
        assert response.status_code == 200
        assert "saved_mappings_json" in response.context


@pytest.mark.django_db
class TestViewsEdgeCases:
    def test_dashboard_with_no_files(self, authenticated_client):
        response = authenticated_client.get(reverse("dashboard"))
        assert response.status_code == 200
        assert response.context["processed_count"] == 0
        assert response.context["pending_count"] == 0

    def test_upload_history_empty(self, authenticated_client):
        response = authenticated_client.get(reverse("upload_history"))
        assert response.status_code == 200
        assert len(response.context["files"]) == 0

    def test_manage_templates_no_templates(self, authenticated_client):
        response = authenticated_client.get(reverse("manage_templates"))
        assert response.status_code == 200
        assert "templates" in response.context


@pytest.mark.django_db
class TestValidationEdgeCases:
    def test_validate_with_only_header_row(
        self, test_user, test_template, test_validation_rule
    ):
        csv_file = SimpleUploadedFile(
            "only_header.csv", b"Name,Score\n", content_type="text/csv"
        )
        upl = UploadedFile.objects.create(
            user=test_user, template=test_template, file=csv_file, status="Completed"
        )
        from automation.utils import validate_excel_data

        result = validate_excel_data(upl)
        assert result is True
