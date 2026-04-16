import pytest
from automation.models import (
    DomainTemplate,
    ValidationRule,
    FormulaRule,
    UploadedFile,
    ValidationResult,
    AuditLog,
)


@pytest.mark.django_db
class TestDomainTemplate:
    def test_domain_template_str(self, test_template):
        assert str(test_template) == "Test Template"

    def test_domain_template_fields(self, test_user):
        template = DomainTemplate.objects.create(
            template_name="Student Grading",
            domain_type="education",
            created_by=test_user,
        )
        assert template.template_name == "Student Grading"
        assert template.domain_type == "education"
        assert template.created_by == test_user
        assert template.created_at is not None


@pytest.mark.django_db
class TestValidationRule:
    def test_validation_rule_str(self, test_validation_rule):
        assert str(test_validation_rule) == "Score Range"

    def test_validation_rule_default_security_level(self, test_template):
        rule = ValidationRule.objects.create(
            template=test_template,
            rule_name="Test Rule",
            column_name="TestCol",
            condition_expression="x > 0",
            error_message="Error",
        )
        assert rule.security_level == "Normal"

    def test_validation_rule_cascade_delete(self, test_template, test_validation_rule):
        test_template.delete()
        assert not ValidationRule.objects.filter(id=test_validation_rule.id).exists()


@pytest.mark.django_db
class TestFormulaRule:
    def test_formula_rule_str(self, test_formula_rule):
        assert str(test_formula_rule) == "Total Score"

    def test_formula_rule_fields(self, test_template):
        rule = FormulaRule.objects.create(
            template=test_template,
            formula_name="Average",
            target_column="Avg",
            condition_expression="sum/count",
            explanation_text="Average is calculated",
        )
        assert str(rule) == "Average"

    def test_formula_rule_cascade_delete(self, test_template, test_formula_rule):
        test_template.delete()
        assert not FormulaRule.objects.filter(id=test_formula_rule.id).exists()


@pytest.mark.django_db
class TestUploadedFile:
    def test_uploaded_file_str(self, test_uploaded_file):
        assert "UploadedFile object" in str(test_uploaded_file)

    def test_uploaded_file_default_status(self, test_user, test_template):
        f = UploadedFile.objects.create(user=test_user, template=test_template)
        assert f.status == "Pending"

    def test_uploaded_file_short_name_with_file(self, test_uploaded_file_with_file):
        name = test_uploaded_file_with_file.short_name
        assert "test" in name.lower() and ".csv" in name.lower()

    def test_uploaded_file_short_name_no_file(self, test_uploaded_file):
        assert test_uploaded_file.short_name == "Untitled"

    def test_uploaded_file_short_name_empty_file(self, test_user, test_template):
        f = UploadedFile.objects.create(user=test_user, template=test_template, file="")
        assert f.short_name == "Untitled"

    def test_uploaded_file_cascade_delete(
        self, test_user, test_template, test_uploaded_file
    ):
        test_user.delete()
        assert not UploadedFile.objects.filter(id=test_uploaded_file.id).exists()


@pytest.mark.django_db
class TestValidationResult:
    def test_validation_result_str(self, test_validation_result):
        assert "Row" in str(test_validation_result)
        assert "1" in str(test_validation_result)

    def test_validation_result_default_is_valid(self, test_uploaded_file):
        result = ValidationResult.objects.create(
            file=test_uploaded_file,
            row_index=1,
            column_name="Test",
            error_details="Error",
        )
        assert result.is_valid is False

    def test_validation_result_str_empty_file_name(self, test_uploaded_file, db):
        result = ValidationResult.objects.create(
            file=test_uploaded_file,
            row_index=1,
            column_name="Test",
            error_details="Error",
        )
        result_str = str(result)
        assert "Row" in result_str
        assert "1" in result_str

    def test_validation_result_cascade_delete(
        self, test_uploaded_file, test_validation_result
    ):
        test_uploaded_file.delete()
        assert not ValidationResult.objects.filter(
            id=test_validation_result.id
        ).exists()

    def test_validation_result_ai_insight(self, test_validation_result, remove_api_key):
        insight = test_validation_result.ai_insight
        assert insight is not None
        assert len(insight) > 0


@pytest.mark.django_db
class TestAuditLog:
    def test_audit_log_str(self, test_audit_log):
        assert "testuser" in str(test_audit_log)
        assert "File Upload" in str(test_audit_log)

    def test_audit_log_fields(self, test_user):
        log = AuditLog.objects.create(
            user=test_user,
            action_type="Login",
            details="User logged in",
        )
        assert str(log) == "testuser - Login"
        assert log.action_timestamp is not None

    def test_audit_log_cascade_delete(self, test_user, test_audit_log):
        test_user.delete()
        assert not AuditLog.objects.filter(id=test_audit_log.id).exists()
