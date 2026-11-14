from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('edital/novo/', views.novo_edital_view, name='novo_edital'),
    path('edital/<int:edital_id>/upload/', views.upload_planilhas_view, name='upload_planilhas'),
    path('edital/<int:edital_id>/auditoria/', views.auditoria_semaforo_view, name='auditoria_semaforo'),
    path('edital/<int:edital_id>/homologar-todas/', views.homologar_todas_pendencias_view, name='homologar_todas'),
    path('candidato/<int:candidato_id>/confirmar/', views.confirmar_candidato_view, name='confirmar_candidato'),
    path('edital/<int:edital_id>/classificar/', views.processar_classificacao_view, name='processar_classificacao'),
    path('edital/<int:edital_id>/resultado/', views.resultado_final_view, name='resultado_final'),
    path('edital/<int:edital_id>/exportar/pdf/', views.exportar_pdf_view, name='exportar_pdf'),
    path('edital/<int:edital_id>/exportar/excel/', views.exportar_excel_view, name='exportar_excel'),
]
