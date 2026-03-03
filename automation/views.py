import os
import time
from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.contrib.auth.models import User

from .models import DomainTemplate, ValidationRule, FormulaRule, AuditLog, UploadedFile
from .forms import CustomUserCreationForm


def is_admin(user):
    return user.is_staff or user.is_superuser


def redirectBasedOnRole(user):
    if user.is_staff or user.is_superuser:
        return redirect("admin_dashboard")
    return redirect("dashboard")


# =========================
# Authentication Views
# =========================
def login_view(request):
    if request.user.is_authenticated:
        return redirectBasedOnRole(request.user)

    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get("username")
            password = form.cleaned_data.get("password")
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f"Welcome back, {username}!")
                return redirectBasedOnRole(user)
            else:
                messages.error(request, "Invalid username or password.")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, error)
    else:
        form = AuthenticationForm()

    return render(request, "login.html", {"form": form})


def register_view(request):
    if request.user.is_authenticated:
        return redirectBasedOnRole(request.user)

    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get("username")
            messages.success(
                request, f"Account created for {username}! You can now login."
            )
            return redirect("login")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{error}")
    else:
        form = CustomUserCreationForm()

    return render(request, "register.html", {"form": form})


def logout_view(request):
    if request.method == "POST":
        logout(request)
        messages.info(request, "You have successfully logged out.")
        return redirect("login")
    return redirect("login")


# =========================
# Dashboard Views
# =========================
@login_required
def dashboard_view(request):
    if is_admin(request.user):
        return redirect("admin_dashboard")

    if request.method == "POST":
        domain = request.POST.get("domain")
        uploaded_file = request.FILES.get("file")

        if not uploaded_file or not domain:
            messages.error(request, "Please select a domain and upload a file.")
        else:
            template = DomainTemplate.objects.filter(domain_type=domain).first()
            if not template:
                template = DomainTemplate.objects.first()

            file_record = UploadedFile.objects.create(
                user=request.user,
                template=template,
                file=uploaded_file,
                status="Pending",
            )

            AuditLog.objects.create(
                user=request.user,
                action_type="File Upload",
                details=f"Uploaded file: {uploaded_file.name} for domain: {domain}",
            )

            messages.success(
                request, "File uploaded successfully! Processing will begin shortly."
            )
            return redirect("dashboard")

    files = UploadedFile.objects.filter(user=request.user).order_by("-upload_time")
    processed_count = files.filter(status="Completed").count()
    pending_count = files.filter(status="Pending").count()

    context = {
        "files": files,
        "processed_count": processed_count,
        "pending_count": pending_count,
    }
    return render(request, "user_dashboard.html", context)


@login_required
def admin_dashboard_view(request):
    if not is_admin(request.user):
        return redirect("dashboard")

    logs = AuditLog.objects.all().order_by("-action_timestamp")[:5]
    domain_count = DomainTemplate.objects.count()
    rule_count = ValidationRule.objects.count()

    context = {
        "logs": logs,
        "domain_count": domain_count,
        "rule_count": rule_count,
    }

    return render(request, "dashboard.html", context)


# =========================
# Manage Templates View
# =========================
@login_required
@user_passes_test(is_admin)
def manage_templates_view(request):
    selected_template_id = request.GET.get("template_id")
    templates = DomainTemplate.objects.all()

    validation_rules = []
    formula_rules = []

    if selected_template_id:
        validation_rules = ValidationRule.objects.filter(
            template_id=selected_template_id
        )
        formula_rules = FormulaRule.objects.filter(template_id=selected_template_id)
    else:
        validation_rules = ValidationRule.objects.all()
        formula_rules = FormulaRule.objects.all()

    return render(
        request,
        "manage_templates.html",
        {
            "templates": templates,
            "validation_rules": validation_rules,
            "formula_rules": formula_rules,
            "selected_id": selected_template_id,
        },
    )


# =========================
# Upload File View
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
            if not file.name.endswith((".xlsx", ".csv")):
                messages.error(
                    request,
                    f"{file.name} is not supported. Only CSV and XLSX files allowed.",
                )
                continue

            uploaded_file = UploadedFile.objects.create(
                user=request.user, file=file, status="Processing"
            )

            time.sleep(2)

            uploaded_file.status = "Completed"
            uploaded_file.save()

        messages.success(request, "File(s) processed successfully.")
        return redirect("upload_file")

    context = {"latest_upload": latest_upload}

    return render(request, "upload.html", context)
