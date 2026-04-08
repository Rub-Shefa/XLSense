# automation/selectors.py
from .models import ValidationRule, FormulaRule


def get_rules_for_domain(template_id):
    """
    Fetches all validation and formula rules
    associated with a specific domain template.
    """
    validations = ValidationRule.objects.filter(template_id=template_id)
    formulas = FormulaRule.objects.filter(template_id=template_id)
    return validations, formulas
