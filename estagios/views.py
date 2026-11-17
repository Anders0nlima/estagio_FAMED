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
    gerar_oficio_word_edital,
    gerar_excel_resultado_edital,
    gerar_planilha_frequencia_preenchida,
    importar_planilha_frequencia,
    salvar_frequencias_em_lote,
    marcar_todos_aptos,
    gerar_certificado_individual_word,
    gerar_zip_certificados_word,
    gerar_certificado_individual_pdf,
    gerar_zip_certificados,
    disparar_certificados_email,
    gerar_folha_frequencia_individual_pdf,
    gerar_zip_folhas_frequencia,
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
        try:
            pct_cotas = float(str(request.POST.get('percentual_cotas', 0.5)).replace(',', '.'))
        except (ValueError, TypeError):
            pct_cotas = 0.5
        try:
            pct_mulheres = float(str(request.POST.get('percentual_mulheres', 0.0)).replace(',', '.'))
        except (ValueError, TypeError):
            pct_mulheres = 0.0
        aplicar_genero = (pct_mulheres > 0.0)
        dividir_ciclo = request.POST.get('dividir_por_ciclo', 'true').lower() in ('true', '1', 't', 'on')

        edital = Edital.objects.create(
            titulo=titulo,
            semestre=semestre,
            ano=ano,
            numero_oficio=numero_oficio,
            protocolo=protocolo,
            percentual_cotas=pct_cotas,
            percentual_mulheres=pct_mulheres,
            aplicar_genero=aplicar_genero,
            dividir_por_ciclo=dividir_ciclo,
        )
        messages.success(request, f"Edital '{edital.titulo}' criado com sucesso! Agora anexe as planilhas.")
        return redirect('upload_planilhas', edital_id=edital.id)

    return render(request, 'estagios/novo_edital.html')

@login_required
def editar_edital_view(request, edital_id):
    edital = get_object_or_404(Edital, id=edital_id)
    if request.method == 'POST':
        edital.titulo = request.POST.get('titulo', edital.titulo)
        edital.semestre = request.POST.get('semestre', edital.semestre)
        try:
            edital.ano = int(request.POST.get('ano', edital.ano))
        except (ValueError, TypeError):
            pass
        edital.numero_oficio = request.POST.get('numero_oficio', edital.numero_oficio)
        edital.protocolo = request.POST.get('protocolo', edital.protocolo)
        try:
            val_cotas = str(request.POST.get('percentual_cotas', edital.percentual_cotas)).replace(',', '.')
            edital.percentual_cotas = float(val_cotas)
        except (ValueError, TypeError):
            pass
        try:
            val_mulheres = str(request.POST.get('percentual_mulheres', edital.percentual_mulheres)).replace(',', '.')
            edital.percentual_mulheres = float(val_mulheres)
        except (ValueError, TypeError):
            pass
        edital.aplicar_genero = (edital.percentual_mulheres > 0.0)
        if 'dividir_por_ciclo' in request.POST:
            edital.dividir_por_ciclo = request.POST.get('dividir_por_ciclo', 'true').lower() in ('true', '1', 't', 'on')
        edital.save()
        messages.success(request, f"Edital '{edital.titulo}' atualizado com sucesso!")
        return redirect('dashboard')

    return render(request, 'estagios/novo_edital.html', {'edital': edital, 'modo_edicao': True})

@login_required
def excluir_edital_view(request, edital_id):
    edital = get_object_or_404(Edital, id=edital_id)
    if request.method == 'POST':
        titulo = edital.titulo
        edital.delete()
        messages.success(request, f"Processo seletivo '{titulo}' excluído com sucesso!")
    return redirect('dashboard')

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
    
    # Filtro de aba no semáforo e busca
    aba = request.GET.get('aba', 'todos')
    q = request.GET.get('q', '').strip()
    candidatos_qs = edital.candidatos.all()

    total_count = candidatos_qs.count()
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

    if q:
        from django.db.models import Q
        candidatos = candidatos.filter(
            Q(nome__icontains=q) |
            Q(matricula__icontains=q) |
            Q(crg_digitado__icontains=q) |
            Q(email__icontains=q)
        )

    return render(request, 'estagios/auditoria_semaforo.html', {
        'edital': edital,
        'candidatos': candidatos,
        'aba': aba,
        'q': q,
        'total_count': total_count,
        'verdes_count': verdes_count,
        'amarelos_count': amarelos_count,
        'vermelhos_count': vermelhos_count,
        'pendencias_count': pendencias_count,
    })

@login_required
def confirmar_candidato_view(request, candidato_id):
    candidato = get_object_or_404(Candidato, id=candidato_id)
    if request.method == 'POST':
        novo_crg = request.POST.get('crg_oficial', '').strip()
        if novo_crg:
            try:
                val = float(novo_crg.replace(',', '.'))
                confirmar_auditoria_candidato(candidato, val)
                messages.success(request, f"Nota de {candidato.nome} homologada com sucesso: {candidato.crg_oficial:.4f}")
            except ValueError:
                messages.error(request, f"Valor de CRG inválido informado: '{novo_crg}'.")
        else:
            messages.error(request, "Por favor, informe um valor de CRG para homologação.")
            
    referer = request.META.get('HTTP_REFERER')
    if referer and 'auditoria' in referer:
        return redirect(referer)
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

@login_required
def exportar_docx_view(request, edital_id):
    edital = get_object_or_404(Edital, id=edital_id)
    docx_filename = f"Oficio_Selecao_Estagios_FAMED_{edital.semestre}.docx"
    docx_path = os.path.join(settings.BASE_DIR, docx_filename)
    
    gerar_oficio_word_edital(edital, docx_path)
    
    if os.path.exists(docx_path):
        return FileResponse(
            open(docx_path, 'rb'),
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            filename=docx_filename
        )
    raise Http404("Erro ao gerar o Ofício em Word (.docx).")


# =============================================================================
# MÓDULO PÓS-ESTÁGIO: FREQUÊNCIA, CERTIFICADOS E ENVIO DE E-MAILS
# =============================================================================

@login_required
def frequencia_certificados_view(request, edital_id):
    """Página principal de gestão de frequência pós-estágio e emissão de certificados."""
    edital = get_object_or_404(Edital, id=edital_id)
    aprovados_qs = Resultado.objects.filter(edital=edital, status='APROVADO').select_related('candidato', 'oportunidade').order_by('oportunidade__id', 'posicao')

    total_aprovados = aprovados_qs.count()
    aptos_count = sum(1 for r in aprovados_qs if r.status_conclusao == 'APTO')
    reprovados_count = sum(1 for r in aprovados_qs if r.status_conclusao == 'REPROVADO')
    pendentes_count = sum(1 for r in aprovados_qs if r.status_conclusao == 'PENDENTE')
    emails_enviados_count = aprovados_qs.filter(email_enviado=True).count()

    # Agrupa por oportunidade/professor
    grupos_professores = []
    for op in edital.oportunidades.all().order_by('id'):
        alocados_op = [r for r in aprovados_qs if r.oportunidade_id == op.id]
        if alocados_op:
            grupos_professores.append({
                'oportunidade': op,
                'professor': op.professor,
                'local': op.local,
                'periodo': op.periodo,
                'carga_horaria': alocados_op[0].carga_horaria_horas if alocados_op else 36,
                'alocados': alocados_op,
            })

    modo_simulacao = 'filebased' in settings.EMAIL_BACKEND
    pasta_simulacao = str(settings.EMAIL_FILE_PATH)

    return render(request, 'estagios/frequencia_certificados.html', {
        'edital': edital,
        'grupos_professores': grupos_professores,
        'total_aprovados': total_aprovados,
        'aptos_count': aptos_count,
        'reprovados_count': reprovados_count,
        'pendentes_count': pendentes_count,
        'emails_enviados_count': emails_enviados_count,
        'modo_simulacao': modo_simulacao,
        'pasta_simulacao': pasta_simulacao,
    })

@login_required
def salvar_frequencia_view(request, edital_id):
    """Salva os percentuais de frequência e status preenchidos no formulário web."""
    edital = get_object_or_404(Edital, id=edital_id)
    if request.method == 'POST':
        total = salvar_frequencias_em_lote(edital, request.POST)
        messages.success(request, f"Cargas horárias, frequências e status atualizados com sucesso ({total} alunos processados)!")
    return redirect('frequencia_certificados', edital_id=edital.id)

@login_required
def marcar_todos_aptos_view(request, edital_id):
    """Atalho rápido para marcar 100% de presença para todos os aprovados."""
    edital = get_object_or_404(Edital, id=edital_id)
    if request.method == 'POST':
        qtd = marcar_todos_aptos(edital)
        messages.success(request, f"Todos os {qtd} alunos aprovados foram homologados com 100% de frequência (Aptos)!")
    return redirect('frequencia_certificados', edital_id=edital.id)

@login_required
def exportar_planilha_frequencia_view(request, edital_id):
    """Gera e faz o download da planilha Excel pré-preenchida para os professores."""
    edital = get_object_or_404(Edital, id=edital_id)
    output_filename = f"Frequencia_Estagio_FAMED_{edital.semestre}.xlsx"
    pasta_temp = os.path.join(settings.MEDIA_ROOT, f"temp_{edital.id}")
    os.makedirs(pasta_temp, exist_ok=True)
    output_path = os.path.join(pasta_temp, output_filename)

    gerar_planilha_frequencia_preenchida(edital, output_path)

    if os.path.exists(output_path):
        return FileResponse(
            open(output_path, 'rb'),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            filename=output_filename
        )
    raise Http404("Erro ao gerar a planilha de frequência.")

@login_required
def upload_planilha_frequencia_view(request, edital_id):
    """Importa a planilha Excel preenchida com as frequências informadas pelos professores."""
    edital = get_object_or_404(Edital, id=edital_id)
    if request.method == 'POST':
        arquivo = request.FILES.get('arquivo_frequencia')
        if not arquivo:
            messages.error(request, "Nenhum arquivo Excel de frequência selecionado.")
            return redirect('frequencia_certificados', edital_id=edital.id)

        pasta_temp = os.path.join(settings.MEDIA_ROOT, f"upload_freq_{edital.id}")
        os.makedirs(pasta_temp, exist_ok=True)
        caminho_salvo = os.path.join(pasta_temp, arquivo.name)
        with open(caminho_salvo, 'wb+') as dest:
            for chunk in arquivo.chunks():
                dest.write(chunk)

        res = importar_planilha_frequencia(edital, caminho_salvo)
        messages.success(
            request,
            f"Planilha de frequência importada com sucesso! {res['atualizados']} alunos analisados "
            f"({res['aptos']} aptos e {res['reprovados']} com frequência insuficiente)."
        )
    return redirect('frequencia_certificados', edital_id=edital.id)

@login_required
def baixar_certificado_individual_view(request, resultado_id):
    """Gera e faz o download do Certificado individual em formato Word (.docx) de um aluno aprovado (ou PDF opcional)."""
    resultado = get_object_or_404(Resultado.objects.select_related('candidato', 'oportunidade', 'edital'), id=resultado_id)
    
    pasta_cert = os.path.join(settings.MEDIA_ROOT, f"certificados_edital_{resultado.edital.id}")
    os.makedirs(pasta_cert, exist_ok=True)
    
    safe_name = "".join(c for c in resultado.candidato.nome if c.isalnum() or c in (' ', '_', '-')).rstrip()
    formato = request.GET.get('formato', 'word').lower()

    if formato == 'pdf':
        pdf_filename = f"Certificado_FAMED_{resultado.candidato.matricula}_{safe_name}.pdf"
        pdf_path = os.path.join(pasta_cert, pdf_filename)
        gerar_certificado_individual_pdf(resultado, pdf_path)
        if os.path.exists(pdf_path):
            return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf', filename=pdf_filename)
        raise Http404("Erro ao gerar o certificado em PDF.")
    
    docx_filename = f"Certificado_FAMED_{resultado.candidato.matricula}_{safe_name}.docx"
    docx_path = os.path.join(pasta_cert, docx_filename)
    gerar_certificado_individual_word(resultado, docx_path)
    
    if os.path.exists(docx_path):
        return FileResponse(
            open(docx_path, 'rb'), 
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document', 
            filename=docx_filename
        )
    raise Http404("Erro ao gerar o certificado em Word (.docx).")

@login_required
def baixar_certificados_zip_view(request, edital_id):
    """Empacota e faz o download de todos os certificados dos alunos aptos em formato Word (.docx) em um arquivo ZIP."""
    edital = get_object_or_404(Edital, id=edital_id)
    
    concluintes_count = Resultado.objects.filter(edital=edital, status='APROVADO', concluiu_estagio=True).count()
    if concluintes_count == 0:
        messages.warning(request, "Nenhum aluno concluinte (Apto) encontrado para gerar certificados no momento.")
        return redirect('frequencia_certificados', edital_id=edital.id)

    formato = request.GET.get('formato', 'word').lower()
    if formato == 'pdf':
        zip_filename = f"Certificados_PDF_FAMED_{edital.semestre}.zip"
        zip_path = os.path.join(settings.MEDIA_ROOT, zip_filename)
        gerar_zip_certificados(edital, zip_path)
    else:
        zip_filename = f"Certificados_Word_FAMED_{edital.semestre}.zip"
        zip_path = os.path.join(settings.MEDIA_ROOT, zip_filename)
        gerar_zip_certificados_word(edital, zip_path)

    if os.path.exists(zip_path):
        return FileResponse(open(zip_path, 'rb'), content_type='application/zip', filename=zip_filename)
    raise Http404("Erro ao gerar o arquivo ZIP de certificados.")

@login_required
def enviar_certificados_email_view(request, edital_id):
    """Dispara os certificados por e-mail para todos os alunos concluintes."""
    edital = get_object_or_404(Edital, id=edital_id)
    if request.method == 'POST':
        concluintes_count = Resultado.objects.filter(edital=edital, status='APROVADO', concluiu_estagio=True).count()
        if concluintes_count == 0:
            messages.warning(request, "Nenhum aluno concluinte (Apto) registrado para envio de certificados.")
            return redirect('frequencia_certificados', edital_id=edital.id)

        email_teste = request.POST.get('email_teste', '').strip() or None
        res = disparar_certificados_email(edital, email_teste_destino=email_teste)

        if res['modo_simulacao']:
            messages.success(
                request,
                f"🛡️ Simulação Concluída: {res['enviados_sucesso']} e-mails com certificados foram gerados e armazenados com segurança "
                f"na pasta local 'media/emails_simulados/'. Nenhum e-mail real foi enviado aos estudantes."
            )
        else:
            messages.success(
                request,
                f"✉️ Sucesso: {res['enviados_sucesso']} certificados foram despachados com sucesso via servidor SMTP institucional!"
            )

        if res['erros']:
            messages.error(request, f"Atenção: Ocorreram erros no envio para {len(res['erros'])} discentes.")
    return redirect('frequencia_certificados', edital_id=edital.id)


@login_required
def baixar_folha_frequencia_individual_view(request, resultado_id):
    """Gera e baixa a folha de presença diária em PDF (modelo FAMED) pré-preenchida para o aluno."""
    resultado = get_object_or_404(Resultado.objects.select_related('candidato', 'oportunidade', 'edital'), id=resultado_id)
    pasta_temp = os.path.join(settings.MEDIA_ROOT, f"folhas_freq_{resultado.edital.id}")
    os.makedirs(pasta_temp, exist_ok=True)

    safe_name = "".join(c for c in resultado.candidato.nome if c.isalnum() or c in (' ', '_', '-')).rstrip()
    pdf_filename = f"Folha_Frequencia_{resultado.candidato.matricula}_{safe_name}.pdf"
    pdf_path = os.path.join(pasta_temp, pdf_filename)

    gerar_folha_frequencia_individual_pdf(resultado, pdf_path)

    if os.path.exists(pdf_path):
        return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf', filename=pdf_filename)
    raise Http404("Erro ao gerar a folha de frequência em PDF.")


@login_required
def baixar_folhas_frequencia_zip_view(request, edital_id):
    """Gera um arquivo ZIP com todas as folhas de presença diárias em PDF dos alunos aprovados."""
    edital = get_object_or_404(Edital, id=edital_id)
    zip_filename = f"Folhas_Frequencia_Diaria_FAMED_{edital.semestre}.zip"
    zip_path = os.path.join(settings.MEDIA_ROOT, zip_filename)

    gerar_zip_folhas_frequencia(edital, zip_path)

    if os.path.exists(zip_path):
        return FileResponse(open(zip_path, 'rb'), content_type='application/zip', filename=zip_filename)
    raise Http404("Erro ao gerar o arquivo ZIP de folhas de frequência.")
