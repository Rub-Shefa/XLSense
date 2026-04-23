import os
import pandas as pd
from unittest.mock import patch, MagicMock
from automation.utils import (
    generate_ai_explanation,
    find_best_column,
    validate_excel_data,
    get_formula_recommendations,
    calculate_quality_score,
)
from automation.views import (
    detect_column_types,
    preprocess_dataframe,
    remove_empty_unnamed_columns,
)


class TestFindBestColumn:
    def test_exact_match(self):
        columns = ["Name", "Score", "Total"]
        result = find_best_column("Total", columns)
        assert result == "Total"

    def test_exact_match_cleaned(self):
        columns = ["name", "score", "total"]
        result = find_best_column("Total", columns)
        assert result == "total"

    def test_alphanumeric_match(self):
        columns = ["first_name", "last_name"]
        result = find_best_column("FirstName", columns)
        assert result == "first_name"

    def test_substring_match_rule_in_column(self):
        columns = ["score_total", "bonus"]
        result = find_best_column("total", columns)
        assert result == "score_total"

    def test_substring_match_column_in_rule(self):
        columns = ["total"]
        result = find_best_column("score_total", columns)
        assert result == "total"

    def test_no_match(self):
        columns = ["Name", "Score"]
        result = find_best_column("Total", columns)
        assert result is None


class TestDetectColumnTypes:
    def test_empty_column(self):
        df = pd.DataFrame({"col": [None, None, None]})
        result = detect_column_types(df)
        assert result["col"] == "Empty"

    def test_numeric_column(self):
        df = pd.DataFrame({"col": [1, 2, 3, 4, 5]})
        result = detect_column_types(df)
        assert result["col"] == "Numeric"

    def test_date_column(self):
        df = pd.DataFrame({"col": ["2024-01-01", "2024-01-02", "2024-01-03"]})
        result = detect_column_types(df)
        assert result["col"] == "Date"

    def test_mixed_column(self):
        df = pd.DataFrame({"col": [1, 2, "a", "b", 3]})
        result = detect_column_types(df)
        assert result["col"] == "Mixed"

    def test_text_column(self):
        df = pd.DataFrame({"col": ["a", "b", "c", "d"]})
        result = detect_column_types(df)
        assert result["col"] == "Text"


class TestPreprocessDataframe:
    def test_column_names_cleaned(self):
        df = pd.DataFrame({"  Name ": ["Alice"], "Score Value": [85]})
        result = preprocess_dataframe(df)
        assert "name" in result.columns
        assert "score_value" in result.columns

    def test_string_values_trimmed(self):
        df = pd.DataFrame({"Name": ["  Alice  ", "Bob"], "Score": [85, 90]})
        result = preprocess_dataframe(df)
        assert result.loc[0, "name"] == "Alice"

    def test_empty_rows_removed(self):
        df = pd.DataFrame({"Name": ["Alice", None, "Bob"], "Score": [85, None, 90]})
        result = preprocess_dataframe(df)
        assert len(result) == 2

    def test_single_value_rows_removed(self):
        df = pd.DataFrame({"Name": ["Alice", "Bob"], "Score": [85, None]})
        result = preprocess_dataframe(df)
        assert len(result) == 1
        assert result.iloc[0]["name"] == "Alice"


class TestRemoveEmptyUnnamedColumns:
    def test_removes_empty_unnamed_columns(self):
        df = pd.DataFrame({"Unnamed: 0": [None, None], "Name": ["Alice", "Bob"]})
        result = remove_empty_unnamed_columns(df)
        assert "Unnamed: 0" not in result.columns
        assert "Name" in result.columns

    def test_keeps_non_empty_unnamed_columns(self):
        df = pd.DataFrame({"Unnamed: 0": [1, 2], "Name": ["Alice", "Bob"]})
        result = remove_empty_unnamed_columns(df)
        assert "Unnamed: 0" in result.columns


class TestCalculateQualityScore:
    def test_zero_rows_returns_zero(self, test_uploaded_file):
        result = calculate_quality_score(test_uploaded_file, 0)
        assert result == 0

    def test_all_valid_returns_100(self, test_uploaded_file):
        result = calculate_quality_score(test_uploaded_file, 10)
        assert result == 100.0

    def test_partial_valid(self, test_uploaded_file, test_validation_result):
        result = calculate_quality_score(test_uploaded_file, 10)
        assert 0 <= result <= 100


class TestGetFormulaRecommendations:
    def test_recommendation_for_missing_column(
        self, test_uploaded_file, test_formula_rule
    ):
        df_columns = ["Name", "Score"]
        recommendations = get_formula_recommendations(test_uploaded_file, df_columns)
        assert len(recommendations) == 1
        assert recommendations[0]["column"] == "Total"

    def test_no_recommendation_when_column_exists(
        self, test_uploaded_file, test_formula_rule
    ):
        df_columns = ["Name", "Score", "Total"]
        recommendations = get_formula_recommendations(test_uploaded_file, df_columns)
        assert len(recommendations) == 0


class TestValidateExcelData:
    def test_validate_creates_results_on_failure(
        self, test_uploaded_file_with_file, test_validation_rule
    ):
        result = validate_excel_data(test_uploaded_file_with_file)
        assert result is True


class TestAiExplanation:
    def test_generate_explanation_uses_template_when_no_api(self, remove_api_key):
        result, _ = generate_ai_explanation(
            formula_name="Total Score",
            target_column="Total",
            condition_expression="Score + Bonus",
            context_data={"Score": 85, "Bonus": 10},
        )
        assert result is not None
        assert len(result) > 0
        assert "Total" in result

    def test_generate_explanation_includes_formula_details(self, remove_api_key):
        result, _ = generate_ai_explanation(
            formula_name="Average",
            target_column="Avg",
            condition_expression="(Math + Science) / 2",
            context_data={"Math": 90, "Science": 80},
        )
        assert "Average" in result or "Avg" in result

    def test_generate_explanation_without_context(self, remove_api_key):
        result, _ = generate_ai_explanation(
            formula_name="GPA",
            target_column="GPA",
            condition_expression="sum(grades) / len(grades)",
        )
        assert result is not None
        assert "GPA" in result

    @patch("automation.utils.requests.post")
    def test_api_called_with_correct_payload(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "This formula adds Score and Bonus to get Total."
                    }
                }
            ]
        }
        mock_post.return_value = mock_response

        with patch.dict(
            os.environ,
            {
                "AI_API_KEY": "sk-test123",
                "AI_API_URL": "https://api.example.com/v1/chat/completions",
                "AI_MODEL": "deepseek-v3",
            },
        ):
            result, ai_used = generate_ai_explanation(
                formula_name="Total Score",
                target_column="Total",
                condition_expression="Score + Bonus",
                context_data={"Score": 85, "Bonus": 10},
            )

        assert result == "This formula adds Score and Bonus to get Total."
        assert ai_used is True
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[1]["json"]["model"] == "deepseek-v3"
        assert call_kwargs[1]["headers"]["Authorization"] == "Bearer sk-test123"
        assert call_kwargs[0][0] == "https://api.example.com/v1/chat/completions"

    @patch("automation.utils.requests.post")
    def test_api_falls_back_on_error(self, mock_post, remove_api_key):
        mock_post.side_effect = Exception("Connection refused")

        with patch.dict(os.environ, {"AI_API_KEY": "sk-test123"}):
            result, ai_used = generate_ai_explanation(
                formula_name="Total Score",
                target_column="Total",
                condition_expression="Score + Bonus",
            )

        assert result is not None
        assert "Total" in result
        assert ai_used is False

    def test_fallback_math_error(self, remove_api_key):
        result, _ = generate_ai_explanation(
            formula_name="Total",
            target_column="Total",
            condition_expression="Math Error: Expected 100, found 50.",
        )
        assert "Logic Mismatch" in result or "Math Error" in result

    def test_fallback_boundary_with_numbers(self, remove_api_key):
        result, _ = generate_ai_explanation(
            formula_name="Score Range",
            target_column="Score",
            condition_expression="Score must be between 0 and 100",
        )
        assert "Boundary" in result

    def test_fallback_boundary_without_numbers(self, remove_api_key):
        result, _ = generate_ai_explanation(
            formula_name="Score Range",
            target_column="Score",
            condition_expression="Score exceeds limit",
        )
        assert "Boundary" in result or "exceeds" in result

    def test_fallback_default(self, remove_api_key):
        result, _ = generate_ai_explanation(
            formula_name="Check",
            target_column="Col",
            condition_expression="x > 5",
        )
        assert "System Validation" in result or "failed" in result.lower()

    def test_context_appended_to_fallback(self, remove_api_key):
        result, _ = generate_ai_explanation(
            formula_name="Total",
            target_column="Total",
            condition_expression="Score + Bonus",
            context_data={"Score": 85, "Bonus": 10},
        )
        assert "85" in result or "Score=85" in result
