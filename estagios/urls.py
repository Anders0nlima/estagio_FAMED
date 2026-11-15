from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('edital/novo/', views.novo_edital_view, name='novo_edital'),
    path('edital/<int:edital_id>/editar/', views.editar_edital_view, name='editar_edital'),
    path('edital/<int:edital_id>/excluir/', views.excluir_edital_view, name='excluir_edital'),
    path('edital/<int:edital_id>/upload/', views.upload_planilhas_view, name='upload_planilhas'),
    path('edital/<int:edital_id>/auditoria/', views.auditoria_semaforo_view, name='auditoria_semaforo'),
    path('edital/<int:edital_id>/homologar-todas/', views.homologar_todas_pendencias_view, name='homologar_todas'),
    path('candidato/<int:candidato_id>/confirmar/', views.confirmar_candidato_view, name='confirmar_candidato'),
    path('edital/<int:edital_id>/classificar/', views.processar_classificacao_view, name='processar_classificacao'),
    path('edital/<int:edital_id>/resultado/', views.resultado_final_view, name='resultado_final'),
    path('edital/<int:edital_id>/exportar/pdf/', views.exportar_pdf_view, name='exportar_pdf'),
    path('edital/<int:edital_id>/exportar/excel/', views.exportar_excel_view, name='exportar_excel'),
    # Módulo Pós-Estágio, Frequência e Certificados
    path('edital/<int:edital_id>/pos-estagio/', views.frequencia_certificados_view, name='frequencia_certificados'),
    path('edital/<int:edital_id>/pos-estagio/salvar/', views.salvar_frequencia_view, name='salvar_frequencia'),
    path('edital/<int:edital_id>/pos-estagio/marcar-todos-aptos/', views.marcar_todos_aptos_view, name='marcar_todos_aptos'),
    path('edital/<int:edital_id>/pos-estagio/planilha/exportar/', views.exportar_planilha_frequencia_view, name='exportar_planilha_frequencia'),
    path('edital/<int:edital_id>/pos-estagio/planilha/importar/', views.upload_planilha_frequencia_view, name='upload_planilha_frequencia'),
    path('resultado/<int:resultado_id>/certificado/', views.baixar_certificado_individual_view, name='baixar_certificado_individual'),
    path('resultado/<int:resultado_id>/folha-frequencia/', views.baixar_folha_frequencia_individual_view, name='baixar_folha_frequencia_individual'),
    path('edital/<int:edital_id>/pos-estagio/certificados/zip/', views.baixar_certificados_zip_view, name='baixar_certificados_zip'),
    path('edital/<int:edital_id>/pos-estagio/folhas-frequencia/zip/', views.baixar_folhas_frequencia_zip_view, name='baixar_folhas_frequencia_zip'),
    path('edital/<int:edital_id>/pos-estagio/certificados/email/', views.enviar_certificados_email_view, name='enviar_certificados_email'),
]
