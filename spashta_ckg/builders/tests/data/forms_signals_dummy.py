"""Fixture for Django form->model binding + signal receivers (spec/fullstack-coupling-roadmap.md P4).

class WidgetForm(forms.ModelForm): class Meta: model = Widget   -> uses_model (WidgetForm -> Widget)
@receiver(post_save, sender=Widget) def on_widget_saved(...)     -> listens_to (on_widget_saved -> Signal post_save)
"""

from django import forms
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class Widget(models.Model):
    name = models.CharField(max_length=50)


class WidgetForm(forms.ModelForm):
    class Meta:
        model = Widget
        fields = ["name"]


@receiver(post_save, sender=Widget)
def on_widget_saved(sender, instance, **kwargs):
    return None
