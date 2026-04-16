import os
import io
import pytest
from django.contrib.auth.models import User
from automation.models import (
    DomainTemplate,
    ValidationRule,
    FormulaRule,
    UploadedFile,
    ValidationResult,
    AuditLog,
)
from django.core.files.uploadedfile import SimpleUploadedFile


@pytest.fixture
def test_user(db):
    return User.objects.create_user(username="testuser", password="testpass123")


@pytest.fixture
def test_admin(db):
    return User.objects.create_user(
        username="admin", password="adminpass123", is_staff=True
    )


@pytest.fixture
def test_template(test_user):
    return DomainTemplate.objects.create(
        template_name="Test Template",
        domain_type="testing",
        created_by=test_user,
    )


@pytest.fixture
def test_validation_rule(test_template):
    return ValidationRule.objects.create(
        template=test_template,
        rule_name="Score Range",
        column_name="Score",
        condition_expression="x >= 0 and x <= 100",
        error_message="Score must be between 0 and 100",
        security_level="Normal",
    )


@pytest.fixture
def test_formula_rule(test_template):
    return FormulaRule.objects.create(
        template=test_template,
        formula_name="Total Score",
        target_column="Total",
        condition_expression="Score + Bonus",
        explanation_text="Total is the sum of Score and Bonus.",
    )


@pytest.fixture
def test_audit_log(test_user):
    return AuditLog.objects.create(
        user=test_user,
        action_type="File Upload",
        details="Test file uploaded successfully",
    )


@pytest.fixture
def csv_file():
    content = "Name,Score,Bonus\nAlice,85,10\nBob,90,5\n"
    return SimpleUploadedFile(
        name="test.csv",
        content=content.encode("utf-8"),
        content_type="text/csv",
    )


@pytest.fixture
def xlsx_file():
    import pandas as pd

    df = pd.DataFrame({"Name": ["Alice", "Bob"], "Score": [85, 90], "Bonus": [10, 5]})
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")
    buffer.seek(0)
    return SimpleUploadedFile(
        name="test.xlsx",
        content=buffer.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@pytest.fixture
def test_uploaded_file(test_user, test_template):
    return UploadedFile.objects.create(
        user=test_user,
        template=test_template,
        status="Completed",
    )


@pytest.fixture
def test_uploaded_file_with_file(test_user, test_template, csv_file):
    return UploadedFile.objects.create(
        user=test_user,
        template=test_template,
        file=csv_file,
        status="Completed",
    )


@pytest.fixture
def test_validation_result(test_uploaded_file):
    return ValidationResult.objects.create(
        file=test_uploaded_file,
        row_index=1,
        column_name="Total",
        error_details="Math Error: Expected 95, found 80.",
        is_valid=False,
    )


@pytest.fixture
def authenticated_client(client, test_user):
    client.login(username="testuser", password="testpass123")
    return client


@pytest.fixture
def admin_client(client, test_admin):
    client.login(username="admin", password="adminpass123")
    return client


@pytest.fixture
def remove_api_key():
    original = os.environ.pop("AI_API_KEY", None)
    yield
    if original is not None:
        os.environ["AI_API_KEY"] = original
