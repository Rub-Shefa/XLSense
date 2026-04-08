import io
import json
import os
import pandas as pd
import requests
import re
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill


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
    # FIX: Added local imports to stop the "Undefined Variable" errors
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

    for index, row in df.iterrows():
        # --- PART A: LOGIC VALIDATION ---
        for rule in rules:
            actual_col = find_best_column(rule.column_name, df.columns)
            if actual_col:
                raw_val = row[actual_col]

                if pd.isna(raw_val) or raw_val == "":
                    val = 0
                else:
                    try:
                        # FIX: Added 'coerce' to handle the Date format warning/crash
                        if "date" in str(actual_col).lower():
                            val = pd.to_datetime(raw_val, errors="coerce")
                        else:
                            val = float(raw_val)
                    except:
                        val = str(raw_val)

                try:
                    allowed_locals = {"x": val, "index": index}
                    allowed_globals = {
                        "__builtins__": None,
                        "str": str,
                        "int": int,
                        "float": float,
                        "len": len,
                        "abs": abs,
                        "round": round,
                    }

                    if not eval(
                        rule.condition_expression, allowed_globals, allowed_locals
                    ):
                        ValidationResult.objects.create(
                            file=uploaded_file_obj,
                            row_index=index + 1,
                            column_name=actual_col,
                            error_details=rule.error_message,
                            is_valid=False,
                        )
                except Exception as e:
                    continue

        # --- PART B: FORMULA AUDIT ---
        row_context = {
            str(k).replace(" ", ""): (0 if pd.isna(v) or v == "" else v)
            for k, v in row.items()
        }
        for f_rule in formula_rules:
            actual_target_col = find_best_column(f_rule.target_column, df.columns)
            if actual_target_col:
                try:
                    excel_val = row[actual_target_col]
                    expected_val = eval(
                        f_rule.condition_expression, {"__builtins__": None}, row_context
                    )

                    if str(excel_val).strip() != str(expected_val).strip():
                        ValidationResult.objects.create(
                            file=uploaded_file_obj,
                            row_index=index + 1,
                            column_name=actual_target_col,
                            error_details=f"Math Error: Expected {expected_val}, found {excel_val}.",
                            is_valid=False,
                        )
                except:
                    continue
    return True


def get_formula_recommendations(uploaded_file_obj, df_columns):
    # FIX: Added local import
    from .models import FormulaRule

    template = uploaded_file_obj.template
    all_formula_rules = FormulaRule.objects.filter(template=template)

    recommendations = []
    for rule in all_formula_rules:
        actual_col = find_best_column(rule.target_column, df_columns)
        if not actual_col:
            recommendations.append(
                {
                    "column": rule.target_column,
                    "formula": rule.condition_expression,
                    "message": f"Suggested: Create '{rule.target_column}'. Use the formula below to calculate it.",
                }
            )
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
        if df[col].dtype == "object":
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
