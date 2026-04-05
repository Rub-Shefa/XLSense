from django.db import models
from django.contrib.auth.models import User
import os


# 1. The main template for the domain (e.g., Student Grading)
class DomainTemplate(models.Model):
    template_name = models.CharField(max_length=255)
    domain_type = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)

    def __str__(self):
        return self.template_name


# 2. The Rule for specific column ranges
class ValidationRule(models.Model):
    template = models.ForeignKey(DomainTemplate, on_delete=models.CASCADE)
    rule_name = models.CharField(max_length=255)
    column_name = models.CharField(max_length=100)
    condition_expression = models.TextField()
    error_message = models.TextField()
    security_level = models.CharField(max_length=50, default="Normal")

    def __str__(self):
        return self.rule_name


# 3. The Rule for math formulas
class FormulaRule(models.Model):
    template = models.ForeignKey(DomainTemplate, on_delete=models.CASCADE)
    formula_name = models.CharField(max_length=255)
    target_column = models.CharField(max_length=100)
    condition_expression = models.TextField()
    explanation_text = models.TextField()

    def __str__(self):
        return self.formula_name


# 4. The actual Excel File being uploaded
class UploadedFile(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    template = models.ForeignKey(DomainTemplate, on_delete=models.SET_NULL, null=True)
    file = models.FileField(upload_to="uploads/")
    upload_time = models.DateTimeField(auto_now_add=True)
    processed_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=50, default="Pending")
    style_data = models.JSONField(null=True, blank=True)
    column_mappings = models.JSONField(null=True, blank=True)

    @property
    def short_name(self):
        if self.file and self.file.name:
            return os.path.basename(self.file.name)
        return "Untitled"


class ValidationResult(models.Model):
    file = models.ForeignKey(UploadedFile, on_delete=models.CASCADE)
    row_index = models.IntegerField()
    column_name = models.CharField(max_length=100)
    error_details = models.TextField()
    is_valid = models.BooleanField(default=False)

    def __str__(self):
        try:
            name = self.file.file.name
        except Exception:
            name = "Unknown"
        return f"Result for {name} - Row {self.row_index}"

    @property
    def ai_insight(self):
        """
        A property that provides the professional AI explanation
        directly from the model instance.
        """
        # We import here to avoid circular dependency with views/utils
        from .utils import generate_ai_explanation 
        
        # We reuse your new professional logic
        return generate_ai_explanation(
            formula_name="Validation Rule",
            target_column=self.column_name,
            condition_expression=self.error_details
        )


# 6. Tracking who did what
class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    action_type = models.CharField(max_length=100)
    details = models.TextField()
    action_timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.action_type}"
