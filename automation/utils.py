import pandas as pd
from .models import ValidationRule, ValidationResult, FormulaRule

def find_best_column(rule_name, excel_columns):
    rule_clean = str(rule_name).strip().lower().replace(" ", "")
    standard_map = {}
    alpha_map = {}
    
    for col in excel_columns:
        c_str = str(col).strip().lower().replace(" ", "")
        c_alpha = "".join(char for char in c_str if char.isalnum())
        standard_map[c_str] = col
        alpha_map[c_alpha] = col

    if rule_clean in standard_map:
        return standard_map[rule_clean]
    
    rule_alpha = "".join(char for char in rule_clean if char.isalnum())
    if rule_alpha in alpha_map:
        return alpha_map[rule_alpha]

    for clean_name, original_name in standard_map.items():
        if rule_clean in clean_name or clean_name in rule_clean:
            return original_name
    return None

def validate_excel_data(uploaded_file_obj):
    file_path = uploaded_file_obj.file.path
    df = pd.read_csv(file_path) if file_path.endswith('.csv') else pd.read_excel(file_path)
    df = df.loc[:, ~df.columns.astype(str).str.contains("^Unnamed")]
    
    template = uploaded_file_obj.template
    rules = ValidationRule.objects.filter(template=template)
    formula_rules = FormulaRule.objects.filter(template=template)
    
    for index, row in df.iterrows():
        # --- PART A: LOGIC VALIDATION ---
        for rule in rules:
            actual_col = find_best_column(rule.column_name, df.columns)
            if actual_col:
                raw_val = row[actual_col]
                
                # SANITIZE VALUE: Ensure it's a number or empty string, NEVER None
                if pd.isna(raw_val) or raw_val == "":
                    val = 0
                else:
                    try:
                        val = float(raw_val)
                    except:
                        val = str(raw_val)
                
                try:
                    # Added 'abs' and 'round' to allowed functions for better logic
                    allowed_locals = {"x": val, "index": index}
                    allowed_globals = {"__builtins__": None, "str": str, "int": int, "float": float, "len": len, "abs": abs, "round": round}
                    
                    if not eval(rule.condition_expression, allowed_globals, allowed_locals):
                        ValidationResult.objects.create(
                            file=uploaded_file_obj,
                            row_index=index + 1,
                            column_name=actual_col,
                            error_details=rule.error_message,
                            is_valid=False
                        )
                except Exception as e:
                    # This prevents the 'NoneType' message from cluttering the report
                    continue 

        # --- PART B: FORMULA AUDIT ---
        row_context = {str(k).replace(" ", ""): (0 if pd.isna(v) or v == "" else v) for k, v in row.items()}
        for f_rule in formula_rules:
            actual_target_col = find_best_column(f_rule.target_column, df.columns)
            if actual_target_col:
                try:
                    excel_val = row[actual_target_col]
                    expected_val = eval(f_rule.condition_expression, {"__builtins__": None}, row_context)
                    
                    if str(excel_val).strip() != str(expected_val).strip():
                        ValidationResult.objects.create(
                            file=uploaded_file_obj,
                            row_index=index + 1,
                            column_name=actual_target_col,
                            error_details=f"Math Error: Expected {expected_val}, found {excel_val}.",
                            is_valid=False
                        )
                except:
                    continue
    return True

def get_formula_recommendations(uploaded_file_obj, df_columns):
    template = uploaded_file_obj.template
    all_formula_rules = FormulaRule.objects.filter(template=template)
    
    recommendations = []
    
    for rule in all_formula_rules:
        actual_col = find_best_column(rule.target_column, df_columns)
        
        if not actual_col:
            recommendations.append({
                "column": rule.target_column,
                "formula": rule.condition_expression, # e.g., "Price * 0.15"
                "message": f"Suggested: Create '{rule.target_column}'. Use the formula below to calculate it based on your other data."
            })
            
    return recommendations

def calculate_quality_score(uploaded_file_obj, total_rows):
    # Get count of unique rows that have at least one error
    error_rows_count = ValidationResult.objects.filter(
        file=uploaded_file_obj, 
        is_valid=False
    ).values('row_index').distinct().count()
    
    if total_rows == 0:
        return 0
        
    success_rows = total_rows - error_rows_count
    score = (success_rows / total_rows) * 100
    return round(score, 2)