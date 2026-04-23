import re
import json
import ast
import os
import time
from unicodedata import normalize
from urllib import request
from wsgiref import headers
import pandas as pd
from django.utils import timezone
from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.db.models import Q
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.core.files.base import ContentFile
from io import BytesIO
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
from django.http import HttpResponse
from io import BytesIO
from .text_import_views import extract_text_from_pdf, call_ai_to_csv, parse_csv_to_rows

def is_admin(user):
    return user.is_staff or user.is_superuser


def homepage_view(request):
    return render(request, "homepage.html")


def redirectBasedOnRole(user):
    return redirect("dashboard")



def detect_column_types(df):
    detected_types = {}
    for column in df.columns:
        sample = df[column].dropna()
        if sample.empty:
            detected_types[column] = "Empty"
            continue
        total = len(sample)

        # Numeric check (strict)
        numeric_converted = pd.to_numeric(sample, errors="coerce")
        numeric_ratio = numeric_converted.notna().sum() / total
        if numeric_ratio > 0.8:
            detected_types[column] = "Numeric"
            continue

        # Check if column contains date-like patterns (e.g., '/', '-', month names)
        sample_str = sample.astype(str)
        has_letters = sample_str.str.contains(r"[A-Za-z]", na=False).any()
        has_digits = sample_str.str.contains(r"\d", na=False).any()
        has_special = sample_str.str.contains(r"[^\w\s]", na=False).any()
        date_pattern = sample_str.str.contains(r'[/\-]|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december', case=False, na=False)
        has_date_pattern = date_pattern.any()

        date_ratio = 0
        if has_date_pattern:
            # Try with dayfirst=True
            try:
                date_converted = pd.to_datetime(sample, errors='coerce', dayfirst=True)
                date_ratio = date_converted.notna().sum() / total
            except:
                pass
            
            # Try explicit formats
            if date_ratio < 0.4:
                for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d %B %Y", "%B %d, %Y", "%d-%m-%Y"]:
                    try:
                        date_converted = pd.to_datetime(sample, format=fmt, errors='coerce')
                        ratio = date_converted.notna().sum() / total
                        if ratio > date_ratio:
                            date_ratio = ratio
                        if date_ratio >= 0.4:
                            break
                    except:
                        continue
            
            # Try pandas guess
            if date_ratio < 0.4:
                try:
                    date_converted = pd.to_datetime(sample, errors='coerce')
                    ratio = date_converted.notna().sum() / total
                    if ratio > date_ratio:
                        date_ratio = ratio
                except:
                    pass

        # Final classification
        if date_ratio >= 0.4:
            detected_types[column] = "Date"
        elif numeric_ratio > 0.2:
            detected_types[column] = "Mixed"
        elif has_digits and (has_letters or has_special):
            detected_types[column] = "Mixed"

        elif numeric_ratio > 0.2:
            detected_types[column] = "Mixed"

        else:
            detected_types[column] = "Text"
    
    return detected_types

def preprocess_dataframe(df):
    # clean column names
    df.columns = [str(col).strip().lower().replace(" ", "_") for col in df.columns]

    # replace empty strings with NaN
    df.replace(r"^\s*$", pd.NA, regex=True, inplace=True)

    # trim values
    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace("nan", pd.NA)

    # remove fully empty rows
    df = df.dropna(how="all")

    # remove rows with only 1 value
    df = df[df.count(axis=1) > 0]

    df = df.reset_index(drop=True)

    return df


def remove_empty_unnamed_columns(df):
    return df.loc[:, ~(
        df.columns.astype(str).str.lower().str.contains("unnamed") &
        (df.isna().sum() == len(df))
    )]


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
def audit_logs_view(request):
    """Admin-only paginated audit log viewer with filtering and search."""
    if not is_admin(request.user):
        return redirect("dashboard")

    # Filter parameters
    user_filter = request.GET.get("user", "").strip()
    action_filter = request.GET.get("action_type", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    search = request.GET.get("search", "").strip()
    page_num = request.GET.get("page", "1")

    # Base queryset
    logs = AuditLog.objects.select_related("user").order_by("-action_timestamp")

    # Apply filters
    if user_filter:
        logs = logs.filter(user__username__icontains=user_filter)
    if action_filter:
        logs = logs.filter(action_type__icontains=action_filter)
    if date_from:
        logs = logs.filter(action_timestamp__date__gte=date_from)
    if date_to:
        logs = logs.filter(action_timestamp__date__lte=date_to)
    if search:
        logs = logs.filter(
            Q(action_type__icontains=search)
            | Q(details__icontains=search)
        )

    # Pagination: 20 records per page
    from django.core.paginator import Paginator
    paginator = Paginator(logs, 20)
    try:
        page_obj = paginator.get_page(page_num)
    except (ValueError, TypeError):
        page_obj = paginator.get_page(1)

    # Distinct action types for filter dropdown
    action_types = sorted(
        AuditLog.objects.values_list("action_type", flat=True).distinct()
    )

    filter_parts = []
    if user_filter:
        filter_parts.append(f"user={user_filter}")
    if action_filter:
        filter_parts.append(f"action_type={action_filter}")
    if date_from:
        filter_parts.append(f"date_from={date_from}")
    if date_to:
        filter_parts.append(f"date_to={date_to}")
    if search:
        filter_parts.append(f"search={search}")
    filter_qs = "&".join(filter_parts)

    context = {
        "logs": page_obj,
        "action_types": action_types,
        "filters": {
            "user": user_filter,
            "action_type": action_filter,
            "date_from": date_from,
            "date_to": date_to,
            "search": search,
        },
        "filter_qs": f"&{filter_qs}" if filter_qs else "",
    }
    return render(request, "audit_logs.html", context)


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
        request.session.pop("parsed_files", None)

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
            if not file.name.endswith((".xlsx", ".csv", ".pdf", ".txt")):
                messages.error(request, f"{file.name} is not supported.")
                continue

            uploaded_file = UploadedFile.objects.create(
                user=request.user, template=template, file=file, status="Processing"
            )

            try:
                file.seek(0)

                # ---------- Excel / CSV files ----------
                if file.name.endswith(".csv") or file.name.endswith(".xlsx"):
                    if file.name.endswith(".csv"):
                        df = pd.read_csv(file)
                    else:
                        df = pd.read_excel(file)

                    print("=" * 50)
                    print(f"File: {file.name}")
                    print("Original columns:", list(df.columns))
                    print("Original shape:", df.shape)

                    # Apply preprocessing
                    df = preprocess_dataframe(df)
                    df = remove_empty_unnamed_columns(df)

                    print("After cleaning columns:", list(df.columns))
                    print("After cleaning shape:", df.shape)

                    if df.empty:
                        uploaded_file.status = "Failed"
                        uploaded_file.save()
                        messages.error(request, f"{file.name} has no valid data.")
                        continue

                    preview_data = df.fillna("").values.tolist()
                    columns = list(df.columns)
                    detected_types = detect_column_types(df)
                    print("Detected types:", detected_types)

                    uploaded_file.status = "Completed"
                    uploaded_file.processed_time = timezone.now()
                    uploaded_file.save()

                    validate_excel_data(uploaded_file)

                    parsed_files.append(
                        {
                            "id": uploaded_file.id,
                            "file_name": file.name,
                            "preview_data": preview_data,
                            "columns": columns,
                            "detected_types": detected_types,
                        }
                    )

                    AuditLog.objects.create(
                        user=request.user,
                        action_type="File Upload",
                        details=f"Successfully uploaded and parsed: {file.name} | Domain: {selected_domain}",
                    )

                    success_count += 1

                # ---------- PDF / TXT files (AI conversion) ----------
                else:
                    used_fallback = False
                    try:
                        # Extract text
                        if file.name.endswith('.pdf'):
                            raw_text = extract_text_from_pdf(file)
                        else:  # .txt
                            file.seek(0)
                            raw_text = file.read().decode('utf-8', errors='ignore')

                        if not raw_text.strip():
                            raise ValueError("No text extracted from file")

                        # Try AI first
                        csv_data = call_ai_to_csv(raw_text)
                        rows = parse_csv_to_rows(csv_data)
                        if not rows:
                            raise ValueError("AI returned empty table")
                    except Exception as ai_error:
                        # AI failed – use fallback parser
                        print(f"AI failed: {ai_error}, using fallback parser")
                        used_fallback = True
                        # Simple fallback: split lines by whitespace
                        fallback_rows = []
                        for line in raw_text.strip().splitlines():
                            if line.strip():
                                cols = line.split()
                                if cols:
                                    fallback_rows.append(cols)
                        if not fallback_rows:
                            raise ValueError("Fallback could not parse text")
                        # Assume first row is header
                        rows = fallback_rows

                    # Convert rows to DataFrame
                    if len(rows) > 0:
                        df = pd.DataFrame(rows[1:], columns=rows[0])  # first row as header
                    else:
                        raise ValueError("No data rows")

                    # Apply preprocessing
                    df = preprocess_dataframe(df)
                    df = remove_empty_unnamed_columns(df)

                    if df.empty:
                        raise ValueError("No valid data after preprocessing")

                    # Save as Excel
                    excel_buffer = BytesIO()
                    df.to_excel(excel_buffer, index=False)
                    excel_buffer.seek(0)
                    base_name = file.name.rsplit('.', 1)[0]
                    excel_name = f"{base_name}_converted.xlsx"
                    uploaded_file.file.save(excel_name, ContentFile(excel_buffer.getvalue()))
                    uploaded_file.status = "Completed"
                    uploaded_file.processed_time = timezone.now()
                    uploaded_file.save()

                    # Generate preview data
                    preview_data = df.fillna("").values.tolist()
                    columns = list(df.columns)
                    detected_types = detect_column_types(df)

                    # Validate using existing rules
                    validate_excel_data(uploaded_file)

                    parsed_files.append({
                        "id": uploaded_file.id,
                        "file_name": excel_name,
                        "preview_data": preview_data,
                        "columns": columns,
                        "detected_types": detected_types,
                    })

                    # Log with fallback info
                    if used_fallback:
                        AuditLog.objects.create(
                            user=request.user,
                            action_type="File Upload",
                            details=f"Converted {file.name} using FALLBACK parser (AI failed) | Domain: {selected_domain}",
                        )
                        messages.warning(request, f"{file.name}: AI service unavailable. Used basic text parser. Table may be less accurate.")
                    else:
                        AuditLog.objects.create(
                            user=request.user,
                            action_type="File Upload",
                            details=f"Converted {file.name} to structured Excel using AI | Domain: {selected_domain}",
                        )
                    continue   # skip the Excel/CSV processing below (already handled)

            except Exception as e:
                uploaded_file.status = "Failed"
                uploaded_file.save()
                AuditLog.objects.create(
                    user=request.user,
                    action_type="Upload Error",
                    details=f"Failed to process {file.name}: {str(e)}",
                )
                messages.error(request, f"{file.name} failed to process.")

        # Remove original text/PDF files from preview (keep only converted Excel)
        parsed_files = [item for item in parsed_files if not item['file_name'].lower().endswith(('.txt', '.pdf'))]
        request.session["parsed_files"] = parsed_files

        if success_count > 0:
            messages.success(request, "File(s) processed successfully.")

        return redirect("upload_file")

    parsed_files = request.session.get("parsed_files", None)

    # Hide latest_upload if we have parsed_files to avoid double preview
    if parsed_files:
        latest_upload = None
    elif not latest_upload:
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
    if request.user.is_staff:
        uploaded_file = get_object_or_404(UploadedFile, id=file_id)
    else:
        uploaded_file = get_object_or_404(UploadedFile, id=file_id, user=request.user)

    results = ValidationResult.objects.filter(file=uploaded_file, is_valid=False)

    try:
        file_path = uploaded_file.file.path
        if file_path.endswith(".csv"):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)

        df = remove_empty_unnamed_columns(df)

        total_rows = len(df)

        score = calculate_quality_score(uploaded_file, total_rows)
        recommendations = get_formula_recommendations(uploaded_file, df.columns)

    except Exception as e:
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

    return JsonResponse({"explanation": explanation, "ai_used": ai_success}, status=200)


@login_required
def download_excel_view(request, file_id):
    if request.user.is_staff:
        uploaded_file = get_object_or_404(UploadedFile, id=file_id)
    else:
        uploaded_file = get_object_or_404(UploadedFile, id=file_id, user=request.user)

    file_path = uploaded_file.file.path.lower()
    style = request.GET.get("style", "")
    

    if file_path.endswith(".pdf") or file_path.endswith(".txt"):
        return HttpResponse(
            "Download not available for this file type.",
            content_type="text/plain"
        )


    if file_path.endswith(".csv"):
        df = pd.read_csv(file_path)
    else:
        df = pd.read_excel(file_path)
    
    # remove empty rows (match preview)
    df = df.dropna(how="all")
    df = df[df.count(axis=1) > 0]
    df = df.reset_index(drop=True)

    
    from openpyxl import Workbook
    from openpyxl.utils.dataframe import dataframe_to_rows
    from openpyxl.worksheet.table import Table, TableStyleInfo

    wb = Workbook()
    ws = wb.active

    # write dataframe to sheet
    for r in dataframe_to_rows(df, index=False, header=True):
        ws.append(r)
    from openpyxl.styles import Font, PatternFill

    style_data = getattr(uploaded_file, "style_data", None)

    # --- TRACKER FOR DOWNLOAD ---
    print("\n" + "="*50)
    print("📥 STEP DOWNLOAD: Attempting to apply styles to Excel.")
    print("Style Data exists?:", style_data is not None)

    
    if isinstance(style_data, str) and style_data.strip():
        try:
            # Try standard JSON first
            style_data = json.loads(style_data)
        except Exception:
            try:
                style_data = ast.literal_eval(style_data)
            except Exception as e:
                print(f"AST Error in Download: {e}")
                style_data = None


    # Helper function to convert color to aRGB format
    def convert_to_argb(color_value):
        """Convert various color formats to openpyxl aRGB format (8 hex chars)"""
        if not color_value:
            return None
        
        # Remove any # prefix and convert to string
        color_str = str(color_value).strip()
        if color_str.startswith('#'):
            color_str = color_str[1:]
        
        # Remove rgb() or rgba() if present
        if color_str.startswith('rgb'):
            import re
            rgb_match = re.search(r'rgb\((\d+),\s*(\d+),\s*(\d+)\)', color_str)
            if rgb_match:
                r, g, b = int(rgb_match.group(1)), int(rgb_match.group(2)), int(rgb_match.group(3))
                return f"FF{r:02x}{g:02x}{b:02x}".upper()
        
        # If it's 6 hex characters, add FF prefix for alpha
        if len(color_str) == 6 and all(c in '0123456789ABCDEFabcdef' for c in color_str):
            return f"FF{color_str.upper()}"
        
        # If it's 3 hex characters (like F00), expand to 6
        if len(color_str) == 3 and all(c in '0123456789ABCDEFabcdef' for c in color_str):
            expanded = ''.join([c*2 for c in color_str])
            return f"FF{expanded.upper()}"
        
        # If it's already 8 hex characters, use as is
        if len(color_str) == 8 and all(c in '0123456789ABCDEFabcdef' for c in color_str):
            return color_str.upper()
        
        # Default to black with full opacity
        return "FF000000"

    user_bg_cells = set()
    if style_data:
        for row_idx, row in enumerate(style_data, start=2):  # +2 because of header row (1-indexed, row 1 is header)
            for col_idx, cell in enumerate(row, start=1):
                if isinstance(cell, dict):
                    excel_cell = ws.cell(row=row_idx, column=col_idx)

                    # Handle font color
                    font_color = None
                    if cell.get("color"):
                        font_color = convert_to_argb(cell.get("color"))

                    # Handle font family (take first in CSS stack, strip quotes)
                    font_name = None
                    if cell.get("fontFamily"):
                        font_name = cell.get("fontFamily").split(",")[0].strip().strip("'\"")

                    # Handle font size (convert px to pt: pt = px * 0.75)
                    font_size = None
                    if cell.get("fontSize"):
                        try:
                            px_val = float(str(cell.get("fontSize")).replace("px", "").strip())
                            font_size = round(px_val * 0.75, 1)
                        except (ValueError, TypeError):
                            font_size = None

                    underline_val = cell.get("underline")
                    if underline_val == "double":
                        underline_style = "double"
                    elif underline_val == "single":
                        underline_style = "single"
                    else:
                        underline_style = None

                    excel_cell.font = Font(
                        bold=cell.get("bold", False),
                        italic=cell.get("italic", False),
                        underline=underline_style,
                        color=font_color,
                        name=font_name,
                        size=font_size
                    )

                    # Handle background color
                    if cell.get("bg"):
                        bg_color = convert_to_argb(cell.get("bg"))
                        excel_cell.fill = PatternFill(
                            start_color=bg_color,
                            end_color=bg_color,
                            fill_type="solid"
                        )
                        user_bg_cells.add((row_idx, col_idx))

    # Apply theme colors manually to match the CSS preview exactly
    THEME_STYLES = {
        "light":  {"header_bg": "FFF1F5F9", "header_fg": "FF1A1A2E", "alt_bg": "FFF8FAFC"},
        "medium": {"header_bg": "FF5B9BD5", "header_fg": "FFFFFFFF", "alt_bg": "FFDEEAF6"},
        "dark":   {"header_bg": "FF203864", "header_fg": "FFFFFFFF", "alt_bg": "FFD9E1F2"},
    }

    if style in THEME_STYLES:
        theme = THEME_STYLES[style]
        # Apply header row
        for cell in ws[1]:
            cell.fill = PatternFill(start_color=theme["header_bg"], end_color=theme["header_bg"], fill_type="solid")
            cell.font = Font(bold=True, color=theme["header_fg"])
        # Apply alternating rows — skip cells that have a user-defined background
        for row_idx in range(2, ws.max_row + 1):
            if row_idx % 2 == 0:
                for cell in ws[row_idx]:
                    if (row_idx, cell.column) not in user_bg_cells:
                        cell.fill = PatternFill(start_color=theme["alt_bg"], end_color=theme["alt_bg"], fill_type="solid")

    # Add table (keeps filter arrows; no built-in table style since we apply colors manually above)
    from openpyxl.utils import get_column_letter

    end_col = get_column_letter(len(df.columns))
    end_row = len(df) + 1
    table = Table(displayName="Table1", ref=f"A1:{end_col}{end_row}")
    ws.add_table(table)
    # make header bold
    
    for col in ws.columns:
        max_length = 0
        col_letter = col[0].column_letter

        for cell in col:
            try:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            except:
                pass

        ws.column_dimensions[col_letter].width = max_length + 2
    # save
    from io import BytesIO
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    response = HttpResponse(
        output,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    filename = uploaded_file.file.name.split("/")[-1].replace(".csv", "").replace(".xlsx", "")
    response["Content-Disposition"] = f'attachment; filename="{filename}_processed.xlsx"'

    return response

@login_required
def preview_excel_view(request, file_id):
    if request.user.is_staff:
        uploaded_file = get_object_or_404(UploadedFile, id=file_id)
    else:
        uploaded_file = get_object_or_404(UploadedFile, id=file_id, user=request.user)

    file_path = uploaded_file.file.path

    if file_path.endswith(".csv"):
        df = pd.read_csv(file_path)
    else:
        df = pd.read_excel(file_path)

    df = preprocess_dataframe(df)
    df = remove_empty_unnamed_columns(df)

    
    df.columns = [str(col).replace("_", " ").title() for col in df.columns]

    # auto width simulation (important)
    df = df.fillna("")

    # Inside preview_excel_view
    style_data = getattr(uploaded_file, "style_data", None)

    # --- STEP 4 TRACKER: LOADING FOR PREVIEW ---
    print("\n" + "="*50)
    print("🟢 STEP 4 (PYTHON PREVIEW): Pulled style_data from DB.")
    print("Type pulled from DB:", type(style_data))
    print("Raw data check:", str(style_data)[:100])
    
    # --- THE BULLETPROOF PARSER we added earlier ---
    if isinstance(style_data, str) and style_data.strip():
        try:
            style_data = json.loads(style_data)
            print("✅ STEP 4a: json.loads() worked!")
        except Exception as e1:
            print(f"⚠️ STEP 4a: json.loads() failed: {e1}")
            try:
                style_data = ast.literal_eval(style_data)
                print("✅ STEP 4b: ast.literal_eval() worked!")
            except Exception as e2:
                print(f"❌ STEP 4b: AST failed too! Error: {e2}")
                style_data = None
    
    print("Final style_data type before rendering:", type(style_data))
    print("="*50 + "\n")

    html = '<table class="excel-table">'

    # HEADER
    html += '<thead><tr>'
    for col in df.columns:
        html += f'<th>{col}</th>'
    html += '</tr></thead><tbody>'

    # ROWS
    for i, row in enumerate(df.values):
        html += '<tr>'
    
        for j, val in enumerate(row):
            style_attr = ""

            if style_data and i < len(style_data) and j < len(style_data[i]):
                cell = style_data[i][j]

                if isinstance(cell, dict):
                    styles = []

                    if cell.get("bold"):
                        styles.append("font-weight:bold")
                    if cell.get("italic"):
                        styles.append("font-style:italic")
                    underline_val = cell.get("underline")
                    if underline_val:
                        if underline_val == "double":
                            styles.append("text-decoration:underline double")
                        else:
                            styles.append("text-decoration:underline")
                        
                    if cell.get("color"):
                        styles.append(f"color:{cell.get('color')}")
                    if cell.get("bg"):
                        styles.append(f"background:{cell.get('bg')}")
                    if cell.get("fontFamily"):
                        styles.append(f"font-family:{cell.get('fontFamily')}")
                    if cell.get("fontSize"):
                        styles.append(f"font-size:{cell.get('fontSize')}")

                    style_attr = f' style="{";".join(styles)}"'

            html += f'<td{style_attr}>{val}</td>'

        html += '</tr>'

    html += '</tbody></table>'

    table_html = html

    return JsonResponse({"table": table_html})


@login_required
def workbook_list_view(request):
    all_files = UploadedFile.objects.filter(user=request.user).order_by("-upload_time")
    
    original_files = []
    edited_files = []
    
    for f in all_files:
        if f.column_mappings or "_edited" in f.file.name:
            edited_files.append(f)
        else:
            original_files.append(f)
    
    return render(request, "workbook_list.html", {
        "original_files": original_files,
        "edited_files": edited_files,
    })