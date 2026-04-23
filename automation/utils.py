import io
import json
import os
import pandas as pd
import requests
import re
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill


def ai_match_columns(file_columns, db_columns, api_key=None, api_url=None, model=None):
    """
    Use Groq/OpenAI API to find best matches between file columns and DB columns.
    Returns a dict: {file_column: best_db_column} for columns where confidence > threshold.
    """
    if not file_columns or not db_columns:
        return {}
    
    api_key = api_key or os.environ.get("AI_API_KEY")
    api_url = api_url or os.environ.get("AI_API_URL", "https://api.groq.com/openai/v1/chat/completions")
    model = model or os.environ.get("AI_MODEL", "llama3-70b-8192")
    
    if not api_key:
        print("AI column matching skipped: no API key")
        return {}
    
    prompt = f"""You are a data mapping expert. Match each column from the user's file to the most suitable column from the database schema.
User file columns: {file_columns}
Database expected columns: {db_columns}

Return ONLY a JSON object mapping each user column to the best matching database column. Use exact strings from the lists.
If no good match exists, map to null.
Example output: {{"Student Name": "full_name", "ID": "student_id", "Extra": null}}

Now return the JSON mapping."""
    
    try:
        response = requests.post(
            api_url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "response_format": {"type": "json_object"}
            },
            timeout=15
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        # Extract JSON from response (sometimes markdown wrapped)
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        mapping = json.loads(content)
        # Validate keys are in file_columns, values in db_columns or null
        valid_mapping = {}
        for fc in file_columns:
            if fc in mapping and mapping[fc] in db_columns:
                valid_mapping[fc] = mapping[fc]
        return valid_mapping
    except Exception as e:
        print(f"AI column matching failed: {e}")
        return {}

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
    import pandas as pd
    from .models import ValidationRule, FormulaRule, ValidationResult

    file_path = uploaded_file_obj.file.path
    df = (
        pd.read_csv(file_path)
        if file_path.endswith(".csv")
        else pd.read_excel(file_path)
    )
    df = df.loc[:, ~df.columns.astype(str).str.contains("^Unnamed")]

    template = uploaded_file_obj.template
    rules = ValidationRule.objects.filter(template=template)
    formula_rules = FormulaRule.objects.filter(template=template)
    ValidationResult.objects.filter(file=uploaded_file_obj).delete()

    print(f"Validating file: {uploaded_file_obj.file.name}")
    print(f"DataFrame columns: {list(df.columns)}")
    print(f"Number of validation rules: {rules.count()}")
    print(f"Number of formula rules: {formula_rules.count()}")

    for index, row in df.iterrows():
        # Keep track of which columns already failed so we don't double-report!
        failed_columns_for_row = set()

        # =========================================================
        # 1. BUILD ROBUST ROW CONTEXT (REFINED)
        # =========================================================
        row_context = {}
        # Get the mappings the user saved in the UI
        saved_mappings = getattr(uploaded_file_obj, "column_mappings", {})

        for key, val_str in row.items():
            if pd.isna(key) or str(key).strip() == "": 
                continue
            
            # Clean the value
            if pd.isna(val_str) or val_str == "":
                parsed_val = 0 # Default to 0 for math safety
            else:
                raw_str = str(val_str).strip()
                try:
                    parsed_val = float(raw_str)
                except:
                    parsed_val = raw_str

            # A. Add the original name (and variants) to context
            clean_key = str(key).replace(" ", "")
            row_context[clean_key] = parsed_val
            row_context[clean_key.title()] = parsed_val
            
            # B. CRITICAL: Add the MAPPED name to context
            # If the file has '10sqrtx' and it's mapped to 'Bonus', 
            # this adds 'Bonus' to the context so eval() can find it!
            if key in saved_mappings:
                db_name = saved_mappings[key]
                row_context[db_name] = parsed_val
        
        # DEBUG PRINT: Run this once and check your terminal 
        # to see if 'Bonus' is actually in this list!
        # print(f"Row Context Keys: {row_context.keys()}")

        # =========================================================
        # 2. LOGIC VALIDATION
        # =========================================================
        for rule in rules:
            actual_col = find_best_column(rule.column_name, df.columns)
            if actual_col:
                raw_val = row[actual_col]

                if pd.isna(raw_val) or raw_val == "":
                    val = 0 if ("<" in rule.condition_expression or ">" in rule.condition_expression) else ""
                else:
                    try:
                        if "date" in str(actual_col).lower():
                            val = pd.to_datetime(raw_val, errors="coerce")
                        else:
                            val = float(raw_val)
                    except:
                        val = str(raw_val).strip()

                try:
                    allowed_locals = {"x": val, "index": index}
                    allowed_locals.update(row_context)

                    allowed_globals = {
                        "__builtins__": None,
                        "str": str, "int": int, "float": float,
                        "len": len, "abs": abs, "round": round,
                    }

                    if not eval(rule.condition_expression, allowed_globals, allowed_locals):
                        ValidationResult.objects.create(
                            file=uploaded_file_obj,
                            row_index=index + 1,
                            column_name=actual_col,
                            error_details=rule.error_message,
                            is_valid=False,
                        )
                        # Mark this column as failed so the Formula Audit ignores it!
                        failed_columns_for_row.add(actual_col)
                        print(f"  -> Validation failed for row {index+1}, column {actual_col}")
                except Exception as e:
                    print(f"  -> Logic Error evaluating rule '{rule.rule_name}' on col '{actual_col}': {e}")
                    continue

        # =========================================================
        # 3. FORMULA AUDIT
        # =========================================================
        for f_rule in formula_rules:
            actual_target_col = find_best_column(f_rule.target_column, df.columns)
            
            # Skip this formula check if a Logic Validation rule already failed for this exact cell
            if actual_target_col and actual_target_col not in failed_columns_for_row:
                try:
                    excel_val = row[actual_target_col]
                    
                    safe_formula_context = {k: (0 if v == "" else v) for k, v in row_context.items()}
                    
                    expected_val = eval(
                        f_rule.condition_expression, {"__builtins__": None}, safe_formula_context
                    )
                    
                    # Clean up the display values so it says "Empty" instead of "nan"
                    display_excel_val = "Empty" if pd.isna(excel_val) or str(excel_val).strip() == "" else str(excel_val).strip()
                    display_expected_val = str(expected_val).strip()

                    if display_excel_val != display_expected_val:
                        ValidationResult.objects.create(
                            file=uploaded_file_obj,
                            row_index=index + 1,
                            column_name=actual_target_col,
                            error_details=f"Math Error: Expected {display_expected_val}, found {display_excel_val}.",
                            is_valid=False,
                        )
                        print(f"  -> Formula mismatch for row {index+1}, column {actual_target_col}")
                except Exception as e:
                    print(f"  -> Error in formula audit for '{f_rule.target_column}': {e}")
                    continue

def get_formula_recommendations(uploaded_file_obj, df_columns):
    from .models import FormulaRule, ValidationRule
    from .utils import preprocess_dataframe, remove_empty_unnamed_columns, ai_match_columns, find_best_column
    import pandas as pd

    template = uploaded_file_obj.template
    validation_cols = set(ValidationRule.objects.filter(template=template).values_list('column_name', flat=True))
    formula_cols = set(FormulaRule.objects.filter(template=template).values_list('target_column', flat=True))
    all_domain_cols = validation_cols.union(formula_cols)

    # Load the actual DataFrame to check column content
    file_path = uploaded_file_obj.file.path
    if file_path.endswith('.csv'):
        df = pd.read_csv(file_path)
    else:
        df = pd.read_excel(file_path)
    
    df = df.loc[:, ~df.columns.astype(str).str.contains("^Unnamed")]
    df = preprocess_dataframe(df)
    df = remove_empty_unnamed_columns(df)

    actual_columns = list(df.columns)

    saved_mappings = getattr(uploaded_file_obj, "column_mappings", {})
    
    reverse_map = {}
    
    if saved_mappings:
        for file_col, db_col in saved_mappings.items():
            reverse_map[db_col] = file_col
    else:
        if actual_columns and all_domain_cols:
            ai_mapping = ai_match_columns(actual_columns, list(all_domain_cols))
            for file_col, db_col in ai_mapping.items():
                reverse_map[db_col] = file_col

    recommendations = []
    for domain_col in all_domain_cols:
        # Check if column exists (via user mapping, AI mapping, or fuzzy text match)
        actual_col = reverse_map.get(domain_col) or find_best_column(domain_col, actual_columns)
        exists = actual_col is not None

        if not exists:
            formula_rule = FormulaRule.objects.filter(template=template, target_column=domain_col).first()
            if formula_rule:
                formula = formula_rule.condition_expression
                message = f"Suggested: Create '{domain_col}' column. Use the formula below to calculate it."
            else:
                formula = "None (Manual Data Entry)" 
                message = f"Suggested: Create '{domain_col}' column (required for validation)."
            
            recommendations.append({"column": domain_col, "formula": formula, "message": message})
            
    return recommendations

def calculate_quality_score(uploaded_file_obj, total_rows):
    # FIX: Added local import
    from .models import ValidationResult

    error_rows_count = (
        ValidationResult.objects.filter(file=uploaded_file_obj, is_valid=False)
        .values("row_index")
        .distinct()
        .count()
    )

    if total_rows == 0:
        return 0

    success_rows = total_rows - error_rows_count
    score = (success_rows / total_rows) * 100
    return round(score, 2)


def generate_ai_explanation(
    formula_name, target_column, condition_expression, context_data=None
):
    # Try AI API call first
    ai_api_key = os.environ.get("AI_API_KEY")
    ai_api_url = os.environ.get(
        "AI_API_URL", "https://api.openai.com/v1/chat/completions"
    )
    ai_model = os.environ.get("AI_MODEL", "gpt-3.5-turbo")

    if ai_api_key:
        try:
            prompt = (
                f"You are a data analyst explaining spreadsheet formulas in simple, clear terms. Be concise and use bullet points for different aspects. Now, explain this validation error in simple terms, do not write anything extra things, just write the explanation starting with 'Explanation of that validation error: ':\n"
                f"Rule: {formula_name}\n"
                f"Column: {target_column}\n"
                f"Condition: {condition_expression}"
            )
            if context_data:
                prompt += f"\nContext: {context_data}"

            response = requests.post(
                ai_api_url,
                headers={
                    "Authorization": f"Bearer {ai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": ai_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 200,
                },
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip(), True
        except Exception as e:
            print(f"AI API call failed: {e}")

    # Fallback: rule-based explanation
    if "Math Error" in condition_expression:
        explanation = (
            f"**Logic Mismatch Detected:** The value in `{target_column}` doesn't align with the "
            f"calculated results for `{formula_name}`. The system found a manual discrepancy "
            "against the standard formula."
        )
    elif any(
        x in condition_expression.lower()
        for x in ["exceed", "between", "limit", "<=", ">="]
    ):
        numbers = re.findall(r"\d+", condition_expression)
        if numbers:
            max_val = max(map(int, numbers))
            min_val = min(map(int, numbers)) if len(numbers) > 1 else 0
            explanation = (
                f"**Boundary Violation:** The entry for `{target_column}` is invalid. "
                f"The value must be between **{min_val} and {max_val}**."
            )
        else:
            explanation = f"**Boundary Violation:** The value in `{target_column}` exceeds the limit."
    else:
        explanation = (
            f"**System Validation:** The `{target_column}` field failed the `{formula_name}` "
            f"verification. Logic checked: *{condition_expression}*."
        )

    if context_data:
        explanation += f"\n\n**Context Found:** " + ", ".join(
            f"`{k}={v}`" for k, v in context_data.items()
        )

    return explanation.strip(), False


def preprocess_dataframe(df):
    # clean column names
    df.columns = [str(col).strip().lower().replace(" ", "_") for col in df.columns]

    # replace empty strings with NaN
    df.replace(r"^\s*$", pd.NA, regex=True, inplace=True)

    # trim values
    for col in df.columns:
        # This works whether it's a Series or a DataFrame with one column
        if pd.api.types.is_object_dtype(df[col]):
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace("nan", pd.NA)

    # remove fully empty rows
    df = df.dropna(how="all")

    # remove rows with only 1 value
    df = df[df.count(axis=1) > 1]

    df = df.reset_index(drop=True)

    return df


def remove_empty_unnamed_columns(df):
    return df.loc[
        :,
        ~(
            df.columns.astype(str).str.lower().str.contains("unnamed")
            & (df.isna().sum() == len(df))
        ),
    ]
