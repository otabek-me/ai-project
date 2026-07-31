# app3/urls.py
from django.urls import path
from . import views

app_name = 'app3'

urlpatterns = [
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('admin/ai-chat/', views.admin_ai_chat, name='admin_ai_chat'),
    path('test/<int:test_id>/', views.take_test, name='take_test'),
    path('test/<int:test_id>/result/', views.test_result, name='test_result'),
    path('my-results/', views.my_results, name='my_results'),
    path('admin/delete-test/<int:test_id>/', views.delete_test, name='delete_test'),
    path('test/<int:test_id>/statistics/', views.test_statistics, name='test_statistics'),

]