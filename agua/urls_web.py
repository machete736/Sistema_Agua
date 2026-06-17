from django.urls import path
from .views_web import dashboard

urlpatterns = [
    path('', dashboard, name='dashboard'),
]