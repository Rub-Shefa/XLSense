from pyexpat import errors
import re
import json
import os
import ast
import pandas as pd
from io import BytesIO
import difflib
import openpyxl

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.core.files.base import ContentFile

from .models import UploadedFile, ValidationRule, FormulaRule, ValidationResult
from .utils import preprocess_dataframe, remove_empty_unnamed_columns, ai_match_columns, validate_excel_data, get_formula_recommendations

@login_required
def workbook_editor_view(request, file_id):
    uploaded_file = get_object_or_404(UploadedFile, id=file_id, user=request.user)
    template = uploaded_file.template
    file_path = uploaded_file.file.path

    # Get domain columns (same as before)
    val_cols = list(ValidationRule.objects.filter(template=template).values_list("column_name", flat=True))
    form_cols = list(FormulaRule.objects.filter(template=template).values_list("target_column", flat=True))
    db_columns = list(set(val_cols + form_cols))

    def normalize(col):
        col = str(col).lower()
        col = re.sub(r"[ _()%\.\-/]", "", col)
        return col

    def find_matching_db_column(file_col, db_columns):
        file_norm = normalize(file_col)
        for db_col in db_columns:
            db_norm = normalize(db_col)
            if db_norm == file_norm:
                return db_col
            if db_norm in file_norm or file_norm in db_norm:
                return db_col
            similarity = difflib.SequenceMatcher(None, db_norm, file_norm).ratio()
            if similarity >= 0.65:
                return db_col
        return None

    saved_mappings = getattr(uploaded_file, "column_mappings", {})

    try:
        from openpyxl import load_workbook
        wb_formula = load_workbook(file_path, data_only=False)
        ws_formula = wb_formula.active
        wb_value = load_workbook(file_path, data_only=True)
        ws_value = wb_value.active

        # Extract header (first row)
        headers = []
        for cell_f, cell_v in zip(next(ws_formula.iter_rows(min_row=1, max_row=1)), 
                                   next(ws_value.iter_rows(min_row=1, max_row=1))):
            headers.append(cell_v.value if cell_v.value is not None else "")

        # Data rows (from row 2 onward)
        raw_values = []
        raw_formulas = []
        for row_f, row_v in zip(ws_formula.iter_rows(min_row=2), ws_value.iter_rows(min_row=2)):
            val_row = []
            formula_row = []
            for cell_f, cell_v in zip(row_f, row_v):
                val_row.append(cell_v.value if cell_v.value is not None else "")
                if isinstance(cell_f.value, str) and cell_f.value.startswith('='):
                    formula_row.append(cell_f.value)
                else:
                    formula_row.append(None)
            raw_values.append(val_row)
            raw_formulas.append(formula_row)

        # Create DataFrames with proper column names
        df = pd.DataFrame(raw_values, columns=headers)
        formulas_df = pd.DataFrame(raw_formulas, columns=headers)

        # 1. Remove unnamed and fully empty columns
        unnamed_mask = df.columns.astype(str).str.lower().str.contains("unnamed")
        empty_cols = (df.isna().sum() == len(df))
        cols_to_drop = unnamed_mask & empty_cols
        df = df.loc[:, ~cols_to_drop]
        formulas_df = formulas_df.loc[:, ~cols_to_drop]

        # 2. Rename columns (both DataFrames get same new names)
        new_cols = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        df.columns = new_cols
        formulas_df.columns = new_cols

        # 3. Trim string values in df
        for col in df.columns:
            if pd.api.types.is_object_dtype(df[col]):
                df[col] = df[col].astype(str).str.strip()
                df[col] = df[col].replace("nan", pd.NA)

        # 4. Remove rows that are completely empty (all NaN)
        empty_rows = df.isna().all(axis=1)
        empty_rows_arr = empty_rows.values
        df = df[~empty_rows_arr]
        formulas_df = formulas_df[~empty_rows_arr]

        # 5. Remove rows with only one non-empty value
        row_non_na = df.count(axis=1).values  # numpy array
        rows_to_keep = row_non_na > 1
        df = df[rows_to_keep]
        formulas_df = formulas_df[rows_to_keep]

        # Reset index after row removal
        df = df.reset_index(drop=True)
        formulas_df = formulas_df.reset_index(drop=True)

        user_columns_original = list(df.columns)

        columns_with_classes = []
        ai_matches = {}
        if not saved_mappings:
          ai_matches = ai_match_columns(user_columns_original, db_columns)

        # Process user columns
        for col in user_columns_original:
            matched_db = None
            if saved_mappings and col in saved_mappings:
                matched_db = saved_mappings[col]
            elif not saved_mappings and ai_matches.get(col):
                matched_db = ai_matches[col]
            else:
                matched_db = find_matching_db_column(col, db_columns)
            if matched_db:
                columns_with_classes.append({"name": col, "class": "header-matched", "matched_db": matched_db})
            else:
                columns_with_classes.append({"name": col, "class": "header-custom", "matched_db": None})

        # Add missing domain columns (only if no saved mappings)
        if not saved_mappings:
            matched_cols = [c["matched_db"] for c in columns_with_classes if c["matched_db"]]
            for db_col in db_columns:
                if db_col not in matched_cols and db_col not in df.columns:
                    df[db_col] = ""
                    formulas_df[db_col] = None
                    columns_with_classes.append({"name": db_col, "class": "header-template-only", "matched_db": db_col})

        current_columns = [c["name"] for c in columns_with_classes]
        preview_data = df.fillna("").values.tolist()
        formulas_data = formulas_df.fillna("").values.tolist()

    except Exception as e:
        import traceback
        traceback.print_exc()
        return HttpResponse(f"Error loading file: {e}")

    saved_mappings_json = json.dumps(saved_mappings)
    style_data_raw = getattr(uploaded_file, "style_data", [])
    if isinstance(style_data_raw, str) and style_data_raw:
        try:
            style_data = json.loads(style_data_raw)
        except:
            style_data = []
    else:
        style_data = style_data_raw if style_data_raw else []
    style_data_json = json.dumps(style_data)
    formulas_data_json = json.dumps(formulas_data)



    # Run validation on the file (if not already done)
    validate_excel_data(uploaded_file)

    # Get all validation errors for this file
    errors = ValidationResult.objects.filter(file=uploaded_file, is_valid=False)
    errors_data = [
         {
            "row": err.row_index,
            "column": err.column_name,
             "message": err.error_details,
             "id": err.id,
         }
         for err in errors
        ]

    # Get formula recommendations
    recommendations = get_formula_recommendations(uploaded_file, df.columns)
    print("RECOMMENDATIONS FROM BACKEND:", recommendations)

    return render(request, "workbook_editor.html", {
    "file": uploaded_file,
    "current_columns": current_columns,
    "columns_with_classes": columns_with_classes,
    "db_columns": db_columns,
    "user_columns": user_columns_original,
    "preview_data": preview_data,
    "saved_mappings_json": saved_mappings_json,
    "style_data_json": style_data_json,
    "formulas_data_json": formulas_data_json,
    "errors_data_json": json.dumps(errors_data),        
    "recommendations_json": json.dumps(recommendations), 
})


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
                print(f"Sample Row 0 Style Data: {data.get('rows')[0][0]}") 
            else:
                print("⚠️ WARNING: 'rows' key is missing or empty in JS payload!")
            
            headers = data.get("headers")
            rows = data.get("rows")
            print(f"📥 Received rows count: {len(rows)}")
            if rows:
                 print(f"First row first cell sample: {rows[0][0] if rows[0] else 'empty'}")
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
            df = df.fillna('')
            df = df.replace(['nan', 'None', '<NA>'], '', regex=False)
            print(f"🔧 aligned_style_data length: {len(aligned_style_data)}")
            if aligned_style_data:
                print(f"First aligned row first cell: {aligned_style_data[0][0] if aligned_style_data[0] else 'empty'}")
            
            style_data = json.dumps(aligned_style_data)
            print(f"📦 style_data JSON length: {len(style_data)} characters") 
            
            df = preprocess_dataframe(df)
            df = remove_empty_unnamed_columns(df)
            df = df.fillna('')
            df = df.replace(['nan', 'None', '<NA>', '-'], '', regex=False)

            # 4. Generate new filename
            original_name = os.path.basename(original_file.file.name)
            name_part = original_name.replace(".csv", "").replace(".xlsx", "")
            new_filename = f"{name_part}_edited.xlsx"

            # 5. Save to memory safely
            output = BytesIO()
            df.to_excel(output, index=False, engine="openpyxl")
            output.seek(0)
            print(f"Saved style_data length: {len(style_data)}")

            # 6. Create BRAND NEW object
            new_uploaded_file = UploadedFile(
                user=request.user,
                template=original_file.template,
                status="Completed",
                processed_time=timezone.now(),
            )
            
            # 7. Save the physical file first
            new_uploaded_file.file.save(new_filename, ContentFile(output.read()), save=True)

            # --- STEP 3: THE RECOVERY SAVE ---
            print(f"💾 STEP 3: Forcing styles into New File ID: {new_uploaded_file.id}")
            
            UploadedFile.objects.filter(id=new_uploaded_file.id).update(
                style_data=style_data,
                column_mappings=mappings
            )

            # Verify for the logs
            new_uploaded_file.refresh_from_db()
            print(f"✅ VERIFIED: DB now holds {len(str(new_uploaded_file.style_data))} characters.")
            
            # Run validation on the newly saved file
            from .utils import validate_excel_data
            validate_excel_data(new_uploaded_file)
            print(f"Validation called for file ID {new_uploaded_file.id}")
            print("✅ Validation completed for edited file.")
            print("="*50 + "\n")

            return JsonResponse(
                {"status": "success", "new_file_id": new_uploaded_file.id}
            )

        except Exception as e:
            print(f"❌ CRITICAL ERROR SAVING WORKBOOK: {str(e)}")
            return JsonResponse({"status": "failed", "error": str(e)}, status=500)

    return JsonResponse({"status": "failed"}, status=400)