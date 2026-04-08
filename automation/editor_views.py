import re
import json
import os
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
    
    saved_mappings = getattr(uploaded_file, 'column_mappings', {})
    
    try:
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)
        
        df = preprocess_dataframe(df)
        df = remove_empty_unnamed_columns(df)
        df = df.dropna(how='all')
        df = df.reset_index(drop=True)
        
        user_columns_original = list(df.columns)
        
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