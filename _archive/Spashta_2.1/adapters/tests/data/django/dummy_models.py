"""
Spashta-CKG – Django Adapter Dummy Test Code (v1)

PURPOSE
-------
This file is part of the Django Adapter test suite for Spashta-CKG.
It is NOT a runnable Django application.

The goal of this code is to provide realistic Django patterns that allow:
- Builders to extract correct Python AST structure
- Adapters to detect Django-specific semantics
- Validators to verify framework rules and contracts

This code intentionally balances realism with simplicity.

WHAT THIS FILE IS (AND IS NOT)
------------------------------
✔ IS:
- Representative Django-style code
- Used for semantic detection testing
- Used to validate adapter framework_mapping.json rules
- Used to test adapter contract enforcement (success + violations)

❌ IS NOT:
- A full Django project
- Intended to run via `manage.py`
- Used for application logic testing
- Expected to be production-correct Django code

SEMANTIC COVERAGE
-----------------
Across the dummy Django files, the following framework concepts are exercised:

- DataModels:
  - Django ORM models inheriting from `models.Model`
- Views:
  - Function-based views (FBV)
  - Class-based views (CBV)
  - Generic class-based views (e.g., ListView)
  - TemplateView usage
- Templates:
  - Explicit `render()` calls
  - TemplateView `template_name`
- Routing:
  - URL patterns via `path()` and `urlpatterns`
- Intentional Violations:
  - Examples that should trigger adapter contract warnings/errors
    (e.g., database access inside a view)

KNOWN & ACCEPTABLE LIMITATIONS (v1)
-----------------------------------
- URL routing detection is partially limited due to builder constraints
  (Call nodes for `path()` are not fully emitted yet).
- Some detections rely on documented heuristics
  (e.g., file path containing `views.py`).
- These limitations are intentional, documented, and will be revisited
  as builders evolve.

HOW THIS FILE IS USED IN THE TEST FLOW
--------------------------------------
This file participates in the following validation pipeline:

    dummy_*.py (models, views, urls)
            ↓
    run_build_django_ast.py        (Runs Python Builder)
            ↓
    test_output_ast.json           (Raw, objective AST)
            ↓
    check_django_mapping_coverage.py
        - Performs mock enrichment
        - Verifies Django semantic detectability
        - Validates adapter rules and assumptions

DESIGN PRINCIPLE
----------------
Builders capture *what exists*.
Adapters explain *what it means*.
Tests verify *what can be safely inferred*.

If you are modifying this file:
- Do NOT add application logic
- Do NOT simplify away real Django patterns
- Do NOT remove intentional violations
- Keep changes aligned with framework_mapping.json

This file exists to protect adapter correctness and agent safety.
"""
from django.db import models

class Customer(models.Model):
    name = models.CharField(max_length=50)
    
    def __str__(self):
        return self.name

class Order(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
