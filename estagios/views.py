from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.http import HttpResponse, FileResponse, Http404
from django.conf import settings
import os

from .models import Edital, Oportunidade, Candidato, Resultado, LogDecisao
from .services import (
    importar_planilhas_edital,
    confirmar_auditoria_candidato,
    confirmar_todas_pendencias,
    executar_classificacao_edital,
    gerar_pdf_oficial_edital,
    gerar_excel_resultado_edital,
)

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        u = request.POST.get('username')
        p = request.POST.get('password')
        user = authenticate(request, username=u, password=p)
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, "Usuário ou senha inválidos. Tente novamente.")
    return render(request, 'estagios/login.html')

def logout_view(request):
    logout(request)
    return redirect('login')

@login_required
def dashboard_view(request):
    editais = Edital.objects.all().order_by('-criado_em')
    total_editais = editais.count()
    total_vagas = sum(e.total_vagas for e in editais)
    total_candidatos = sum(e.total_candidatos for e in editais)
    
    return render(request, 'estagios/dashboard.html', {
        'editais': editais,
        'total_editais': total_editais,
        'total_vagas': total_vagas,
        'total_candidatos': total_candidatos,
    })

@login_required
def novo_edital_view(request):
    if request.method == 'POST':
        titulo = request.POST.get('titulo', 'Estágio de Férias FAMED')
        semestre = request.POST.get('semestre', '2026.1')
        ano = int(request.POST.get('ano', 2026))
        numero_oficio = request.POST.get('numero_oficio', '414 / 2026')
        protocolo = request.POST.get('protocolo', '23073.092158/2026-14')
        pct_cotas = float(request.POST.get('percentual_cotas', 0.5))
        pct_mulheres = float(request.POST.get('percentual_mulheres', 0.5))

        edital = Edital.objects.create(
            titulo=titulo,
            semestre=semestre,
            ano=ano,
            numero_oficio=numero_oficio,
            protocolo=protocolo,
            percentual_cotas=pct_cotas,
            percentual_mulheres=pct_mulheres,
        )
        messages.success(request, f"Edital '{edital.titulo}' criado com sucesso! Agora anexe as planilhas.")
        return redirect('upload_planilhas', edital_id=edital.id)

    return render(request, 'estagios/novo_edital.html')

@login_required
def upload_planilhas_view(request, edital_id):
    edital = get_object_or_404(Edital, id=edital_id)

    if request.method == 'POST':
        # Upload manual ou uso dos arquivos padrão locais
        if 'usar_arquivos_teste' in request.POST:
            # Associa ou copia os arquivos já presentes na raiz
            importar_planilhas_edital(edital)
            messages.success(request, "Planilhas de teste validadas e importadas com sucesso!")
            return redirect('auditoria_semaforo', edital_id=edital.id)

        f_vagas = request.FILES.get('arquivo_vagas')
        f_alunos = request.FILES.get('arquivo_alunos')
        f_ingresso = request.FILES.get('arquivo_ingresso')

        if f_vagas:
            edital.arquivo_vagas = f_vagas
        if f_alunos:
            edital.arquivo_alunos = f_alunos
        if f_ingresso:
            edital.arquivo_ingresso = f_ingresso
        edital.save()

        res = importar_planilhas_edital(edital)
        messages.success(
            request,
            f"Dados importados com sucesso! {res['total']} estudantes processados "
            f"({res['verdes']} validados automaticamente, {res['amarelos']} com divergência e {res['vermelhos']} necessitando revisão)."
        )
        return redirect('auditoria_semaforo', edital_id=edital.id)

    return render(request, 'estagios/upload_planilhas.html', {'edital': edital})

@login_required
def auditoria_semaforo_view(request, edital_id):
    edital = get_object_or_404(Edital, id=edital_id)
    
    # Filtro de aba no semáforo
    aba = request.GET.get('aba', 'todos')
    candidatos_qs = edital.candidatos.all()

    verdes_count = candidatos_qs.filter(status_auditoria='VERDE').count()
    amarelos_count = candidatos_qs.filter(status_auditoria='AMARELO').count()
    vermelhos_count = candidatos_qs.filter(status_auditoria='VERMELHO').count()
    pendencias_count = candidatos_qs.filter(auditado_pelo_diretor=False).count()

    if aba == 'verde':
        candidatos = candidatos_qs.filter(status_auditoria='VERDE')
    elif aba == 'amarelo':
        candidatos = candidatos_qs.filter(status_auditoria='AMARELO')
    elif aba == 'vermelho':
        candidatos = candidatos_qs.filter(status_auditoria='VERMELHO')
    elif aba == 'pendentes':
        candidatos = candidatos_qs.filter(auditado_pelo_diretor=False)
    else:
        candidatos = candidatos_qs

    return render(request, 'estagios/auditoria_semaforo.html', {
        'edital': edital,
        'candidatos': candidatos,
        'aba': aba,
        'verdes_count': verdes_count,
        'amarelos_count': amarelos_count,
        'vermelhos_count': vermelhos_count,
        'pendencias_count': pendencias_count,
    })

@login_required
def confirmar_candidato_view(request, candidato_id):
    candidato = get_object_or_404(Candidato, id=candidato_id)
    if request.method == 'POST':
        novo_crg = request.POST.get('crg_oficial', candidato.crg_oficial)
        try:
            confirmar_auditoria_candidato(candidato, float(novo_crg))
            messages.success(request, f"Nota de {candidato.nome} homologada com sucesso: {candidato.crg_oficial:.4f}")
        except ValueError:
            messages.error(request, "Valor de CRG inválido informado.")
    return redirect('auditoria_semaforo', edital_id=candidato.edital.id)

@login_required
def homologar_todas_pendencias_view(request, edital_id):
    edital = get_object_or_404(Edital, id=edital_id)
    qtd = confirmar_todas_pendencias(edital)
    messages.success(request, f"Todas as {qtd} pendências de auditoria foram homologadas com sucesso!")
    return redirect('auditoria_semaforo', edital_id=edital.id)

@login_required
def processar_classificacao_view(request, edital_id):
    edital = get_object_or_404(Edital, id=edital_id)
    
    # Se ainda houver pendências não auditadas, aprova em lote automaticamente para liberar o cálculo
    if edital.pendencias_auditoria_count > 0:
        confirmar_todas_pendencias(edital)

    res = executar_classificacao_edital(edital)
    messages.success(
        request,
        f"Classificação final concluída com sucesso! {res['alocados']} alunos foram selecionados para as vagas "
        f"({res['mulheres']} mulheres e {res['cotistas']} cotistas) e {res['reserva']} no Cadastro de Reserva."
    )
    return redirect('resultado_final', edital_id=edital.id)

@login_required
def resultado_final_view(request, edital_id):
    edital = get_object_or_404(Edital, id=edital_id)
    
    # Oportunidades com seus aprovados
    oportunidades = edital.oportunidades.all().prefetch_related('alocados__candidato')
    aprovados = Resultado.objects.filter(edital=edital, status='APROVADO').select_related('candidato', 'oportunidade')
    reserva = Resultado.objects.filter(edital=edital, status='RESERVA').select_related('candidato')
    logs = edital.logs.all()

    total_alocados = aprovados.count()
    mulheres_alocadas = aprovados.filter(candidato__genero='F').count()
    cotistas_alocados = aprovados.filter(candidato__is_cotista=True).count()

    pct_mulheres = round((mulheres_alocadas / total_alocados * 100), 1) if total_alocados > 0 else 0.0
    pct_cotistas = round((cotistas_alocados / total_alocados * 100), 1) if total_alocados > 0 else 0.0

    return render(request, 'estagios/resultado_final.html', {
        'edital': edital,
        'oportunidades': oportunidades,
        'aprovados': aprovados,
        'reserva': reserva,
        'logs': logs,
        'total_alocados': total_alocados,
        'mulheres_alocadas': mulheres_alocadas,
        'cotistas_alocados': cotistas_alocados,
        'pct_mulheres': pct_mulheres,
        'pct_cotistas': pct_cotistas,
    })

@login_required
def exportar_pdf_view(request, edital_id):
    edital = get_object_or_404(Edital, id=edital_id)
    pdf_filename = f"Oficio_Selecao_Estagios_FAMED_{edital.semestre}.pdf"
    pdf_path = os.path.join(settings.BASE_DIR, pdf_filename)
    
    gerar_pdf_oficial_edital(edital, pdf_path)
    
    if os.path.exists(pdf_path):
        return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf', filename=pdf_filename)
    raise Http404("Erro ao gerar o PDF oficial.")

@login_required
def exportar_excel_view(request, edital_id):
    edital = get_object_or_404(Edital, id=edital_id)
    excel_filename = f"resultado_final_auditoria_{edital.semestre}.xlsx"
    excel_path = os.path.join(settings.BASE_DIR, excel_filename)
    
    gerar_excel_resultado_edital(edital, excel_path)
    
    if os.path.exists(excel_path):
        return FileResponse(
            open(excel_path, 'rb'),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            filename=excel_filename
        )
    raise Http404("Erro ao gerar a planilha Excel.")
