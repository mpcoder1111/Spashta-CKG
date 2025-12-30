"""
views_demo.py - Demo Views for Spashta-CKG

This is a DEMO file used to test Spashta-CKG's Code Knowledge Graph generation.
It demonstrates how Spashta extracts Django views and their relationships.

Part of: Spashta-CKG Demo Project (_demo/)
"""

from django.shortcuts import render
from .models_demo import DemoModel


def home_demo(request):
    """
    Demo home view for Spashta-CKG testing.
    
    This view demonstrates:
    - Function extraction with decorators
    - Import tracking
    - Template rendering detection
    - Context variable detection
    
    Args:
        request: Django HTTP request object
        
    Returns:
        HttpResponse: Rendered home template
    """
    items = DemoModel.objects.all()
    return render(request, "home_demo.html", {"items": items})


def api_items_demo(request):
    """
    Demo API endpoint for HTMX integration.
    
    This view demonstrates:
    - Multiple views in one file
    - Different return patterns
    - Call graph tracking
    
    Args:
        request: Django HTTP request object
        
    Returns:
        HttpResponse: Rendered items partial
    """
    items = DemoModel.objects.all()
    return render(request, "partials/items_demo.html", {"items": items})
