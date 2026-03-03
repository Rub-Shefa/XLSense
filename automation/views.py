import os
import time
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from .models import (
    DomainTemplate,
    ValidationRule,
    FormulaRule,
    AuditLog,
    UploadedFile
)


# =========================
# Dashboard View
# =========================
@login_required
def dashboard_view(request):
    logs = AuditLog.objects.all().order_by('-action_timestamp')[:5]
    domain_count = DomainTemplate.objects.count()
    rule_count = ValidationRule.objects.count()

    context = {
        'logs': logs,
        'domain_count': domain_count,
        'rule_count': rule_count,
    }

    return render(request, 'dashboard.html', context)


# =========================
# Manage Templates View
# =========================
@login_required
def manage_templates_view(request):
    selected_template_id = request.GET.get('template_id')

    templates = DomainTemplate.objects.all()

    validation_rules = []
    formula_rules = []

    if selected_template_id:
        validation_rules = ValidationRule.objects.filter(
            template_id=selected_template_id
        )
        formula_rules = FormulaRule.objects.filter(
            template_id=selected_template_id
        )
    else:
        validation_rules = ValidationRule.objects.all()
        formula_rules = FormulaRule.objects.all()

    return render(request, 'manage_templates.html', {
        'templates': templates,
        'validation_rules': validation_rules,
        'formula_rules': formula_rules,
        'selected_id': selected_template_id
    })


# =========================
# Upload File View (Improved UX Version)
# =========================
@login_required
def upload_file_view(request):

    latest_upload = UploadedFile.objects.order_by("-upload_time").first()

    if request.method == "POST":
        files = request.FILES.getlist("file")

        if not files:
            messages.error(request, "Please select at least one file.")
            return redirect("upload_file")

        for file in files:

            # Validate file type
            if not file.name.endswith((".xlsx", ".csv")):
                messages.error(
                    request,
                    f"{file.name} is not supported. Only CSV and XLSX files allowed."
                )
                continue

            uploaded_file = UploadedFile.objects.create(
    user=request.user,
    file=file,
    status="Processing"
)

            # Simulated processing delay
            time.sleep(2)

            uploaded_file.status = "Completed"
            uploaded_file.save()

        messages.success(request, "File(s) processed successfully.")
        return redirect("upload_file")

    context = {
        "latest_upload": latest_upload
    }

    return render(request, "upload.html", context)