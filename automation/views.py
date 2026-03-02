from django.shortcuts import render
# Make sure ALL your models are imported here:
from .models import DomainTemplate, ValidationRule, FormulaRule, AuditLog

def dashboard_view(request):
    # Fetching real data from the database you built!
    logs = AuditLog.objects.all().order_by('-action_timestamp')[:5]
    domain_count = DomainTemplate.objects.count()
    rule_count = ValidationRule.objects.count()

    context = {
        'logs': logs,
        'domain_count': domain_count,
        'rule_count': rule_count,
    }
    return render(request, 'dashboard.html', context)

def manage_templates_view(request):
    selected_template_id = request.GET.get('template_id')
    
    # 1. Fetch all templates (Student Grading, etc.)
    templates = DomainTemplate.objects.all()
    
    validation_rules = []
    formula_rules = []

    if selected_template_id:
        # 2. Filter rules by the specific template selected
        validation_rules = ValidationRule.objects.filter(template_id=selected_template_id)
        formula_rules = FormulaRule.objects.filter(template_id=selected_template_id)
    else:
        # 3. If nothing selected, show everything (initial view)
        validation_rules = ValidationRule.objects.all()
        formula_rules = FormulaRule.objects.all()

    return render(request, 'manage_templates.html', {
        'templates': templates,
        'validation_rules': validation_rules,
        'formula_rules': formula_rules,
        'selected_id': selected_template_id
    })