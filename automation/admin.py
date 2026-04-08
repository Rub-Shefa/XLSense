from django.contrib import admin
from .models import (
    DomainTemplate,
    ValidationRule,
    FormulaRule,
    UploadedFile,
    ValidationResult,
    AuditLog,
)


# 1. Setup the Inlines for the Template Engine
class ValidationRuleInline(admin.TabularInline):
    model = ValidationRule
    extra = 1


class FormulaRuleInline(admin.TabularInline):
    model = FormulaRule
    extra = 1


# 2. Register DomainTemplate (Rubaiya's Core Task)
@admin.register(DomainTemplate)
class DomainTemplateAdmin(admin.ModelAdmin):
    list_display = ("id", "template_name", "domain_type", "created_by", "created_at")
    list_display_links = ("id", "template_name")
    search_fields = ("template_name", "domain_type")
    list_filter = ("domain_type",)
    inlines = [ValidationRuleInline, FormulaRuleInline]


# 3. Register Standalone Rules
@admin.register(ValidationRule)
class ValidationRuleAdmin(admin.ModelAdmin):
    list_display = ("id", "rule_name", "template", "column_name")
    list_display_links = ("id", "rule_name")


@admin.register(FormulaRule)
class FormulaRuleAdmin(admin.ModelAdmin):
    list_display = ("id", "formula_name", "template")
    list_display_links = ("id", "formula_name")


# 4. Register Files and Results (For Adita's upcoming work)
@admin.register(UploadedFile)
class UploadedFileAdmin(admin.ModelAdmin):
    list_display = ("id", "file", "status")


@admin.register(ValidationResult)
class ValidationResultAdmin(admin.ModelAdmin):
    list_display = ("id", "file", "is_valid")


# 5. Register AuditLog
@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    # This shows it in the main table list
    list_display = ("user", "action_type", "details", "action_timestamp")

    # This FORCES it to show up inside the "Add/Edit" form
    readonly_fields = ("action_timestamp",)
