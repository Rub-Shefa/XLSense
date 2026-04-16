import json
import pytest
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from automation.models import UploadedFile


@pytest.mark.django_db
class TestWorkbookEditorView:
    def test_editor_requires_login(self, client):
        response = client.get(reverse("workbook_editor", args=[1]))
        assert response.status_code == 302

    def test_editor_loads_own_file(
        self, authenticated_client, test_uploaded_file_with_file
    ):
        response = authenticated_client.get(
            reverse("workbook_editor", args=[test_uploaded_file_with_file.id])
        )
        assert response.status_code == 200
        assert "file" in response.context

    def test_editor_404_for_other_user(
        self, authenticated_client, test_user, test_template, db
    ):
        from django.contrib.auth.models import User

        other_user = User.objects.create_user(
            username="other_editor", password="pass123"
        )

        csv_file = SimpleUploadedFile(
            "test.csv", b"Name,Score\nAlice,85\n", content_type="text/csv"
        )

        upl = UploadedFile.objects.create(
            user=other_user, template=test_template, file=csv_file, status="Completed"
        )
        response = authenticated_client.get(reverse("workbook_editor", args=[upl.id]))
        assert response.status_code == 404

    def test_editor_loads_csv_file(
        self, authenticated_client, test_uploaded_file_with_file
    ):
        response = authenticated_client.get(
            reverse("workbook_editor", args=[test_uploaded_file_with_file.id])
        )
        assert response.status_code == 200
        assert "preview_data" in response.context

    def test_editor_loads_xlsx_file(
        self, authenticated_client, test_user, test_template, xlsx_file
    ):
        upl = UploadedFile.objects.create(
            user=test_user, template=test_template, file=xlsx_file, status="Completed"
        )
        response = authenticated_client.get(reverse("workbook_editor", args=[upl.id]))
        assert response.status_code == 200

    def test_editor_includes_db_columns(
        self, authenticated_client, test_uploaded_file_with_file, test_formula_rule
    ):
        response = authenticated_client.get(
            reverse("workbook_editor", args=[test_uploaded_file_with_file.id])
        )
        assert response.status_code == 200
        assert "db_columns" in response.context

    def test_editor_adds_missing_template_columns(
        self, authenticated_client, test_uploaded_file_with_file, test_formula_rule
    ):
        response = authenticated_client.get(
            reverse("workbook_editor", args=[test_uploaded_file_with_file.id])
        )
        assert response.status_code == 200
        db_columns = response.context["db_columns"]
        assert "Total" in db_columns


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

    def test_save_creates_new_file(
        self, authenticated_client, test_uploaded_file_with_file
    ):
        data = {
            "headers": ["Name", "Score"],
            "rows": [
                [{"value": "Alice"}, {"value": 85}],
            ],
            "mappings": {},
        }
        response = authenticated_client.post(
            reverse("save_workbook", args=[test_uploaded_file_with_file.id]),
            data=json.dumps(data),
            content_type="application/json",
        )
        result = response.json()
        new_file = UploadedFile.objects.get(id=result["new_file_id"])
        assert new_file.status == "Completed"
        assert new_file.user == test_uploaded_file_with_file.user
        assert new_file.template == test_uploaded_file_with_file.template

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

    def test_save_preserves_style_data(self, authenticated_client, test_uploaded_file):
        data = {
            "headers": ["Name", "Score"],
            "rows": [
                [
                    {"value": "Alice", "bold": True, "color": "#FF0000"},
                    {"value": 85},
                ],
            ],
            "mappings": {},
        }
        response = authenticated_client.post(
            reverse("save_workbook", args=[test_uploaded_file.id]),
            data=json.dumps(data),
            content_type="application/json",
        )
        result = response.json()
        new_file = UploadedFile.objects.get(id=result["new_file_id"])
        assert new_file.style_data is not None

    def test_save_returns_500_on_error(
        self, authenticated_client, test_uploaded_file, db
    ):
        from unittest.mock import patch

        csv_file = SimpleUploadedFile(
            "data.csv", b"Name,Score\nAlice,85\n", content_type="text/csv"
        )
        test_uploaded_file.file = csv_file
        test_uploaded_file.save()

        with patch(
            "automation.editor_views.pd.DataFrame", side_effect=Exception("Test error")
        ):
            data = {"headers": ["Name"], "rows": [[{"value": "Alice"}]], "mappings": {}}
            response = authenticated_client.post(
                reverse("save_workbook", args=[test_uploaded_file.id]),
                data=json.dumps(data),
                content_type="application/json",
            )
        assert response.status_code == 500
        result = response.json()
        assert result.get("status") == "failed"


@pytest.mark.django_db
class TestWorkbookEditorSecurity:
    def test_user_cannot_edit_others_file(
        self, authenticated_client, test_user, test_template, db
    ):
        from django.contrib.auth.models import User

        other = User.objects.create_user(username="other_sec", password="pass123")
        csv_file = SimpleUploadedFile(
            "test.csv", b"Name\nAlice\n", content_type="text/csv"
        )
        upl = UploadedFile.objects.create(
            user=other, template=test_template, file=csv_file, status="Completed"
        )
        response = authenticated_client.get(reverse("workbook_editor", args=[upl.id]))
        assert response.status_code == 404

    def test_user_cannot_save_others_file(
        self, authenticated_client, test_user, test_template, db
    ):
        from django.contrib.auth.models import User

        other = User.objects.create_user(username="other_save", password="pass123")
        csv_file = SimpleUploadedFile(
            "test.csv", b"Name\nAlice\n", content_type="text/csv"
        )
        upl = UploadedFile.objects.create(
            user=other, template=test_template, file=csv_file, status="Completed"
        )
        data = {"headers": ["Name"], "rows": [[{"value": "Alice"}]], "mappings": {}}
        response = authenticated_client.post(
            reverse("save_workbook", args=[upl.id]),
            data=json.dumps(data),
            content_type="application/json",
        )
        assert response.status_code in [404, 500]
