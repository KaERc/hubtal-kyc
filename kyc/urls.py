from django.contrib.auth import views as auth
from django.urls import path

from . import views

app_name = 'kyc'
urlpatterns = [
    path('', views.start, name='start'),
    # ponytail: no login throttling; django-axes, or a rate limit in front of it.
    path('login/', auth.LoginView.as_view(template_name='kyc/login.html'), name='login'),
    path('logout/', auth.LogoutView.as_view(next_page='kyc:start'), name='logout'),
    path('review/', views.review_list, name='review_list'),
    path('review/<int:pk>/', views.review_detail, name='review_detail'),
    path('review/<int:pk>/note/', views.review_note, name='review_note'),
    path('review/<int:pk>/request/', views.review_request, name='review_request'),
    path('review/<int:pk>/do/<str:event>/', views.review_event, name='review_event'),
    path('review/file/<int:pk>/', views.review_download, name='review_download'),
    path('c/<str:token>/', views.case_home, name='case'),
    path('c/<str:token>/s/<str:key>/', views.section, name='section'),
    path('c/<str:token>/docs/', views.docs, name='docs'),
    path('c/<str:token>/docs/<int:pk>/delete/', views.doc_delete, name='doc_delete'),
    path('c/<str:token>/file/<int:pk>/', views.download, name='download'),
    path('c/<str:token>/submit/', views.submit, name='submit'),
    path('c/<str:token>/reply/<int:pk>/', views.reply, name='reply'),
]
