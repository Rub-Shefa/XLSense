import re
import json
import os
import ast
import pandas as pd
from io import BytesIO
import difflib

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.core.files.base import ContentFile

# Import your models and utils
from .models import UploadedFile, ValidationRule, FormulaRule
from .utils import preprocess_dataframe, remove_empty_unnamed_columns


@login_required
def workbook_editor_view(request, file_id):
    uploaded_file = get_object_or_404(UploadedFile, id=file_id, user=request.user)
    template = uploaded_file.template
    file_path = uploaded_file.file.path

    # Get domain columns
    val_cols = list(
        ValidationRule.objects.filter(template=template).values_list(
            "column_name", flat=True
        )
    )
    form_cols = list(
        FormulaRule.objects.filter(template=template).values_list(
            "target_column", flat=True
        )
    )
    db_columns = list(set(val_cols + form_cols))

    # Smart normalization function
    def normalize(col):
        col = str(col).lower()
        col = re.sub(r"[ _()%\.\-/]", "", col)
        return col

    def find_matching_db_column(file_col, db_columns):
        file_norm = normalize(file_col)

        for db_col in db_columns:
            db_norm = normalize(db_col)

            # 1. Exact match
            if db_norm == file_norm:
                return db_col

            # 2. Substring match
            if db_norm in file_norm or file_norm in db_norm:
                return db_col

            # 3. Dynamic similarity match (Catches typos and overlaps)
            similarity = difflib.SequenceMatcher(None, db_norm, file_norm).ratio()
            if similarity >= 0.65:
                return db_col

        return None

    saved_mappings = getattr(uploaded_file, "column_mappings", {})

    try:
        if file_path.endswith(".csv"):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)

        df = preprocess_dataframe(df)
        df = remove_empty_unnamed_columns(df)
        df = df.dropna(how="all")
        df = df.reset_index(drop=True)

        user_columns_original = list(df.columns)
        columns_with_classes = []

        for col in user_columns_original:
            matched_db = find_matching_db_column(col, db_columns)
            if matched_db:
                columns_with_classes.append(
                    {"name": col, "class": "header-matched", "matched_db": matched_db}
                )
            else:
                columns_with_classes.append(
                    {"name": col, "class": "header-custom", "matched_db": None}
                )

        # Add missing domain columns (only if no saved mappings)
        if not saved_mappings:
            matched_cols = [
                c["matched_db"] for c in columns_with_classes if c["matched_db"]
            ]
            for db_col in db_columns:
                if db_col not in matched_cols and db_col not in df.columns:
                    df[db_col] = "-"
                    columns_with_classes.append(
                        {
                            "name": db_col,
                            "class": "header-template-only",
                            "matched_db": None,
                        }
                    )

        current_columns = [c["name"] for c in columns_with_classes]
        preview_data = df.fillna("").values.tolist()

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return HttpResponse(f"Error loading file: {e}")

    # YOUR ORIGINAL, WORKING LOAD LOGIC
    saved_mappings_json = json.dumps(saved_mappings)

    # REMOVED my ast hacks! Django natively loads JSONFields into lists.
    style_data = getattr(uploaded_file, "style_data", [])
    if not style_data: 
        style_data = []
        
    style_data_json = json.dumps(style_data)

    return render(
        request,
        "workbook_editor.html",
        {
            "file": uploaded_file,
            "current_columns": current_columns,
            "columns_with_classes": columns_with_classes,
            "db_columns": db_columns,
            "user_columns": user_columns_original,
            "preview_data": preview_data,
            "saved_mappings_json": saved_mappings_json,
            "style_data_json": style_data_json,
        },
    )


@csrf_exempt
@login_required
def save_workbook_data(request, file_id):
    if request.method == "POST":
        try:
            # --- STEP 2: TRACK DATA COMING FROM JS ---
            data = json.loads(request.body)
            print("\n" + "="*50)
            print("📥 STEP 2 (PYTHON IN): Received data from JS!")
            if data.get("rows"):
                print(f"Sample Row 0 Style Data: {data.get('rows')[0][0]}") # Check first cell of first row
            else:
                print("⚠️ WARNING: 'rows' key is missing or empty in JS payload!")
            
            headers = data.get("headers")
            rows = data.get("rows")
            mappings = data.get("mappings", {})

            # 1. Get the original file
            original_file = get_object_or_404(
                UploadedFile, id=file_id, user=request.user
            )

            # 2. Prevent Pandas Crash
            if len(headers) != len(set(headers)):
                seen = set()
                for i, h in enumerate(headers):
                    if h in seen:
                        headers[i] = f"{h}_{i}"  
                    seen.add(h)

            # 3. Create DataFrame and Align Styles
            clean_rows = []
            aligned_style_data = []

            for i, row in enumerate(rows):
                clean_row = []
                for cell in row:
                    if isinstance(cell, dict):
                        clean_row.append(cell.get("value", cell.get("text", "")))
                    else:
                        clean_row.append(cell)
                
                valid_vals = [v for v in clean_row if pd.notna(v) and str(v).strip() not in ["", "nan", "None"]]
                
                if len(valid_vals) > 1:
                    clean_rows.append(clean_row)
                    aligned_style_data.append(row)

            df = pd.DataFrame(clean_rows, columns=headers)
            
            # --- IMPORTANT: Convert list to JSON string for the DB ---
            style_data = json.dumps(aligned_style_data) 
            
            df = preprocess_dataframe(df)
            df = remove_empty_unnamed_columns(df)
            
            # 4. Generate new filename
            original_name = os.path.basename(original_file.file.name)
            name_part = original_name.replace(".csv", "").replace(".xlsx", "")
            new_filename = f"{name_part}_edited.xlsx"

            # 5. Save to memory safely
            output = BytesIO()
            df.to_excel(output, index=False, engine="openpyxl")
            output.seek(0)

            # 6. Create BRAND NEW object
            # Note: We don't set style_data here yet because file.save() might wipe it
            new_uploaded_file = UploadedFile(
                user=request.user,
                template=original_file.template,
                status="Completed",
                processed_time=timezone.now(),
            )
            
            # 7. Save the physical file first
            # This creates the row in the database and gives us an ID
            new_uploaded_file.file.save(new_filename, ContentFile(output.read()), save=True)

            # --- STEP 3: THE RECOVERY SAVE ---
            # Now that the file is safely on the disk, we FORCE the data into the DB
            print(f"💾 STEP 3: Forcing styles into New File ID: {new_uploaded_file.id}")
            
            # Use .update() to bypass any Django model-saving weirdness
            UploadedFile.objects.filter(id=new_uploaded_file.id).update(
                style_data=style_data,
                column_mappings=mappings
            )

            # Verify for the logs
            new_uploaded_file.refresh_from_db()
            print(f"✅ VERIFIED: DB now holds {len(str(new_uploaded_file.style_data))} characters.")
            print("="*50 + "\n")

            return JsonResponse(
                {"status": "success", "new_file_id": new_uploaded_file.id}
            )

        except Exception as e:
            print(f"❌ CRITICAL ERROR SAVING WORKBOOK: {str(e)}")
            return JsonResponse({"status": "failed", "error": str(e)}, status=500)

    return JsonResponse({"status": "failed"}, status=400)