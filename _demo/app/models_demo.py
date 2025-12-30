"""
models_demo.py - Demo Models for Spashta-CKG

This is a DEMO file used to test Spashta-CKG's Code Knowledge Graph generation.
It demonstrates how Spashta extracts Django model structures.

Part of: Spashta-CKG Demo Project (_demo/)
"""

from django.db import models


class DemoModel(models.Model):
    """
    A simple demo model to showcase Spashta's model detection.
    
    This model demonstrates:
    - Class extraction
    - Field detection
    - Method detection
    - Docstring capture
    """
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        """Return the name as string representation."""
        return self.name
    
    def get_display_name(self):
        """
        Demo method to show Spashta's method extraction.
        
        Returns:
            str: Formatted display name
        """
        return f"Demo: {self.name}"
