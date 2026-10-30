from django.urls import path

from . import views

app_name = 'kyc'
urlpatterns = [
    path('', views.start, name='start'),
    path('c/<str:token>/', views.case_home, name='case'),
    path('c/<str:token>/s/<str:key>/', views.section, name='section'),
    path('c/<str:token>/docs/', views.docs, name='docs'),
    path('c/<str:token>/docs/<int:pk>/delete/', views.doc_delete, name='doc_delete'),
    path('c/<str:token>/file/<int:pk>/', views.download, name='download'),
    path('c/<str:token>/submit/', views.submit, name='submit'),
    path('c/<str:token>/reply/<int:pk>/', views.reply, name='reply'),
]
