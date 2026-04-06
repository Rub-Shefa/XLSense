import re
import json
import os
import time
from unicodedata import normalize
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

        numeric_converted = pd.to_numeric(sample, errors="coerce")
        numeric_ratio = numeric_converted.notna().sum() / total

        if numeric_ratio > 0.8:
            detected_types[column] = "Numeric"
            continue

        date_converted = pd.to_datetime(sample, errors="coerce", dayfirst=True)
        date_ratio = date_converted.notna().sum() / total

        if date_ratio > 0.7:
            detected_types[column] = "Date"
        elif numeric_ratio > 0.2:
            detected_types[column] = "Mixed"
        else:
            detected_types[column] = "Text"

    return detected_types


# ✅ SMART PREPROCESSING
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
    df = df[df.count(axis=1) > 1]

    df = df.reset_index(drop=True)

    return df


# ✅ SAFE unnamed column remover (ONLY if empty)
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

                if file.name.endswith(".csv"):
                    df = pd.read_csv(file)
                elif file.name.endswith(".xlsx"):
                    df = pd.read_excel(file)
                
                else:
                     # For PDF/TXT — just save, no processing
                    uploaded_file.status = "Completed"
                    uploaded_file.processed_time = timezone.now()
                    uploaded_file.save()

                    parsed_files.append(    
                        {
                        "id": uploaded_file.id,
                        "file_name": file.name,
                        "preview_data": None,
                        "columns": [],
                        "detected_types": None,
                        
                        }
                    )

                    continue

                df = preprocess_dataframe(df)
                df = remove_empty_unnamed_columns(df)

                if df.empty:
                    uploaded_file.status = "Failed"
                    uploaded_file.save()
                    messages.error(request, f"{file.name} has no valid data.")
                    continue

                preview_data = df.fillna("").values.tolist()
                columns = list(df.columns)
                detected_types = detect_column_types(df)

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
    df = df[df.count(axis=1) > 1]
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

    if style_data:
        for row_idx, row in enumerate(style_data, start=2):
            for col_idx, cell in enumerate(row, start=1):
                if isinstance(cell, dict):
                    excel_cell = ws.cell(row=row_idx, column=col_idx)

                    excel_cell.font = Font(
                        bold=cell.get("bold", False),
                        italic=cell.get("italic", False),
                        underline="single" if cell.get("underline") else None,
                        color=cell.get("color").replace("#","") if cell.get("color") else None
                    )

                    if cell.get("bg"):
                        excel_cell.fill = PatternFill(
                            start_color=cell.get("bg").replace("#",""),
                            end_color=cell.get("bg").replace("#",""),
                            fill_type="solid"
                        )
    # table range
    from openpyxl.utils import get_column_letter

    end_col = get_column_letter(len(df.columns))
    end_row = len(df) + 1
    table = Table(displayName="Table1", ref=f"A1:{end_col}{end_row}")

    # style mapping
    style_map = {
        "light": "TableStyleLight9",
        "medium": "TableStyleMedium9",
        "dark": "TableStyleDark2"
    }

    table_style = style_map.get(style)

    style_info = TableStyleInfo(
        name=table_style,
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False
    )

    if table_style:
        style_info = TableStyleInfo(
            name=table_style,
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False
        )
        table.tableStyleInfo = style_info

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
    df = df.astype(str)

    style_data = getattr(uploaded_file, "style_data", None)

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
                    if cell.get("underline"):
                        styles.append("text-decoration:underline")
                    if cell.get("color"):
                        styles.append(f"color:{cell.get('color')}")
                    if cell.get("bg"):
                        styles.append(f"background:{cell.get('bg')}")

                    style_attr = f' style="{";".join(styles)}"'

            html += f'<td{style_attr}>{val}</td>'

        html += '</tr>'

    html += '</tbody></table>'

    table_html = html

    return JsonResponse({"table": table_html})


@login_required
def workbook_list_view(request):
    files = UploadedFile.objects.filter(user=request.user).order_by("-upload_time")
    return render(request, "workbook_list.html", {"files": files})



@login_required
def workbook_editor_view(request, file_id):
    uploaded_file = get_object_or_404(UploadedFile, id=file_id, user=request.user)
    template = uploaded_file.template
    file_path = uploaded_file.file.path
    
    # Get domain columns
    val_cols = list(ValidationRule.objects.filter(template=template).values_list('column_name', flat=True))
    form_cols = list(FormulaRule.objects.filter(template=template).values_list('target_column', flat=True))
    db_columns = list(set(val_cols + form_cols))
    
    # Smart normalization function
    def normalize(col):
        col = str(col).lower()
        col = re.sub(r'[ _()%\.\-/]', '', col)
        return col
    
    def find_matching_db_column(file_col, db_columns):
        file_norm = normalize(file_col)
        for db_col in db_columns:
            db_norm = normalize(db_col)
        
            if file_norm == db_norm:
                return db_col
        
        # Partial match (no length restriction)
            if db_norm in file_norm or file_norm in db_norm:
                return db_col
        
        # Specific rules
            if "attendance" in db_norm and "attendance" in file_norm:
                return db_col
            if "quiz" in db_norm and "quiz" in file_norm:
                return db_col
            if "assignment" in db_norm and "assignment" in file_norm:
                return db_col
            if "mid" in db_norm and "mid" in file_norm:
                return db_col
            if "final" in db_norm and "final" in file_norm:
                return db_col
            if "total" in db_norm and "total" in file_norm:
                return db_col
        return None
    # Load saved column mappings
    saved_mappings = getattr(uploaded_file, 'column_mappings', {})
    
    try:
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)
        
        # ===== ADD THESE LINES FOR PROPER CLEANING =====
        df = preprocess_dataframe(df)
        df = remove_empty_unnamed_columns(df)
        # Remove fully empty rows
        df = df.dropna(how='all')
        df = df.reset_index(drop=True)
        # ===============================================
        
        user_columns_original = list(df.columns)
        
        # Build columns_with_classes with pre-selected mapping
        columns_with_classes = []
        
        for col in user_columns_original:
            matched_db = find_matching_db_column(col, db_columns)
            print(f"DEBUG: Column '{col}' -> matched_db: {matched_db}")  # ADD THIS LINE
            print(f"DEBUG: db_columns list: {db_columns}")
            if matched_db:
                columns_with_classes.append({
                    'name': col, 
                    'class': 'header-matched',
                    'matched_db': matched_db
                })
            else:
                columns_with_classes.append({
                    'name': col, 
                    'class': 'header-custom',
                    'matched_db': None
                })
        
        # Add missing domain columns (only if no saved mappings)
        if not saved_mappings:
            matched_cols = [c['matched_db'] for c in columns_with_classes if c['matched_db']]
            for db_col in db_columns:
                if db_col not in matched_cols and db_col not in df.columns:
                    df[db_col] = "-"
                    columns_with_classes.append({
                        'name': db_col, 
                        'class': 'header-template-only',
                        'matched_db': None
                    })
        
        current_columns = [c['name'] for c in columns_with_classes]
        preview_data = df.fillna("").values.tolist()
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return HttpResponse(f"Error loading file: {e}")
    
    saved_mappings_json = json.dumps(saved_mappings)
    
    return render(request, "workbook_editor.html", {
        "file": uploaded_file,
        "current_columns": current_columns,
        "columns_with_classes": columns_with_classes,
        "db_columns": db_columns,
        "user_columns": user_columns_original,
        "preview_data": preview_data,
        "saved_mappings_json": saved_mappings_json,
    })
@csrf_exempt
@login_required
def save_workbook_data(request, file_id):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            headers = data.get('headers')
            rows = data.get('rows')
            mappings = data.get('mappings', {})
            
            # 1. Get the original file
            original_file = get_object_or_404(UploadedFile, id=file_id, user=request.user)
            
            # 2. Prevent Pandas Crash: Check for duplicate mapped columns
            if len(headers) != len(set(headers)):
                seen = set()
                for i, h in enumerate(headers):
                    if h in seen:
                        headers[i] = f"{h}_{i}" # Rename duplicates (e.g., Name_1, Name_2)
                    seen.add(h)

            # 3. Create DataFrame
            # extract values only
            clean_rows = []

            for row in rows:
                clean_row = []
                for cell in row:
                    if isinstance(cell, dict):
                        clean_row.append(cell.get("value"))
                    else:
                        clean_row.append(cell)
                clean_rows.append(clean_row)

            df = pd.DataFrame(clean_rows, columns=headers)
            style_data = rows
            df = preprocess_dataframe(df)
            df = remove_empty_unnamed_columns(df)
            # 4. Generate new filename
            original_name = os.path.basename(original_file.file.name)
            name_part = original_name.replace('.csv', '').replace('.xlsx', '')
            new_filename = f"{name_part}_edited.xlsx"
            
            # 5. Save to memory safely
            output = BytesIO()
            df.to_excel(output, index=False, engine='openpyxl') # Force openpyxl engine
            output.seek(0)
            
            # 6. FIX: Create BRAND NEW object WITHOUT column_mappings in the arguments
            new_uploaded_file = UploadedFile(
                user=request.user,
                template=original_file.template,
                status="Completed",
                processed_time=timezone.now()
            )
            new_uploaded_file.style_data = style_data
            new_uploaded_file.column_mappings = mappings
            
            # 7. Save the physical file (This also automatically saves the database record)
            new_uploaded_file.file.save(new_filename, ContentFile(output.read()))
            
            return JsonResponse({"status": "success", "new_file_id": new_uploaded_file.id})

        except Exception as e:
            print(f" CRITICAL ERROR SAVING WORKBOOK: {str(e)}")
            return JsonResponse({"status": "failed", "error": str(e)}, status=500)
            
    return JsonResponse({"status": "failed"}, status=400)