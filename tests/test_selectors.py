import pytest
from automation.selectors import get_rules_for_domain


@pytest.mark.django_db
class TestSelectors:
    def test_get_rules_for_domain_returns_rules(
        self, test_template, test_validation_rule, test_formula_rule
    ):
        validation_rules, formula_rules = get_rules_for_domain(test_template.id)
        assert validation_rules.count() == 1
        assert formula_rules.count() == 1
        assert validation_rules.first() == test_validation_rule
        assert formula_rules.first() == test_formula_rule

    def test_get_rules_for_domain_empty(self, test_template):
        validation_rules, formula_rules = get_rules_for_domain(test_template.id)
        assert validation_rules.count() == 0
        assert formula_rules.count() == 0
