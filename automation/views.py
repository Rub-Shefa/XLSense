import re
import json
import os
import time
import pandas as pd
from django.utils import timezone
from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from .utils import (
    validate_excel_data,
    get_formula_recommendations,
    calculate_quality_score,
    generate_ai_explanation,
)
from .models import (
    DomainTemplate,
    ValidationRule,
    FormulaRule,
    AuditLog,
    UploadedFile,
    ValidationResult,
)
from .forms import CustomUserCreationForm


def is_admin(user):
    return user.is_staff or user.is_superuser


def redirectBasedOnRole(user):
    return redirect("dashboard")


def detect_column_types(df):
    detected_types = {}

    for column in df.columns:
        sample = df[column].dropna()

        if sample.empty:
            detected_types[column] = "Empty"
            continue

        if pd.api.types.is_numeric_dtype(sample):
            detected_types[column] = "Numeric"
            continue

        try:
            pd.to_datetime(sample, errors="raise")
            detected_types[column] = "Date"
            continue
        except:
            pass

        numeric_count = pd.to_numeric(sample, errors="coerce").notna().sum()
        total_count = len(sample)

        if numeric_count > 0 and numeric_count < total_count:
            detected_types[column] = "Mixed"
        else:
            detected_types[column] = "Text"

    return detected_types


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

        messages.error(request, "Invalid username or password.")

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
        form = CustomUserCreationForm()

    return render(request, "register.html", {"form": form})


def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def dashboard_view(request):

    if is_admin(request.user):
        files = UploadedFile.objects.all().order_by("-upload_time")
    else:
        files = UploadedFile.objects.filter(user=request.user).order_by("-upload_time")

    processed_count = files.filter(status="Completed").count()
    pending_count = files.filter(status="Pending").count()

    context = {
        "files": files,
        "processed_count": processed_count,
        "pending_count": pending_count,
        "is_admin": is_admin(request.user),
    }

    return render(request, "user_dashboard.html", context)


@login_required
def admin_dashboard_view(request):

    logs = (
        AuditLog.objects.select_related("user").all().order_by("-action_timestamp")[:10]
    )

    domain_count = DomainTemplate.objects.count()
    rule_count = ValidationRule.objects.count()
    files_processed = UploadedFile.objects.filter(status="Completed").count()
    user_count = User.objects.count()

    context = {
        "logs": logs,
        "domain_count": domain_count,
        "rule_count": rule_count,
        "files_processed": files_processed,
        "user_count": user_count,
    }

    return render(request, "dashboard.html", context)


@login_required
def manage_templates_view(request):

    selected_template_id = request.GET.get("template_id")
    templates = DomainTemplate.objects.all()

    if not selected_template_id and templates.exists():
        selected_template_id = str(templates.first().id)

    if selected_template_id:
        validation_rules = ValidationRule.objects.filter(
            template_id=selected_template_id
        )
        formula_rules = FormulaRule.objects.filter(template_id=selected_template_id)
    else:
        validation_rules = []
        formula_rules = []

    return render(
        request,
        "manage_templates.html",
        {
            "templates": templates,
            "validation_rules": validation_rules,
            "formula_rules": formula_rules,
            "selected_id": selected_template_id,
            "page_title": "Domain Templates",
        },
    )


@login_required
def upload_file_view(request):
    domains = DomainTemplate.objects.all()

    latest_upload = (
        UploadedFile.objects.filter(user=request.user).order_by("-upload_time").first()
    )

    if request.method == "POST":
        selected_domain = request.POST.get("domain")
        files = request.FILES.getlist("file")

        if not selected_domain:
            messages.error(request, "Please select a domain.")
            return redirect("upload_file")

        if not files:
            messages.error(request, "Please select at least one file.")
            return redirect("upload_file")

        template = DomainTemplate.objects.filter(domain_type=selected_domain).first()

        if not template:
            messages.error(request, "Selected domain template not found.")
            return redirect("upload_file")

        success_count = 0
        parsed_files = []

        for file in files:
            if not file.name.endswith((".xlsx", ".csv")):
                messages.error(request, f"{file.name} is not supported.")
                continue

            uploaded_file = UploadedFile.objects.create(
                user=request.user, template=template, file=file, status="Processing"
            )

            try:
                file.seek(0)

                if file.name.endswith(".csv"):
                    df = pd.read_csv(file)
                else:
                    df = pd.read_excel(file)

                df = df.loc[:, ~df.columns.astype(str).str.contains("^Unnamed")]

                if df.empty:
                    uploaded_file.status = "Failed"
                    uploaded_file.save()
                    messages.error(request, f"{file.name} is empty.")
                    continue

                preview_data = df.fillna("").to_dict(orient="records")
                detected_types = detect_column_types(df)

                uploaded_file.status = "Completed"
                uploaded_file.processed_time = timezone.now()
                uploaded_file.save()

                validate_excel_data(uploaded_file)

                parsed_files.append(
                    {
                        "file_name": file.name,
                        "preview_data": preview_data,
                        "detected_types": detected_types,
                    }
                )

                AuditLog.objects.create(
                    user=request.user,
                    action_type="File Upload",
                    details=f"Successfully uploaded and parsed: {file.name} | Domain: {selected_domain}",
                )

                success_count += 1

            except Exception as e:
                uploaded_file.status = "Failed"
                uploaded_file.save()

                AuditLog.objects.create(
                    user=request.user,
                    action_type="Upload Error",
                    details=f"Failed to process {file.name}: {str(e)}",
                )

                messages.error(request, f"{file.name} failed to process.")

        request.session["parsed_files"] = parsed_files

        if success_count > 0:
            messages.success(request, "File(s) processed successfully.")

        return redirect("upload_file")

    parsed_files = request.session.get("parsed_files", None)

    if not latest_upload:
        request.session.pop("parsed_files", None)
        parsed_files = None

    return render(
        request,
        "upload.html",
        {
            "latest_upload": latest_upload,
            "domains": domains,
            "parsed_files": parsed_files,
        },
    )


@login_required
def upload_history_view(request):
    if request.user.is_staff:
        files = UploadedFile.objects.all().order_by("-upload_time")
    else:
        files = UploadedFile.objects.filter(user=request.user).order_by("-upload_time")

    return render(request, "upload_history.html", {"files": files})


@login_required
def validation_report_view(request, file_id):
    # Use get_object_or_404 to prevent 500 errors if the ID is wrong
    if request.user.is_staff:
        uploaded_file = get_object_or_404(UploadedFile, id=file_id)
    else:
        uploaded_file = get_object_or_404(UploadedFile, id=file_id, user=request.user)

    # 1. Get existing validation errors
    results = ValidationResult.objects.filter(file=uploaded_file, is_valid=False)

    # 2. Process the file for dynamic insights
    try:
        file_path = uploaded_file.file.path
        if file_path.endswith(".csv"):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)

        df = df.loc[:, ~df.columns.astype(str).str.contains("^Unnamed")]

        total_rows = len(df)

        # Calculate Score & Get Recs
        score = calculate_quality_score(uploaded_file, total_rows)
        recommendations = get_formula_recommendations(uploaded_file, df.columns)

    except Exception as e:
        # Fallback if file reading fails
        score = 0
        recommendations = []
        print(f"Error processing file for report: {e}")

    context = {
        "uploaded_file": uploaded_file,
        "results": results,
        "quality_score": score,
        "recommendations": recommendations,
        "page_title": "Validation Report",
    }

    return render(request, "report.html", context)


@csrf_exempt
@login_required
@require_POST
def ai_explain_view(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    result_id = data.get("result_id")
    if not result_id:
        return JsonResponse({"error": "result_id is required"}, status=400)

    result = get_object_or_404(ValidationResult, id=result_id)
    template = result.file.template

    formula = FormulaRule.objects.filter(
        template=template,
        target_column__iexact=result.column_name,
    ).first()

    if formula:
        explanation, ai_success = generate_ai_explanation(
            formula_name=formula.formula_name,
            target_column=formula.target_column,
            condition_expression=formula.condition_expression,
        )
    else:
        explanation, ai_success = generate_ai_explanation(
            formula_name="Validation Rule",
            target_column=result.column_name,
            condition_expression=result.error_details,
        )

    status_code = 200 if ai_success else 503
    return JsonResponse(
        {"explanation": explanation, "ai_used": ai_success}, status=status_code
    )
