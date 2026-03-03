from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
import time

from .models import (
    DomainTemplate,
    ValidationRule,
    FormulaRule,
    UploadedFile,
    AuditLog
)


# ----------------------------------
# Dashboard View
# ----------------------------------
@login_required
def dashboard_view(request):
    logs = AuditLog.objects.all().order_by('-action_timestamp')[:5]
    domain_count = DomainTemplate.objects.count()
    rule_count = ValidationRule.objects.count()

    return render(request, 'dashboard.html', {
        'logs': logs,
        'domain_count': domain_count,
        'rule_count': rule_count,
    })


# ----------------------------------
# Manage Templates View
# ----------------------------------
@login_required
def manage_templates_view(request):
    selected_template_id = request.GET.get('template_id')

    templates = DomainTemplate.objects.all()
    validation_rules = []
    formula_rules = []

    if selected_template_id:
        validation_rules = ValidationRule.objects.filter(template_id=selected_template_id)
        formula_rules = FormulaRule.objects.filter(template_id=selected_template_id)
    else:
        validation_rules = ValidationRule.objects.all()
        formula_rules = FormulaRule.objects.all()

    return render(request, 'manage_templates.html', {
        'templates': templates,
        'validation_rules': validation_rules,
        'formula_rules': formula_rules,
        'selected_id': selected_template_id
    })


# ----------------------------------
# Upload File View
# ----------------------------------
@login_required
def upload_file_view(request):
    templates = DomainTemplate.objects.all()

    if request.method == "POST":
        selected_template_id = request.POST.get("template")
        uploaded_file = request.FILES.get("file")

        # Validate input
        if not selected_template_id or not uploaded_file:
            messages.error(request, "Please select a domain and a file.")
            return redirect("upload_file")

        # Validate file type
        if not uploaded_file.name.endswith((".xlsx", ".csv")):
            messages.error(request, "Only .xlsx and .csv files are allowed.")
            return redirect("upload_file")

        template = DomainTemplate.objects.get(id=selected_template_id)

        # Create file record with Processing status
        file_instance = UploadedFile.objects.create(
            user=request.user,
            template=template,
            file=uploaded_file,
            status="Processing"
        )

        # Simulated backend processing delay
        time.sleep(3)

        # Mark as completed
        file_instance.status = "Completed"
        file_instance.processed_time = timezone.now()
        file_instance.save()

        return redirect("upload_file")

    # Get latest uploaded file
    latest_file = UploadedFile.objects.filter(
        user=request.user
    ).order_by("-upload_time").first()

    return render(request, "upload.html", {
        "templates": templates,
        "latest_file": latest_file,
    })