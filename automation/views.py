from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.decorators import login_required
import time

from .models import (
    DomainTemplate,
    ValidationRule,
    FormulaRule,
    AuditLog,
    UploadedFile
)


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


@login_required
def manage_templates_view(request):
    selected_template_id = request.GET.get('template_id')
    templates = DomainTemplate.objects.all()

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


@login_required
def upload_file_view(request):
    templates = DomainTemplate.objects.all()

    # Simulate background processing
    processing_files = UploadedFile.objects.filter(user=request.user, status="Processing")

    for file in processing_files:
        time.sleep(1)  # simulate work
        file.status = "Completed"
        file.processed_time = timezone.now()
        file.save()

    if request.method == "POST":
        uploaded_file = request.FILES.get("file")
        template_id = request.POST.get("template_id")

        if not uploaded_file:
            messages.error(request, "Please select a file.")
            return redirect("upload_file")

        if not uploaded_file.name.lower().endswith((".xlsx", ".csv")):
            messages.error(request, "Only .xlsx and .csv files are allowed.")
            return redirect("upload_file")

        selected_template = DomainTemplate.objects.get(id=template_id)

        UploadedFile.objects.create(
            user=request.user,
            template=selected_template,
            file=uploaded_file,
            status="Processing"
        )

        messages.success(request, "File uploaded. Processing started...")
        return redirect("upload_file")

    user_files = UploadedFile.objects.filter(user=request.user).order_by('-upload_time')
    processing_exists = user_files.filter(status="Processing").exists()

    return render(request, "upload.html", {
        "templates": templates,
        "user_files": user_files,
        "processing_exists": processing_exists
    })