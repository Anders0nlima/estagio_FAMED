# -*- coding: utf-8 -*-
"""
Serviços de Negócio da Plataforma de Estágios FAMED/UFPA
Integra a higienização de formulários, auditoria do semáforo, motor de classificação,
gestão de frequência pós-estágio, geração de certificados em PDF e disparo seguro de e-mails.
"""

import os
import re
import math
import hashlib
import zipfile
import datetime
from typing import Dict, List, Tuple, Any, Optional

import pandas as pd
from django.conf import settings
from django.utils import timezone
from django.core.mail import EmailMultiAlternatives

# ReportLab imports para Certificados e Relatórios
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import cm, mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
    KeepTogether,
)
from reportlab.pdfgen import canvas

from .models import Edital, Oportunidade, Candidato, Resultado, LogDecisao
from classificador import (
    clean_crg,
    clean_matricula,
    clean_phone,
    normalize_name,
    parse_option_id,
    parse_option_list,
    parse_birth_date,
    guess_gender,
    determine_cycle,
    parse_semestres_permitidos,
    parse_opportunities_docx,
    load_cotas_file,
    OPORTUNIDADES_CANONICAS,
    allocate_opportunity,
    sort_candidates,
    Student,
    Opportunity,
    generate_pdf_report,
)


# =============================================================================
# 1. IMPORTAÇÃO E AUDITORIA DO SEMÁFORO
# =============================================================================

def _resolve_edital_file(file_field, default_candidates: List[str]) -> Optional[str]:
    """Resolve o caminho de arquivo enviado no edital ou recorre aos arquivos padrão em teste_fluxo."""
    if file_field:
        try:
            if file_field.path and os.path.exists(file_field.path):
                return file_field.path
        except ValueError:
            pass
    for rel_path in default_candidates:
        abs_path = os.path.join(settings.BASE_DIR, rel_path) if not os.path.isabs(rel_path) else rel_path
        if os.path.exists(abs_path):
            return abs_path
    return None

def _estimar_semestre_candidato(edital: Edital, ano_ingresso: int, max_sem_edital: int) -> int:
    """
    Estima o semestre letivo do estudante com base no ano de ingresso e no período do edital.
    - Editais de férias de virada de ano (Jan/Fev, ex: 2027.1 após 2026.4) usam semestres pares: (ano - ingresso) * 2.
    - Editais de meio de ano (Jul/Ago, ex: 2026.1 Julho) usam semestres ímpares: (ano - ingresso) * 2 + 1.
    """
    ref_txt = f"{edital.titulo} {edital.semestre}".lower()
    is_meio_ano = any(k in ref_txt for k in ['jul', 'ago', '.2', '.3'])
    if is_meio_ano:
        raw_sem = (edital.ano - ano_ingresso) * 2 + 1
    elif any(k in ref_txt for k in ['jan', 'fev', 'dez', '.4']) or edital.ano >= 2027:
        raw_sem = (edital.ano - ano_ingresso) * 2
    else:
        raw_sem = (edital.ano - ano_ingresso) * 2 + 1

    max_cap = 11 if max_sem_edital <= 11 else 12
    return max(1, min(max_cap, raw_sem))

def importar_planilhas_edital(edital: Edital) -> Dict[str, Any]:
    """
    Importa o documento de oportunidades (.docx ou .xlsx), a planilha de inscrições (.xlsx)
    e a planilha de cotistas / forma de ingresso (.xlsx ou .csv) para o banco de dados.
    """
    edital.oportunidades.all().delete()
    edital.candidatos.all().delete()
    edital.resultados.all().delete()
    edital.logs.all().delete()

    # 1. Carregamento das Oportunidades (padrão .docx organizado pelo Diretor)
    vagas_path = _resolve_edital_file(
        edital.arquivo_vagas,
        [
            os.path.join('teste_fluxo', 'Estagio_de_Ferias_FAMED_2027_Candidatura.docx'),
            'vagas_professores.xlsx',
        ]
    )
    vagas_source = OPORTUNIDADES_CANONICAS
    if vagas_path and str(vagas_path).lower().endswith('.docx'):
        parsed_ops = parse_opportunities_docx(vagas_path)
        if not parsed_ops:
            raise ValueError(
                "Não foi possível extrair oportunidades do documento Word (.docx). "
                "Verifique se cada oferta segue o padrão '1) Local – Docente responsável: ... Vagas: ... Perfil do(a) estudante: ...'."
            )
        vagas_source = parsed_ops

    vagas_map = {}
    max_sem_edital = 1
    for op in vagas_source:
        sems = op.get('semestres_permitidos')
        if not sems:
            sems = parse_semestres_permitidos(",".join(op['ciclos_permitidos']))
        if sems:
            max_sem_edital = max(max_sem_edital, max(sems))
        sems_str = ",".join(str(x) for x in sems)
        obj = Oportunidade.objects.create(
            edital=edital,
            codigo_opcao=op['id'],
            professor=op['professor'],
            local=op['local'],
            atividade=op['atividade'],
            periodo=op['periodo'],
            vagas_totais=op['vagas_total'],
            ciclos_permitidos=",".join(op['ciclos_permitidos']),
            semestres_permitidos=sems_str,
        )
        vagas_map[op['id']] = obj

    # 2. Carregamento dos Cotistas / Forma de Ingresso (padrão .xlsx consolidado ou .csv legado)
    cotas_path = _resolve_edital_file(
        edital.arquivo_ingresso,
        [
            os.path.join('teste_fluxo', 'Cotistas_FAMED_Consolidado.xlsx'),
            'forma_ingresso.csv',
        ]
    )
    cotas_dict = load_cotas_file(cotas_path) if cotas_path else {}

    # 3. Carregamento e higienização das inscrições dos alunos (.xlsx)
    alunos_path = _resolve_edital_file(
        edital.arquivo_alunos,
        [
            os.path.join('teste_fluxo', 'Estágio de Férias FAMED Jan-Fev 2027 (respostas).xlsx'),
            'inscricoes_alunos.xlsx',
        ]
    )
    if not alunos_path:
        raise FileNotFoundError("Planilha de inscrições dos alunos não encontrada.")

    df_alunos = pd.read_excel(alunos_path)
    
    col_timestamp = None
    col_nome = None
    col_mat = None
    col_email = None
    col_tel = None
    col_op1 = None
    col_op2 = None
    col_crg = None
    col_link = None

    for col in df_alunos.columns:
        c_low = str(col).lower()
        if 'carimbo' in c_low or 'timestamp' in c_low or 'data/hora' in c_low:
            col_timestamp = col
        elif 'nome completo' in c_low or (c_low.strip() == 'nome'):
            col_nome = col
        elif 'matrícula' in c_low or 'matricula' in c_low:
            col_mat = col
        elif 'e-mail' in c_low or 'email' in c_low:
            col_email = col
        elif 'telefone' in c_low or 'whatsapp' in c_low:
            col_tel = col
        elif 'segunda' in c_low:
            col_op2 = col
        elif 'primeira' in c_low:
            col_op1 = col
        elif 'crg' in c_low:
            col_crg = col
        elif 'anexe' in c_low or 'histórico' in c_low or 'historico' in c_low:
            col_link = col

    if not col_nome and not col_mat:
        raise ValueError("A planilha de alunos não possui colunas reconhecíveis de Nome ou Matrícula.")

    if col_timestamp:
        df_alunos[col_timestamp] = pd.to_datetime(df_alunos[col_timestamp], errors='coerce')
        df_alunos = df_alunos.sort_values(col_timestamp)

    # Descartar linhas fantasma/vazias sem nome nem matrícula
    total_bruto = len(df_alunos)
    df_alunos['mat_clean_temp'] = df_alunos[col_mat].apply(clean_matricula) if col_mat else ''
    df_alunos['nome_norm_temp'] = df_alunos[col_nome].apply(normalize_name) if col_nome else ''
    df_alunos = df_alunos[(df_alunos['mat_clean_temp'] != '') | (df_alunos['nome_norm_temp'] != '')].copy()
    ignorados_vazios = total_bruto - len(df_alunos)

    # Dupla desduplicação mantendo o envio mais recente (primeiro por matrícula, depois por nome normalizado)
    if col_mat:
        mask_mat = df_alunos['mat_clean_temp'] != ''
        df_com_mat = df_alunos[mask_mat].drop_duplicates(subset=['mat_clean_temp'], keep='last')
        df_sem_mat = df_alunos[~mask_mat]
        df_alunos = pd.concat([df_com_mat, df_sem_mat])
        if col_timestamp:
            df_alunos = df_alunos.sort_values(col_timestamp)

    if col_nome:
        mask_nome = df_alunos['nome_norm_temp'] != ''
        df_com_nome = df_alunos[mask_nome].drop_duplicates(subset=['nome_norm_temp'], keep='last')
        df_sem_nome = df_alunos[~mask_nome]
        df_alunos = pd.concat([df_com_nome, df_sem_nome])
        if col_timestamp:
            df_alunos = df_alunos.sort_values(col_timestamp)

    total_importados = 0
    verdes = 0
    amarelos = 0
    vermelhos = 0
    tem_coluna_crg = (col_crg is not None)

    for _, row in df_alunos.iterrows():
        raw_mat = row[col_mat] if col_mat else ''
        mat = clean_matricula(raw_mat)
        raw_nome = row[col_nome] if col_nome else ''
        nome = '' if pd.isna(raw_nome) else " ".join(str(raw_nome).split())
        raw_email = row[col_email] if col_email else ''
        email = '' if pd.isna(raw_email) else str(raw_email).strip().lower()
        tel = clean_phone(row[col_tel]) if col_tel else ''
        raw_crg_val = row[col_crg] if col_crg else None
        raw_crg = '' if (raw_crg_val is None or pd.isna(raw_crg_val)) else str(raw_crg_val).strip()
        raw_link = row[col_link] if col_link else None
        link = '' if (raw_link is None or pd.isna(raw_link)) else str(raw_link).strip()
        
        op1 = parse_option_id(row[col_op1]) if col_op1 else '1'
        op2_list = parse_option_list(row[col_op2]) if col_op2 else []
        op2_str = ", ".join(op2_list)
        
        ts = row[col_timestamp] if col_timestamp else timezone.now()
        if pd.isna(ts):
            ts = timezone.now()
        elif timezone.is_naive(ts):
            ts = timezone.make_aware(ts)

        # Cruzamento com planilha de cotistas (por matrícula ou nome normalizado sem acentos)
        nome_norm = normalize_name(nome)
        cotas_info = cotas_dict.get(mat) or cotas_dict.get(nome_norm) or cotas_dict.get(nome.lower(), {})
        is_cotista = cotas_info.get('is_cotista', False)
        forma_ingresso = cotas_info.get('forma_ingresso', 'Ampla Concorrência')

        # Determinação do ano de ingresso (e correção caso haja erro de digitação na matrícula)
        ano_ingresso = edital.ano
        mat_valida_ano = bool(mat and len(mat) >= 4 and mat[:4].isdigit() and 1990 <= int(mat[:4]) <= edital.ano)
        mat_atipica = not (mat and len(mat) >= 10 and mat_valida_ano)
        obs_matricula = ""

        cotista_mat = cotas_info.get('matricula', '')
        if cotista_mat and len(cotista_mat) >= 4 and cotista_mat[:4].isdigit() and (mat_atipica or (mat != cotista_mat)):
            # Se cruzou por nome porque o aluno errou a matrícula no Forms, usa a matrícula oficial da lista consolidada
            obs_matricula = f" Matrícula corrigida pela lista de cotistas ({mat or 'vazia'} -> {cotista_mat})."
            mat = cotista_mat
            mat_valida_ano = True
            mat_atipica = False

        if mat_valida_ano:
            ano_ingresso = int(mat[:4])
        elif cotas_info.get('ano_periodo'):
            ap_match = re.search(r'(\d{4})', str(cotas_info['ano_periodo']))
            if ap_match:
                ano_ingresso = int(ap_match.group(1))

        if not mat:
            mat = f"PEND-{total_importados + 1:03d}"
            mat_atipica = True

        # Semestre estimado & Ciclo
        semestre_estimado = _estimar_semestre_candidato(edital, ano_ingresso, max_sem_edital)
        ciclo = determine_cycle(semestre_estimado)
        data_nasc = parse_birth_date(cotas_info.get('data_nascimento_raw') or cotas_info.get('data_nasc'), ano_ingresso)
        genero = guess_gender(nome)

        # Avaliação no Semáforo de Auditoria
        if not tem_coluna_crg:
            crg_digitado_display = "Não informado no Forms"
            crg_calculado = 0.0
            status_semaforo = 'VERMELHO'
            motivo = 'Formulário sem campo de CRG — abrir "Ver PDF" do histórico anexo e informar nota oficial.'
            if mat_atipica:
                motivo += ' Matrícula atípica/incompleta: conferir também o semestre no PDF.'
            elif obs_matricula:
                motivo += obs_matricula
            vermelhos += 1
        else:
            crg_digitado_display = raw_crg
            crg_calculado = clean_crg(raw_crg)
            status_semaforo = 'VERDE'
            motivo = 'CRG consistente e validado automaticamente.'

            if any(t in raw_crg.lower() for t in ['não tenho', 'nao tenho', 'não possuo', 'cursando 1º', 'sem crg']) or not raw_crg:
                status_semaforo = 'VERMELHO'
                motivo = 'Aluno sem CRG informado no Forms (CRG preliminar 0.0).'
                vermelhos += 1
            elif '(' in raw_crg or len(raw_crg.split()) > 2:
                status_semaforo = 'VERMELHO'
                motivo = f'Texto explicativo inserido no campo de nota: "{raw_crg[:45]}..."'
                vermelhos += 1
            elif raw_crg.isdigit() and len(raw_crg) >= 4 and float(raw_crg) > 10.0:
                status_semaforo = 'AMARELO'
                motivo = f'Nota digitada sem vírgula/ponto ({raw_crg}), ajustada para {crg_calculado:.4f}.'
                amarelos += 1
            elif ',' in raw_crg:
                status_semaforo = 'AMARELO'
                motivo = f'Nota informada com vírgula ({raw_crg}), padronizada para {crg_calculado:.4f}.'
                amarelos += 1
            elif mat_atipica:
                status_semaforo = 'VERMELHO'
                motivo = 'Matrícula atípica/incompleta: conferir histórico anexo.'
                vermelhos += 1
            else:
                verdes += 1

            if obs_matricula:
                motivo += obs_matricula

        Candidato.objects.create(
            edital=edital,
            matricula=mat,
            nome=nome,
            email=email,
            telefone=tel,
            crg_digitado=crg_digitado_display,
            crg_oficial=crg_calculado,
            link_historico=link,
            status_auditoria=status_semaforo,
            motivo_auditoria=motivo.strip(),
            auditado_pelo_diretor=(status_semaforo == 'VERDE'),
            op1=op1 or '1',
            op2=op2_str,
            genero=genero,
            is_cotista=is_cotista,
            forma_ingresso=forma_ingresso,
            ano_ingresso=ano_ingresso,
            semestre=semestre_estimado,
            ciclo=ciclo,
            data_nascimento=data_nasc,
            timestamp_inscricao=ts,
        )
        total_importados += 1

    edital.status = 'IMPORTADO'
    edital.save()

    return {
        'total': total_importados,
        'oportunidades': len(vagas_map),
        'ignorados_vazios': ignorados_vazios,
        'tem_coluna_crg': tem_coluna_crg,
        'verdes': verdes,
        'amarelos': amarelos,
        'vermelhos': vermelhos,
    }

def confirmar_auditoria_candidato(candidato: Candidato, crg_homologado: float) -> Candidato:
    """Atualiza a nota confirmada pelo diretor na auditoria do semáforo."""
    candidato.crg_oficial = round(float(crg_homologado), 4)
    candidato.auditado_pelo_diretor = True
    candidato.status_auditoria = 'VERDE'
    candidato.motivo_auditoria = f"Homologado manualmente pelo diretor com CRG {candidato.crg_oficial:.4f}."
    candidato.save()
    return candidato

def confirmar_todas_pendencias(edital: Edital) -> int:
    """Aprova em lote todas as pendências restantes, assumindo o valor calculado."""
    pendentes = edital.candidatos.filter(auditado_pelo_diretor=False)
    count = pendentes.count()
    for c in pendentes:
        c.auditado_pelo_diretor = True
        c.status_auditoria = 'VERDE'
        c.motivo_auditoria += " (Homologado em lote pelo diretor)."
        c.save()
    edital.status = 'AUDITADO'
    edital.save()
    return count

def extrair_dados_historico_pdf(pdf_bytes: bytes, filename: str = "") -> Dict[str, Any]:
    """
    Extrai Matrícula, Nome e CRG da página inicial de um histórico acadêmico PDF do SIGAA/UFPA.
    Retorna ok=False caso o PDF seja imagem escaneada sem texto selecionável ou ilegível.
    """
    from io import BytesIO
    texto_paginas = []
    lib_disponivel = False

    try:
        import fitz
        lib_disponivel = True
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            for i in range(min(2, len(doc))):
                t = doc[i].get_text("text") or ""
                if t.strip():
                    texto_paginas.append(t)
    except ImportError:
        pass
    except Exception:
        texto_paginas = []

    if not texto_paginas:
        try:
            import pypdf
            lib_disponivel = True
            reader = pypdf.PdfReader(BytesIO(pdf_bytes))
            for i in range(min(2, len(reader.pages))):
                t = reader.pages[i].extract_text() or ""
                if t.strip():
                    texto_paginas.append(t)
        except ImportError:
            pass
        except Exception:
            texto_paginas = []

    if not lib_disponivel:
        raise RuntimeError("Nenhuma biblioteca de leitura de PDF (pymupdf ou pypdf) está instalada no servidor.")

    texto = "\n".join(texto_paginas).strip()
    if not texto:
        return {'ok': False, 'motivo': 'PDF sem texto selecionável (imagem/escaneado).'}

    # 1. Extração da Matrícula (no texto do SIGAA ou fallback no nome do arquivo)
    mat = ''
    m_mat = re.search(r'Matr[íi]cula\s*:\s*(\d{6,15})', texto, re.IGNORECASE)
    if m_mat:
        mat = clean_matricula(m_mat.group(1))
    elif filename:
        m_fn = re.search(r'\b((?:19|20)\d{8,10})\b', filename)
        if m_fn:
            mat = clean_matricula(m_fn.group(1))

    # 2. Extração do Nome no histórico SIGAA (linha anterior a "Nome:" ou na mesma linha)
    nome = ''
    lines = [ln.strip() for ln in texto.splitlines() if ln.strip()]
    for idx, ln in enumerate(lines):
        m_same = re.match(r'^Nome\s*:\s*(.+)$', ln, re.IGNORECASE)
        if m_same and m_same.group(1).strip():
            nome = m_same.group(1).strip()
            break
        if re.match(r'^Nome\s*:?$', ln, re.IGNORECASE) and idx > 0:
            prev = lines[idx - 1]
            if not any(k in prev.lower() for k in ['proeg', 'ciac', 'histórico', 'emitido', 'dados']):
                nome = prev
                break

    # 3. Extração do CRG (ex: "CRG: 4.9765" ou "CRG: 8,5000")
    crg_val: Optional[float] = None
    m_crg = re.search(r'\bCRG\s*:\s*(\d+(?:[\.,]\d+)?)', texto, re.IGNORECASE)
    if not m_crg:
        m_crg = re.search(r'Coeficiente\s+de\s+Rendimento\s+Geral\s*:?\s*(\d+(?:[\.,]\d+)?)', texto, re.IGNORECASE)
    if m_crg:
        try:
            val = float(m_crg.group(1).replace(',', '.'))
            if 0.0 <= val <= 10.0:
                crg_val = round(val, 4)
        except ValueError:
            crg_val = None

    return {
        'ok': True,
        'matricula': mat,
        'nome': nome,
        'crg': crg_val,
        'texto_norm': normalize_name(texto),
    }

def importar_crgs_historicos_zip_ou_pdfs(edital: Edital, uploaded_files: List[Any]) -> Dict[str, Any]:
    """
    Processa um arquivo .zip (baixado do Google Drive) ou múltiplos .pdf de históricos do SIGAA,
    casa cada arquivo com o respectivo candidato pela Matrícula ou Nome e atualiza o CRG oficial.
    """
    candidatos = list(edital.candidatos.all())
    cand_by_mat = {clean_matricula(c.matricula): c for c in candidatos if c.matricula}
    cand_by_nome = {normalize_name(c.nome): c for c in candidatos if c.nome}

    pdfs_para_ler: List[Tuple[str, bytes]] = []
    imagens_ignoradas = 0

    for f in uploaded_files:
        fname = getattr(f, 'name', '') or ''
        ext = os.path.splitext(fname.lower())[1]
        raw_bytes = f.read()

        if ext == '.zip':
            from io import BytesIO
            with zipfile.ZipFile(BytesIO(raw_bytes)) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    inner_name = info.filename
                    base_inner = os.path.basename(inner_name)
                    if not base_inner or base_inner.startswith('.') or '__MACOSX' in inner_name:
                        continue
                    inner_ext = os.path.splitext(base_inner.lower())[1]
                    if inner_ext == '.pdf':
                        pdfs_para_ler.append((base_inner, zf.read(info.filename)))
                    elif inner_ext in ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.heic'):
                        imagens_ignoradas += 1
        elif ext == '.pdf':
            pdfs_para_ler.append((os.path.basename(fname), raw_bytes))
        elif ext in ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.heic'):
            imagens_ignoradas += 1

    atualizados = 0
    sem_texto_ou_crg = 0
    nao_casados = 0

    for fname, pdf_bytes in pdfs_para_ler:
        dados = extrair_dados_historico_pdf(pdf_bytes, filename=fname)
        if not dados.get('ok') or dados.get('crg') is None:
            sem_texto_ou_crg += 1
            continue

        cand = None
        if dados.get('matricula'):
            cand = cand_by_mat.get(dados['matricula'])
        if not cand and dados.get('nome'):
            cand = cand_by_nome.get(normalize_name(dados['nome']))
        if not cand and dados.get('texto_norm'):
            texto_norm = dados['texto_norm']
            for nome_norm, c_obj in cand_by_nome.items():
                if nome_norm and nome_norm in texto_norm:
                    cand = c_obj
                    break

        if not cand:
            nao_casados += 1
            continue

        crg = dados['crg']
        _aplicar_crg_extraido(cand, crg, f"histórico PDF ({fname})")
        atualizados += 1

    if edital.pendencias_auditoria_count == 0 and atualizados > 0:
        edital.status = 'AUDITADO'
        edital.save()

    return {
        'pdfs_lidos': len(pdfs_para_ler),
        'atualizados': atualizados,
        'sem_texto_ou_crg': sem_texto_ou_crg,
        'nao_casados': nao_casados,
        'imagens_ignoradas': imagens_ignoradas,
    }

def _aplicar_crg_extraido(cand: Candidato, crg: float, origem: str) -> None:
    """Atualiza e valida o candidato no banco após extração bem-sucedida do CRG."""
    cand.crg_oficial = crg
    if not cand.crg_digitado or cand.crg_digitado == "Não informado no Forms":
        cand.crg_digitado = f"PDF: {crg:.4f}"
    cand.status_auditoria = 'VERDE'
    cand.auditado_pelo_diretor = True
    cand.motivo_auditoria = f"CRG {crg:.4f} extraído automaticamente de {origem}."
    cand.save()

def _extract_gdrive_file_id(url: str) -> Optional[str]:
    """Extrai o ID do arquivo a partir de qualquer URL padrão do Google Drive."""
    if not url:
        return None
    for pat in [r'[?&]id=([a-zA-Z0-9_-]+)', r'/file/d/([a-zA-Z0-9_-]+)', r'/d/([a-zA-Z0-9_-]+)']:
        m = re.search(pat, str(url).strip())
        if m:
            return m.group(1)
    return None

def _download_gdrive_pdf_bytes(url: str, session=None) -> Dict[str, Any]:
    """
    Baixa em memória um arquivo compartilhado por link no Google Drive (ou URL direta de PDF).
    Identifica se o arquivo está restrito (login Google), se é uma imagem ou um PDF válido.
    """
    import requests

    sess = session or requests.Session()
    file_id = _extract_gdrive_file_id(url)
    target_url = f"https://drive.google.com/uc?export=download&id={file_id}" if file_id else str(url).strip()

    try:
        resp = sess.get(target_url, timeout=18, allow_redirects=True)
    except Exception as exc:
        return {'ok': False, 'reason': 'erro_rede', 'detail': str(exc)}

    if resp.status_code in (401, 403):
        return {'ok': False, 'reason': 'restrito'}
    if resp.status_code >= 400:
        return {'ok': False, 'reason': 'erro_rede', 'detail': f'HTTP {resp.status_code}'}

    ctype = (resp.headers.get('Content-Type') or '').lower()
    content = resp.content or b''

    # Caso o Google Drive exiba tela de confirmação de download para arquivo grande
    if 'text/html' in ctype and file_id and b'confirm=' in content and b'accounts.google.com' not in resp.url.encode():
        m_conf = re.search(r'confirm=([0-9A-Za-z_]+)', content.decode('utf-8', errors='ignore'))
        if m_conf:
            try:
                resp = sess.get(f"{target_url}&confirm={m_conf.group(1)}", timeout=18, allow_redirects=True)
                ctype = (resp.headers.get('Content-Type') or '').lower()
                content = resp.content or b''
            except Exception as exc:
                return {'ok': False, 'reason': 'erro_rede', 'detail': str(exc)}

    if content.startswith(b'%PDF') or 'application/pdf' in ctype:
        return {'ok': True, 'bytes': content}
    if ctype.startswith('image/'):
        return {'ok': False, 'reason': 'imagem'}
    if 'text/html' in ctype or 'accounts.google.com' in str(resp.url):
        return {'ok': False, 'reason': 'restrito'}

    return {'ok': False, 'reason': 'nao_pdf'}

def importar_crgs_dos_links_drive(edital: Edital, max_workers: int = 12, time_budget_seconds: Optional[float] = None) -> Dict[str, Any]:
    """
    Percorre em paralelo os links do Google Drive de todos os candidatos pendentes do edital,
    baixa os PDFs em memória (quando compartilhados com 'Qualquer pessoa com o link'),
    extrai o CRG oficial do SIGAA e valida cada candidato automaticamente.
    """
    import time
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from django.db import transaction
    import requests

    if time_budget_seconds is None:
        time_budget_seconds = 24.0 if os.environ.get('RENDER') else 120.0

    pendentes = list(
        edital.candidatos.filter(auditado_pelo_diretor=False)
        .exclude(link_historico='')
        .exclude(link_historico__isnull=True)
    )

    if not pendentes:
        return {
            'total_links': 0,
            'atualizados': 0,
            'restritos': 0,
            'imagens': 0,
            'sem_texto_ou_crg': 0,
            'erros_rede': 0,
            'nao_processados_tempo': 0,
        }

    thread_local = threading.local()
    sessions_criadas = []

    def _get_thread_session():
        if not hasattr(thread_local, 'session'):
            s = requests.Session()
            thread_local.session = s
            sessions_criadas.append(s)
        return thread_local.session

    def _processar_um(cand_id: int, url: str) -> Tuple[int, Dict[str, Any]]:
        sess = _get_thread_session()
        dl = _download_gdrive_pdf_bytes(url, session=sess)
        if not dl.get('ok') and dl.get('reason') == 'erro_rede':
            time.sleep(0.3)
            dl = _download_gdrive_pdf_bytes(url, session=sess)
        if not dl.get('ok'):
            return cand_id, {'ok': False, 'reason': dl.get('reason', 'erro_rede')}
        dados = extrair_dados_historico_pdf(dl['bytes'])
        if not dados.get('ok') or dados.get('crg') is None:
            return cand_id, {'ok': False, 'reason': 'sem_texto_ou_crg'}
        return cand_id, {'ok': True, 'crg': dados['crg']}

    resultados: Dict[int, Dict[str, Any]] = {}
    workers = min(max_workers, max(1, len(pendentes)))
    deadline = time.monotonic() + time_budget_seconds

    futures = {}
    executor = ThreadPoolExecutor(max_workers=workers)
    try:
        futures = {executor.submit(_processar_um, c.id, c.link_historico): c.id for c in pendentes}
        try:
            for fut in as_completed(futures, timeout=max(1.0, time_budget_seconds)):
                c_id, info = fut.result()
                resultados[c_id] = info
                if time.monotonic() >= deadline:
                    break
        except TimeoutError:
            pass
    finally:
        for fut in futures:
            if not fut.done():
                fut.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        for s in sessions_criadas:
            try:
                s.close()
            except Exception:
                pass

    nao_processados_tempo = max(0, len(pendentes) - len(resultados))

    cand_map = {c.id: c for c in pendentes}
    atualizados = 0
    restritos = 0
    imagens = 0
    sem_texto_ou_crg = 0
    erros_rede = 0

    with transaction.atomic():
        for c_id, info in resultados.items():
            cand = cand_map[c_id]
            if info.get('ok'):
                _aplicar_crg_extraido(cand, info['crg'], "link do Google Drive")
                atualizados += 1
            else:
                reason = info.get('reason')
                if reason == 'restrito':
                    restritos += 1
                elif reason in ('imagem', 'nao_pdf'):
                    imagens += 1
                    cand.motivo_auditoria = "Anexo enviado não é PDF selecionável (foto/imagem) — conferir via 'Ver PDF'."
                    cand.save(update_fields=['motivo_auditoria'])
                elif reason == 'sem_texto_ou_crg':
                    sem_texto_ou_crg += 1
                    cand.motivo_auditoria = "PDF sem texto ou CRG não identificado — conferir via 'Ver PDF'."
                    cand.save(update_fields=['motivo_auditoria'])
                else:
                    erros_rede += 1

    if edital.pendencias_auditoria_count == 0 and atualizados > 0:
        edital.status = 'AUDITADO'
        edital.save()

    return {
        'total_links': len(pendentes),
        'atualizados': atualizados,
        'restritos': restritos,
        'imagens': imagens,
        'sem_texto_ou_crg': sem_texto_ou_crg,
        'erros_rede': erros_rede,
        'nao_processados_tempo': nao_processados_tempo,
    }


# =============================================================================
# 2. MOTOR DE CLASSIFICAÇÃO OFICIAL
# =============================================================================

def executar_classificacao_edital(edital: Edital) -> Dict[str, Any]:
    """Executa a classificação oficial dos candidatos em 2 rodadas com cotas e 50% mulheres."""
    opp_dict = {}
    pct_mulheres = edital.percentual_mulheres if edital.aplicar_genero else 0.0

    for op in edital.oportunidades.all():
        ciclos_list = [c.strip() for c in op.ciclos_permitidos.split(',') if c.strip()]
        sems_list = [int(s.strip()) for s in op.semestres_permitidos.split(',') if s.strip().isdigit()]
        if not sems_list:
            sems_list = parse_semestres_permitidos(",".join(ciclos_list))
        opp_dict[op.codigo_opcao] = Opportunity(
            id=op.codigo_opcao,
            professor=op.professor,
            local=op.local,
            atividade=op.atividade,
            periodo=op.periodo,
            vagas_total=op.vagas_totais,
            ciclos_permitidos=ciclos_list,
            semestres_permitidos=sems_list,
            percentual_cotas=edital.percentual_cotas,
            percentual_mulheres=pct_mulheres,
            dividir_por_ciclo=edital.dividir_por_ciclo,
        )

    students_list = []
    candidatos_db_map = {}
    for c in edital.candidatos.all():
        candidatos_db_map[c.matricula] = c
        op2_list = [x.strip() for x in c.op2.split(',') if x.strip()]
        s = Student(
            matricula=c.matricula,
            nome=c.nome,
            email=c.email,
            telefone=c.telefone,
            crg=c.crg_oficial,
            op1=c.op1,
            op2_list=op2_list,
            timestamp=c.timestamp_inscricao or timezone.now(),
            genero=c.genero,
            is_cotista=c.is_cotista,
            forma_ingresso=c.forma_ingresso,
            ano_ingresso=c.ano_ingresso,
            semestre_atual=c.semestre,
            ciclo=c.ciclo,
            data_nascimento=c.data_nascimento or datetime.date(2000, 1, 1),
        )
        students_list.append(s)

    edital.resultados.all().delete()
    edital.logs.all().delete()

    audit_logs = []
    audit_logs.append("================================================================================")
    audit_logs.append(f"EXECUÇÃO DO MOTOR DE CLASSIFICAÇÃO: {edital.titulo} ({edital.semestre})")
    audit_logs.append(f"Ação Afirmativa de Gênero: {'ATIVADA' if edital.aplicar_genero else 'DESATIVADA'}")
    audit_logs.append(f"Divisão de Vagas por Ciclo: {'ATIVADA (Ímpar p/ mais avançado)' if edital.dividir_por_ciclo else 'DESATIVADA'}")
    audit_logs.append("================================================================================")

    # --- RODADA 1: 1ª OPÇÃO ---
    audit_logs.append("\n>>> RODADA 1: ALOCAÇÃO EM 1ª OPÇÃO <<<")
    for opp_id, opp in opp_dict.items():
        candidatos_op1 = [s for s in students_list if not s.alocado and s.op1 == opp_id]
        
        if opp.semestres_permitidos:
            elegiveis = [s for s in candidatos_op1 if s.semestre_atual in opp.semestres_permitidos]
            descartados = [s for s in candidatos_op1 if s.semestre_atual not in opp.semestres_permitidos]
            for d in descartados:
                audit_logs.append(f"[Semestre Incompatível na 1ª Opção] {d.nome} ({d.semestre_atual}º semestre) não atende aos requisitos da Opção {opp.id} (Semestres: {opp.semestres_permitidos}).")
        else:
            elegiveis = [s for s in candidatos_op1 if s.ciclo in opp.ciclos_permitidos]
            descartados = [s for s in candidatos_op1 if s.ciclo not in opp.ciclos_permitidos]
            for d in descartados:
                audit_logs.append(f"[Ciclo Incompatível na 1ª Opção] {d.nome} (Ciclo {d.ciclo}) não atende à Opção {opp.id}.")

        selecionados, espera, logs = allocate_opportunity(
            opp=opp,
            eligible_candidates=elegiveis,
            vagas_disponiveis=opp.vagas_total,
            rodada_nome="1ª Opção"
        )
        opp.selecionados = selecionados
        opp.lista_espera = espera
        audit_logs.extend(logs)
        for s in selecionados:
            s.alocado_opcao = 1

    # --- RODADA 2: 2ª OPÇÃO (REMANEJAMENTO) ---
    audit_logs.append("\n>>> RODADA 2: ALOCAÇÃO EM 2ª OPÇÃO (REMANEJAMENTO) <<<")
    for opp_id, opp in opp_dict.items():
        vagas_restantes = opp.vagas_total - len(opp.selecionados)
        if vagas_restantes <= 0:
            continue

        candidatos_op2 = [s for s in students_list if not s.alocado and (opp_id in s.op2_list)]
        
        if opp.semestres_permitidos:
            elegiveis = [s for s in candidatos_op2 if s.semestre_atual in opp.semestres_permitidos]
            descartados = [s for s in candidatos_op2 if s.semestre_atual not in opp.semestres_permitidos]
            for d in descartados:
                audit_logs.append(f"[Semestre Incompatível na 2ª Opção] {d.nome} ({d.semestre_atual}º semestre) não atende à Opção {opp.id}.")
        else:
            elegiveis = [s for s in candidatos_op2 if s.ciclo in opp.ciclos_permitidos]

        if elegiveis:
            novos_sel, nova_esp, logs = allocate_opportunity(
                opp=opp,
                eligible_candidates=elegiveis,
                vagas_disponiveis=vagas_restantes,
                rodada_nome="2ª Opção"
            )
            for s in novos_sel:
                s.alocado_opcao = 2
            opp.selecionados.extend(novos_sel)
            opp.lista_espera.extend(nova_esp)
            audit_logs.extend(logs)

    alocados_count = 0
    for opp_id, opp in opp_dict.items():
        op_db = edital.oportunidades.get(codigo_opcao=opp_id)
        op_db.vagas_preenchidas = len(opp.selecionados)
        op_db.save()

        for pos, s in enumerate(opp.selecionados, 1):
            c_db = candidatos_db_map[s.matricula]
            etiqueta = f"{s.modalidade} - Ciclo {s.ciclo.title()} - {s.alocado_opcao}ª Opção"
            if "Ação Afirmativa" in " ".join(s.historico_auditoria):
                etiqueta += " (Ação Afirmativa Gênero)"

            Resultado.objects.create(
                edital=edital,
                candidato=c_db,
                oportunidade=op_db,
                status='APROVADO',
                posicao=pos,
                modalidade=s.modalidade or 'Ampla Concorrência',
                opcao_atendida=f"{s.alocado_opcao}ª Opção",
                etiqueta_motivo=etiqueta,
                concluiu_estagio=False,
                justificativa_frequencia="Estágio em andamento / Frequência pendente",
                carga_horaria_horas=36,
            )
            alocados_count += 1

    reserva_candidatos = sort_candidates([s for s in students_list if not s.alocado])
    for pos, s in enumerate(reserva_candidatos, 1):
        c_db = candidatos_db_map[s.matricula]
        etiqueta = f"Cadastro de Reserva (Geral) - Posição #{pos} - CRG {s.crg:.4f}"
        Resultado.objects.create(
            edital=edital,
            candidato=c_db,
            oportunidade=None,
            status='RESERVA',
            posicao=pos,
            modalidade='Cadastro de Reserva',
            opcao_atendida='',
            etiqueta_motivo=etiqueta
        )

    for log_msg in audit_logs:
        LogDecisao.objects.create(edital=edital, registro=log_msg)

    edital.status = 'CLASSIFICADO'
    edital.save()

    return {
        'total_vagas': edital.total_vagas,
        'alocados': alocados_count,
        'reserva': len(reserva_candidatos),
        'mulheres': sum(1 for s in students_list if s.alocado and s.genero == 'F'),
        'cotistas': sum(1 for s in students_list if s.alocado and s.is_cotista),
    }


# =============================================================================
# 3. GESTÃO DE FREQUÊNCIA (REGRA DOS 75%)
# =============================================================================

def gerar_planilha_frequencia_preenchida(edital: Edital, output_path: str) -> str:
    """Gera a planilha Excel oficial já pré-preenchida para acompanhamento de frequência dos professores."""
    aprovados = Resultado.objects.filter(edital=edital, status='APROVADO').select_related('candidato', 'oportunidade').order_by('oportunidade__id', 'posicao')

    rows = []
    for r in aprovados:
        op = r.oportunidade
        c = r.candidato
        rows.append({
            'Professor Responsável': op.professor if op else '',
            'Local do Estágio': op.local if op else '',
            'Matrícula': c.matricula,
            'Nome Completo do Aluno': c.nome,
            'E-mail': c.email,
            'Carga Horária (horas)': r.carga_horaria_horas,
            '% Frequência': r.frequencia_percentual if r.frequencia_percentual is not None else '',
            'Status Conclusão (Apto / Reprovado)': 'Apto' if r.concluiu_estagio else ('Reprovado' if r.frequencia_percentual is not None and r.frequencia_percentual < 75 else ''),
            'Observações': r.justificativa_frequencia if r.justificativa_frequencia != "Estágio em andamento / Frequência pendente" else ''
        })

    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        df = pd.DataFrame(rows)
        df.to_excel(writer, sheet_name='Frequência_Estágios', index=False)

    return output_path

def importar_planilha_frequencia(edital: Edital, excel_path: str) -> Dict[str, Any]:
    """
    Lê a planilha de frequência preenchida e atualiza os resultados no banco pela matrícula.
    Aplica a regra dos 75% ou o status explícito 'Apto' / 'Concluído'.
    """
    df = pd.read_excel(excel_path)
    
    col_mat = None
    col_nome = None
    col_freq = None
    col_status = None
    col_obs = None

    for c in df.columns:
        c_low = str(c).lower()
        if 'matr' in c_low:
            col_mat = c
        elif 'nome' in c_low:
            col_nome = c
        elif 'freq' in c_low or '%' in c_low:
            col_freq = c
        elif 'status' in c_low or 'conclus' in c_low or 'apto' in c_low:
            col_status = c
        elif 'obs' in c_low:
            col_obs = c
        elif 'carga' in c_low or 'horas' in c_low:
            col_carga = c

    atualizados = 0
    aptos_count = 0
    reprovados_count = 0

    aprovados_dict = {
        r.candidato.matricula: r 
        for r in Resultado.objects.filter(edital=edital, status='APROVADO').select_related('candidato')
    }

    for _, row in df.iterrows():
        raw_mat = row[col_mat] if col_mat else ''
        mat = clean_matricula(raw_mat)
        
        resultado = aprovados_dict.get(mat)
        if not resultado:
            continue

        # Carga Horária opcional informada na planilha
        if col_carga and pd.notna(row[col_carga]):
            try:
                ch_val = int(float(str(row[col_carga]).strip()))
                if ch_val > 0:
                    resultado.carga_horaria_horas = ch_val
            except (ValueError, TypeError):
                pass

        raw_freq = row[col_freq] if col_freq else None
        raw_status = str(row[col_status]).strip().lower() if col_status else ''
        obs = str(row[col_obs]).strip() if col_obs else ''

        # Parsing da Frequência
        freq_val = None
        if pd.notna(raw_freq) and str(raw_freq).strip():
            try:
                freq_str = str(raw_freq).replace('%', '').replace(',', '.').strip()
                freq_val = float(freq_str)
                if freq_val > 100.0:
                    freq_val = 100.0
                elif freq_val < 0.0:
                    freq_val = 0.0
            except ValueError:
                freq_val = None

        # Avaliação da Regra dos 75% e Status Apto
        concluiu = False
        justificativa = ""

        if freq_val is not None:
            if freq_val >= 75.0:
                concluiu = True
                justificativa = f"Apto: Cumpriu {freq_val:.1f}% de frequência (mínimo exigido: 75%)."
            else:
                concluiu = False
                justificativa = f"Frequência insuficiente: Atingiu {freq_val:.1f}% (mínimo exigido: 75%)."
        elif any(t in raw_status for t in ['apto', 'sim', 'concluido', 'concluído', 'ok', '100']):
            concluiu = True
            justificativa = "Apto: Frequência e aproveitamento homologados pelo docente responsável."
            freq_val = 100.0
        elif any(t in raw_status for t in ['reprovado', 'não', 'nao', 'infrequente', 'falta', 'desistente']):
            concluiu = False
            justificativa = f"Reprovado: {obs if obs else 'Frequência insuficiente informada pelo supervisor.'}"
            freq_val = 0.0
        else:
            concluiu = False
            justificativa = "Pendente de confirmação da frequência."

        resultado.frequencia_percentual = freq_val
        resultado.concluiu_estagio = concluiu
        resultado.justificativa_frequencia = justificativa
        resultado.save()

        atualizados += 1
        if concluiu:
            aptos_count += 1
        else:
            reprovados_count += 1

    return {
        'atualizados': atualizados,
        'aptos': aptos_count,
        'reprovados': reprovados_count,
    }

def salvar_frequencias_em_lote(edital: Edital, dados_frequencia: Dict[str, Any]) -> int:
    """Atualiza as frequências e o status de aprovação a partir do formulário web."""
    aprovados = Resultado.objects.filter(edital=edital, status='APROVADO')
    total = 0
    for r in aprovados:
        r_id = str(r.id)
        status_key = f"status_{r_id}"
        freq_key = f"freq_{r_id}"
        carga_key = f"carga_{r_id}"
        
        status_val = str(dados_frequencia.get(status_key, '')).strip().upper()
        freq_val_raw = dados_frequencia.get(freq_key)
        carga_val_raw = dados_frequencia.get(carga_key)

        # Atualização da Carga Horária editável pelo Diretor
        if carga_val_raw is not None and str(carga_val_raw).strip():
            try:
                ch_num = int(str(carga_val_raw).strip())
                if ch_num > 0:
                    r.carga_horaria_horas = ch_num
            except (ValueError, TypeError):
                pass

        freq_val = None
        if freq_val_raw is not None and str(freq_val_raw).strip():
            try:
                freq_val = float(str(freq_val_raw).replace(',', '.').strip())
                if freq_val > 100.0:
                    freq_val = 100.0
                elif freq_val < 0.0:
                    freq_val = 0.0
            except ValueError:
                freq_val = None

        if status_val == 'REPROVADO':
            r.concluiu_estagio = False
            r.frequencia_percentual = freq_val if freq_val is not None else 0.0
            r.justificativa_frequencia = f"Reprovado: {f'Frequência insuficiente ({r.frequencia_percentual:.1f}% < 75%)' if freq_val is not None else 'Estágio não concluído ou frequência insuficiente.'}"
        elif status_val == 'APTO':
            r.concluiu_estagio = True
            r.frequencia_percentual = freq_val if freq_val is not None else 100.0
            r.justificativa_frequencia = f"Apto: Cumpriu estágio com sucesso{f' ({r.frequencia_percentual:.1f}%)' if freq_val is not None else '.'}"
        elif status_val == 'PENDENTE':
            r.concluiu_estagio = False
            r.frequencia_percentual = None
            r.justificativa_frequencia = "Estágio em andamento / Frequência pendente"
        elif freq_val is not None:
            if freq_val >= 75.0:
                r.concluiu_estagio = True
                r.frequencia_percentual = freq_val
                r.justificativa_frequencia = f"Apto: Cumpriu estágio com sucesso ({freq_val:.1f}%)."
            else:
                r.concluiu_estagio = False
                r.frequencia_percentual = freq_val
                r.justificativa_frequencia = f"Reprovado: Frequência insuficiente ({freq_val:.1f}% < 75%)."
        else:
            r.concluiu_estagio = False
            r.frequencia_percentual = None
            r.justificativa_frequencia = "Estágio em andamento / Frequência pendente"
        
        r.save()
        total += 1
    return total

def marcar_todos_aptos(edital: Edital) -> int:
    """Atalho rápido para marcar 100% de frequência para todos os alunos aprovados."""
    aprovados = Resultado.objects.filter(edital=edital, status='APROVADO')
    for r in aprovados:
        r.concluiu_estagio = True
        r.frequencia_percentual = 100.0
        r.justificativa_frequencia = "Aprovado com 100.0% de frequência."
        r.save()
    return aprovados.count()


# =============================================================================
# 4. GERAÇÃO DE CERTIFICADO INDIVIDUAL EM PDF (REPORTLAB - LANDSCAPE NOBRE)
# =============================================================================

def draw_certificate_borders(c: canvas.Canvas, doc):
    """Desenha a moldura institucional nobre dupla no Certificado em formato paisagem."""
    c.saveState()
    width, height = landscape(A4)

    # Moldura Externa (Azul Marinho UFPA)
    c.setStrokeColor(colors.HexColor('#1A365D'))
    c.setLineWidth(3.5)
    c.rect(12 * mm, 12 * mm, width - 24 * mm, height - 24 * mm)

    # Moldura Interna (Dourado Nobre)
    c.setStrokeColor(colors.HexColor('#C5A059'))
    c.setLineWidth(1.2)
    c.rect(15 * mm, 15 * mm, width - 30 * mm, height - 30 * mm)

    # Cantoneiras Decorativas Sutis
    c.setFillColor(colors.HexColor('#C5A059'))
    corner_size = 4 * mm
    for x in [15 * mm, width - 15 * mm - corner_size]:
        for y in [15 * mm, height - 15 * mm - corner_size]:
            c.rect(x, y, corner_size, corner_size, fill=1, stroke=0)

    c.restoreState()

def gerar_certificado_individual_pdf(resultado: Resultado, output_path: str) -> str:
    """
    Gera o Certificado de Conclusão oficial individual em PDF (formato A4 paisagem).
    Baseado no modelo institucional '4 - Modelo de CERTIFICADO.pdf' com Brasão, Logo e assinaturas.
    """
    candidato = resultado.candidato
    oportunidade = resultado.oportunidade
    edital = resultado.edital

    # Hash de Autenticidade Único (SHA-256 de 12 dígitos)
    seed = f"{candidato.matricula}_{oportunidade.id}_{edital.id}_{settings.SECRET_KEY}"
    codigo_autenticidade = f"FAMED-{hashlib.sha256(seed.encode()).hexdigest()[:10].upper()}"

    dir_output = os.path.dirname(os.path.abspath(output_path))
    if dir_output:
        os.makedirs(dir_output, exist_ok=True)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=landscape(A4),
        leftMargin=25 * mm,
        rightMargin=25 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm
    )

    styles = getSampleStyleSheet()

    style_gov = ParagraphStyle(
        'CertGov',
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        alignment=1,
        textColor=colors.HexColor('#1A202C')
    )
    style_famed = ParagraphStyle(
        'CertFamed',
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11.5,
        alignment=1,
        textColor=colors.HexColor('#2D3748')
    )
    style_title = ParagraphStyle(
        'CertTitle',
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        alignment=1,
        textColor=colors.HexColor('#1A365D')
    )
    style_body = ParagraphStyle(
        'CertBody',
        fontName='Times-Roman',
        fontSize=13,
        leading=22,
        alignment=4,  # Justificado
        textColor=colors.HexColor('#1A202C')
    )
    style_sig = ParagraphStyle(
        'CertSig',
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        alignment=1,
        textColor=colors.HexColor('#2D3748')
    )
    style_auth = ParagraphStyle(
        'CertAuth',
        fontName='Helvetica',
        fontSize=7.5,
        leading=10,
        alignment=1,
        textColor=colors.HexColor('#718096')
    )

    story = []

    # Cabeçalho com Logos
    brasao_candidates = [
        os.path.join(settings.BASE_DIR, "Brasao-UFPA-colorido.png"),
        os.path.join(settings.BASE_DIR, "estagios/static/img/Brasao-UFPA-colorido.png"),
        "Brasao-UFPA-colorido.png",
        "ufpa_brasao.png",
        os.path.join(settings.BASE_DIR, "estagios/static/img/ufpa_brasao.png"),
    ]
    brasao_path = next((p for p in brasao_candidates if os.path.exists(p)), None)
    logo_path = "Logo Estagio de Ferias FAMED.png"
    if not os.path.exists(logo_path):
        logo_path = os.path.join(settings.BASE_DIR, "estagios/static/img/logo_famed.png")

    img_brasao = Image(brasao_path, width=1.4 * cm, height=2.0 * cm) if brasao_path else Paragraph("", style_gov)
    img_logo = Image(logo_path, width=1.8 * cm, height=1.8 * cm) if os.path.exists(logo_path) else Paragraph("", style_gov)

    header_table = Table([
        [
            img_brasao,
            [
                Paragraph("REPÚBLICA FEDERATIVA DO BRASIL", style_gov),
                Paragraph("MINISTÉRIO DA EDUCAÇÃO • UNIVERSIDADE FEDERAL DO PARÁ", style_gov),
                Paragraph("INSTITUTO DE CIÊNCIAS DA SAÚDE • FACULDADE DE MEDICINA", style_famed),
            ],
            img_logo
        ]
    ], colWidths=[2.5 * cm, 19.5 * cm, 2.5 * cm])
    header_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 8 * mm))

    # Título do Certificado
    story.append(Paragraph("CERTIFICADO DE ESTÁGIO VOLUNTÁRIO", style_title))
    story.append(Spacer(1, 7 * mm))

    # Texto Oficial (Baseado em '4 - Modelo de CERTIFICADO.pdf')
    texto_certificado = (
        f"Certificamos que o(a) discente <b>{candidato.nome.upper()}</b>, matrícula nº <b>{candidato.matricula}</b>, "
        f"realizou com assiduidade e aproveitamento o estágio voluntário do programa <b>ESTÁGIO DE FÉRIAS DA FAMED-UFPA</b>, "
        f"serviço do <b>{oportunidade.local}</b>, sob orientação da(o) docente <b>{oportunidade.professor}</b>, "
        f"no período de <b>{oportunidade.periodo}</b>, cumprindo com êxito a carga horária total de <b>{resultado.carga_horaria_horas} horas</b>."
    )
    story.append(Paragraph(texto_certificado, style_body))
    story.append(Spacer(1, 12 * mm))

    # Local e Data de Emissão por extenso
    hoje = datetime.date.today()
    meses = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
             'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
    data_extenso = f"Belém-PA, {hoje.day:02d} de {meses[hoje.month - 1]} de {hoje.year}."

    # Assinaturas lado a lado
    sig_table = Table([
        [
            [
                Paragraph("____________________________________________________", style_sig),
                Paragraph(f"<b>Prof(a). {oportunidade.professor}</b>", style_sig),
                Paragraph("Docente Supervisor(a) do Estágio", style_sig),
                Paragraph("FAMED / UFPA", style_sig),
            ],
            [
                Paragraph("____________________________________________________", style_sig),
                Paragraph("<b>Prof. Dr. Cezar Augusto Muniz Caldas</b>", style_sig),
                Paragraph("Direção da Faculdade de Medicina", style_sig),
                Paragraph("FAMED / ICM - UFPA", style_sig),
            ]
        ]
    ], colWidths=[12.2 * cm, 12.2 * cm])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(sig_table)
    story.append(Spacer(1, 6 * mm))

    # Rodapé Antifraude com Hash e Autenticidade
    auth_text = (
        f"{data_extenso} • Registro institucional nº {edital.numero_oficio} • "
        f"<b>Código de Autenticidade: {codigo_autenticidade}</b><br/>"
        f"A autenticidade deste certificado pode ser verificada junto à Secretaria da FAMED/UFPA."
    )
    story.append(Paragraph(auth_text, style_auth))

    # Build com as molduras desenhadas no canvas
    doc.build(story, onFirstPage=draw_certificate_borders)

    resultado.certificado_codigo = codigo_autenticidade
    resultado.certificado_gerado_em = timezone.now()
    resultado.save()

    return output_path

def gerar_zip_certificados(edital: Edital, zip_output_path: str) -> str:
    """Gera um arquivo ZIP com todos os certificados em PDF dos concluintes do edital."""
    concluintes = Resultado.objects.filter(edital=edital, status='APROVADO', concluiu_estagio=True).select_related('candidato', 'oportunidade')

    pasta_temp = os.path.join(settings.MEDIA_ROOT, f"temp_certificados_{edital.id}")
    os.makedirs(pasta_temp, exist_ok=True)

    with zipfile.ZipFile(zip_output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for r in concluintes:
            safe_name = re.sub(r'\W+', '_', r.candidato.nome)
            pdf_filename = f"Certificado_{r.candidato.matricula}_{safe_name}.pdf"
            pdf_path = os.path.join(pasta_temp, pdf_filename)
            gerar_certificado_individual_pdf(r, pdf_path)
            zipf.write(pdf_path, arcname=pdf_filename)

    return zip_output_path


def gerar_certificado_individual_word(resultado: Resultado, output_path: str) -> str:
    """
    Gera o Certificado de Conclusão oficial individual em formato Word (.docx) em folha A4 normal.
    Atende à solicitação da Diretoria com layout limpo e editável, brasão da UFPA,
    texto padrão oficial homologado e assinatura do Diretor da FAMED.
    """
    import docx
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls

    candidato = resultado.candidato
    oportunidade = resultado.oportunidade
    edital = resultado.edital

    # Hash de Autenticidade Único (SHA-256 de 10 dígitos)
    seed = f"{candidato.matricula}_{oportunidade.id if oportunidade else 0}_{edital.id}_{settings.SECRET_KEY}"
    codigo_autenticidade = f"FAMED-{hashlib.sha256(seed.encode()).hexdigest()[:10].upper()}"

    dir_output = os.path.dirname(os.path.abspath(output_path))
    if dir_output:
        os.makedirs(dir_output, exist_ok=True)

    doc = docx.Document()

    # 1. Configuração da Página: Formato A4 Padrão (210 x 297 mm) em Orientação Retrato
    for section in doc.sections:
        section.page_width = Inches(8.27)
        section.page_height = Inches(11.69)
        section.top_margin = Inches(1.8)
        section.bottom_margin = Inches(1.2)
        section.left_margin = Inches(1.2)
        section.right_margin = Inches(1.2)

    # 2. Título do Certificado (Centralizado, Negrito, Preto)
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_before = Pt(20)
    p_title.paragraph_format.space_after = Pt(36)
    run_title = p_title.add_run("CERTIFICADO DE ESTÁGIO VOLUNTÁRIO")
    run_title.bold = True
    run_title.font.size = Pt(18)
    run_title.font.name = "Calibri"
    run_title.font.color.rgb = RGBColor(0, 0, 0)

    # 3. Tratamento de Dados Dinâmicos
    nome_aluno = candidato.nome.strip().upper()
    matricula = candidato.matricula.strip()
    
    local = oportunidade.local.strip() if (oportunidade and oportunidade.local) else "Hospital Universitário João de Barros Barreto (HUJBB)"
    if local.lower().startswith("serviço do "):
        texto_local = local
    elif local.lower().startswith("do ") or local.lower().startswith("da ") or local.lower().startswith("de "):
        texto_local = f"serviço {local}"
    else:
        texto_local = f"serviço do {local}"

    professor = oportunidade.professor.strip() if (oportunidade and oportunidade.professor) else "Docente Supervisor(a)"
    periodo = oportunidade.periodo.strip() if (oportunidade and oportunidade.periodo) else "período do edital"
    carga_horaria = resultado.carga_horaria_horas if resultado.carga_horaria_horas else 36

    # 4. Corpo do Texto Oficial Homologado (Formatado em A4 Justificado, espaçamento 1.5, Preto)
    p_corpo = doc.add_paragraph()
    p_corpo.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p_corpo.paragraph_format.space_before = Pt(6)
    p_corpo.paragraph_format.space_after = Pt(32)
    p_corpo.paragraph_format.line_spacing = 1.5

    def add_span(text: str, bold: bool = False):
        run = p_corpo.add_run(text)
        run.bold = bold
        run.font.size = Pt(12.5)
        run.font.name = "Calibri"
        run.font.color.rgb = RGBColor(0, 0, 0)
        return run

    add_span("Certificamos que o(a) discente ")
    add_span(nome_aluno, bold=True)
    add_span(", matrícula nº ")
    add_span(matricula, bold=True)
    add_span(", realizou com assiduidade e aproveitamento o estágio voluntário do programa ")
    add_span("ESTÁGIO DE FÉRIAS DA FAMED-UFPA", bold=True)
    add_span(f", {texto_local}")
    add_span(", sob orientação da(o) docente ")
    add_span(professor, bold=True)
    add_span(", no período de ")
    add_span(periodo, bold=True)
    add_span(", cumprindo com êxito a carga horária total de ")
    add_span(f"{carga_horaria} horas", bold=True)
    add_span(".")

    # 5. Data de Emissão por Extenso
    hoje = datetime.date.today()
    meses = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
             'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
    data_formatada = f"Belém-PA, {hoje.day:02d} de {meses[hoje.month - 1]} de {hoje.year}."

    p_data = doc.add_paragraph()
    p_data.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p_data.paragraph_format.space_before = Pt(8)
    p_data.paragraph_format.space_after = Pt(54)
    run_data = p_data.add_run(data_formatada)
    run_data.font.size = Pt(11.5)
    run_data.font.name = "Calibri"
    run_data.font.color.rgb = RGBColor(0, 0, 0)

    # 6. Assinatura do Diretor da FAMED
    p_sig = doc.add_paragraph()
    p_sig.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_sig.paragraph_format.space_before = Pt(24)
    p_sig.paragraph_format.space_after = Pt(2)
    p_sig.paragraph_format.line_spacing = 1.15

    r_linha = p_sig.add_run("___________________________________________________\n")
    r_linha.font.size = Pt(10)
    r_linha.font.color.rgb = RGBColor(0, 0, 0)

    r_dir_nome = p_sig.add_run("Prof. Dr. Cezar Augusto Muniz Caldas\n")
    r_dir_nome.bold = True
    r_dir_nome.font.size = Pt(11)
    r_dir_nome.font.name = "Calibri"
    r_dir_nome.font.color.rgb = RGBColor(0, 0, 0)

    r_dir_cargo = p_sig.add_run("Diretor da Faculdade de Medicina\n")
    r_dir_cargo.font.size = Pt(10)
    r_dir_cargo.font.name = "Calibri"
    r_dir_cargo.font.color.rgb = RGBColor(0, 0, 0)

    r_dir_inst = p_sig.add_run("FAMED / ICM – UFPA")
    r_dir_inst.font.size = Pt(9.5)
    r_dir_inst.font.name = "Calibri"
    r_dir_inst.font.color.rgb = RGBColor(70, 70, 70)

    # 7. Rodapé de Registro Institucional e Código de Autenticidade
    p_auth = doc.add_paragraph()
    p_auth.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_auth.paragraph_format.space_before = Pt(45)
    p_auth.paragraph_format.space_after = Pt(0)
    p_auth.paragraph_format.line_spacing = 1.15

    r_auth = p_auth.add_run(
        f"Registro Institucional nº {edital.numero_oficio} • Protocolo SIPAC: {edital.protocolo} • Código de Autenticidade: {codigo_autenticidade}\n"
        f"A autenticidade deste certificado pode ser verificada junto à Secretaria da FAMED/UFPA."
    )
    r_auth.font.size = Pt(8)
    r_auth.font.italic = True
    r_auth.font.name = "Calibri"
    r_auth.font.color.rgb = RGBColor(140, 140, 140)

    doc.save(output_path)

    # Registra no modelo
    resultado.certificado_codigo = codigo_autenticidade
    resultado.certificado_gerado_em = timezone.now()
    resultado.save()

    return output_path


def gerar_zip_certificados_word(edital: Edital, zip_output_path: str) -> str:
    """Gera um arquivo ZIP com todos os certificados em formato Word (.docx) dos concluintes do edital."""
    concluintes = Resultado.objects.filter(edital=edital, status='APROVADO', concluiu_estagio=True).select_related('candidato', 'oportunidade')

    pasta_temp = os.path.join(settings.MEDIA_ROOT, f"temp_certificados_word_{edital.id}")
    os.makedirs(pasta_temp, exist_ok=True)

    with zipfile.ZipFile(zip_output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for r in concluintes:
            safe_name = re.sub(r'\W+', '_', r.candidato.nome)
            docx_filename = f"Certificado_FAMED_{r.candidato.matricula}_{safe_name}.docx"
            docx_path = os.path.join(pasta_temp, docx_filename)
            gerar_certificado_individual_word(r, docx_path)
            zipf.write(docx_path, arcname=docx_filename)

    return zip_output_path


def gerar_folha_frequencia_individual_pdf(resultado: Resultado, output_path: str) -> str:
    """
    Gera a Folha de Frequência Diária oficial (baseada em '3 - Modelo de FREQUÊNCIA.pdf')
    já pré-preenchida com Local, Supervisor, Nome do Aluno e Matrícula.
    """
    dir_output = os.path.dirname(os.path.abspath(output_path))
    if dir_output:
        os.makedirs(dir_output, exist_ok=True)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm
    )

    styles = getSampleStyleSheet()
    style_head = ParagraphStyle('FreqHead', fontName='Helvetica-Bold', fontSize=9.5, leading=13, alignment=1)
    style_title = ParagraphStyle('FreqTitle', fontName='Helvetica-Bold', fontSize=12, leading=16, alignment=1, textColor=colors.HexColor('#1A365D'))
    style_field = ParagraphStyle('FreqField', fontName='Helvetica', fontSize=8.5, leading=12)
    style_tbl_head = ParagraphStyle('FreqTblHead', fontName='Helvetica-Bold', fontSize=8, leading=10, alignment=1)
    style_tbl_cell = ParagraphStyle('FreqTblCell', fontName='Helvetica', fontSize=7.5, leading=9.5, alignment=1)

    story = []

    # Logos e Cabeçalho Oficial
    brasao_candidates = [
        os.path.join(settings.BASE_DIR, "Brasao-UFPA-colorido.png"),
        os.path.join(settings.BASE_DIR, "estagios/static/img/Brasao-UFPA-colorido.png"),
        "Brasao-UFPA-colorido.png",
        "ufpa_brasao.png",
        os.path.join(settings.BASE_DIR, "estagios/static/img/ufpa_brasao.png"),
    ]
    brasao_path = next((p for p in brasao_candidates if os.path.exists(p)), None)
    logo_path = "Logo Estagio de Ferias FAMED.png"
    if not os.path.exists(logo_path):
        logo_path = os.path.join(settings.BASE_DIR, "estagios/static/img/logo_famed.png")

    img_b = Image(brasao_path, width=1.3 * cm, height=1.85 * cm) if brasao_path else Paragraph("", style_head)
    img_l = Image(logo_path, width=1.6 * cm, height=1.6 * cm) if os.path.exists(logo_path) else Paragraph("", style_head)

    header_table = Table([
        [
            img_b,
            [
                Paragraph("SERVIÇO PÚBLICO FEDERAL", style_head),
                Paragraph("UNIVERSIDADE FEDERAL DO PARÁ", style_head),
                Paragraph("INSTITUTO DE CIÊNCIAS DA SAÚDE • FACULDADE DE MEDICINA", style_head),
            ],
            img_l
        ]
    ], colWidths=[2.2 * cm, 13.6 * cm, 2.2 * cm])
    header_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 4 * mm))

    # Título do Formulário
    story.append(Paragraph("LISTA DE FREQUÊNCIA DE ESTÁGIO DE FÉRIAS", style_title))
    story.append(Spacer(1, 3 * mm))

    # Dados Pré-Preenchidos do Aluno e Local
    c = resultado.candidato
    op = resultado.oportunidade
    info_data = [
        [Paragraph(f"<b>LOCAL:</b> {op.local if op else 'N/A'} (Docente: {op.professor if op else 'N/A'})", style_field)],
        [Paragraph(f"<b>DISCENTE:</b> {c.nome} &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; <b>MATRÍCULA:</b> {c.matricula} &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; <b>CARGA HORÁRIA:</b> {resultado.carga_horaria_horas}h", style_field)],
    ]
    tbl_info = Table(info_data, colWidths=[18 * cm])
    tbl_info.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#CBD5E1')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(tbl_info)
    story.append(Spacer(1, 4 * mm))

    # Tabela Diária para Assinatura (20 Dias de Estágio)
    rows = [[
        Paragraph("DIA", style_tbl_head),
        Paragraph("DATA", style_tbl_head),
        Paragraph("HORÁRIO", style_tbl_head),
        Paragraph("ASSINATURA / SUPERVISOR", style_tbl_head)
    ]]
    for i in range(1, 21):
        rows.append([
            Paragraph(f"{i:02d}", style_tbl_cell),
            Paragraph("", style_tbl_cell),
            Paragraph("", style_tbl_cell),
            Paragraph("", style_tbl_cell),
        ])

    tbl_days = Table(rows, colWidths=[1.8 * cm, 3.2 * cm, 4.0 * cm, 9.0 * cm], rowHeights=[6.0 * mm] + [7.2 * mm] * 20)
    tbl_days.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#94A3B8')),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E2E8F0')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(tbl_days)
    story.append(Spacer(1, 6 * mm))

    # Assinaturas Finais de Homologação
    sig_table = Table([
        [
            Paragraph(f"____________________________________________________<br/><b>Prof(a). {op.professor if op else ''}</b><br/>Docente Supervisor(a) do Estágio - FAMED/UFPA", style_tbl_cell),
            Paragraph("____________________________________________________<br/><b>Assinatura do(a) Discente</b><br/>Estagiário(a) Concluinte", style_tbl_cell),
        ]
    ], colWidths=[9 * cm, 9 * cm])
    story.append(sig_table)

    doc.build(story)
    return output_path


def gerar_zip_folhas_frequencia(edital: Edital, zip_output_path: str) -> str:
    """Gera um arquivo ZIP com as Folhas de Presença diárias em PDF de todos os alunos aprovados."""
    aprovados = Resultado.objects.filter(edital=edital, status='APROVADO').select_related('candidato', 'oportunidade')

    pasta_temp = os.path.join(settings.MEDIA_ROOT, f"temp_folhas_freq_{edital.id}")
    os.makedirs(pasta_temp, exist_ok=True)

    with zipfile.ZipFile(zip_output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for r in aprovados:
            safe_name = re.sub(r'\W+', '_', r.candidato.nome)
            pdf_filename = f"Folha_Frequencia_{r.candidato.matricula}_{safe_name}.pdf"
            pdf_path = os.path.join(pasta_temp, pdf_filename)
            gerar_folha_frequencia_individual_pdf(r, pdf_path)
            zipf.write(pdf_path, arcname=pdf_filename)

    return zip_output_path


# =============================================================================
# 5. DISPARO DE CERTIFICADOS POR E-MAIL (COM SIMULAÇÃO SEGURA)
# =============================================================================

def disparar_certificados_email(edital: Edital, email_teste_destino: Optional[str] = None) -> Dict[str, Any]:
    """
    Envia os certificados individuais por e-mail para todos os alunos concluintes (Aptos).
    Em ambiente de desenvolvimento/teste, grava na pasta 'media/emails_simulados/' sem disparar na internet.
    """
    concluintes = Resultado.objects.filter(edital=edital, status='APROVADO', concluiu_estagio=True).select_related('candidato', 'oportunidade')

    pasta_cert = os.path.join(settings.MEDIA_ROOT, f"certificados_edital_{edital.id}")
    os.makedirs(pasta_cert, exist_ok=True)

    # Pasta de simulação para desenvolvimento
    os.makedirs(settings.EMAIL_FILE_PATH, exist_ok=True)

    total_aptos = concluintes.count()
    enviados_sucesso = 0
    erros = []
    logs_disparo = []

    remetente = settings.DEFAULT_FROM_EMAIL

    for r in concluintes:
        c = r.candidato
        op = r.oportunidade

        # Define destinatário real ou de teste
        destinatario = email_teste_destino if email_teste_destino else c.email

        # Gera o Certificado se ainda não existir
        safe_name = re.sub(r'\W+', '_', c.nome)
        pdf_filename = f"Certificado_{c.matricula}_{safe_name}.pdf"
        pdf_path = os.path.join(pasta_cert, pdf_filename)
        if not os.path.exists(pdf_path):
            gerar_certificado_individual_pdf(r, pdf_path)

        assunto = f"[FAMED/UFPA] Certificado de Conclusão do Estágio de Férias - {c.nome}"

        corpo_texto = (
            f"Prezado(a) discente {c.nome},\n\n"
            f"Parabéns pela conclusão com êxito do estágio de férias da Faculdade de Medicina da UFPA!\n\n"
            f"Serviço: {op.local}\n"
            f"Docente Supervisor(a): {op.professor}\n"
            f"Carga Horária: {r.carga_horaria_horas} horas\n"
            f"Código de Autenticidade: {r.certificado_codigo}\n\n"
            f"Segue em anexo o seu Certificado de Conclusão oficial em formato PDF.\n\n"
            f"Atenciosamente,\n"
            f"Direção da Faculdade de Medicina - FAMED / ICM\n"
            f"Universidade Federal do Pará (UFPA)"
        )

        corpo_html = f"""
        <div style="font-family: Arial, sans-serif; color: #2D3748; line-height: 1.6; max-width: 600px; margin: auto; border: 1px solid #E2E8F0; border-radius: 12px; padding: 24px;">
            <div style="text-align: center; border-bottom: 2px solid #1A365D; padding-bottom: 12px; margin-bottom: 16px;">
                <h2 style="color: #1A365D; margin: 0; font-size: 18px;">UNIVERSIDADE FEDERAL DO PARÁ</h2>
                <h3 style="color: #4A5568; margin: 4px 0 0 0; font-size: 14px;">FACULDADE DE MEDICINA - FAMED/UFPA</h3>
                <p style="color: #718096; margin: 2px 0 0 0; font-size: 12px;">Programa de Estágio de Férias e Extracurricular</p>
            </div>
            
            <p>Prezado(a) discente <b>{c.nome}</b>,</p>
            <p>É com grande satisfação que parabenizamos você pela conclusão do estágio de férias com aproveitamento e assiduidade satisfatória!</p>
            
            <div style="background-color: #F7FAFC; border-left: 4px solid #1A365D; padding: 12px 16px; margin: 16px 0; border-radius: 4px;">
                <p style="margin: 4px 0;"><b>Local do Estágio:</b> {op.local}</p>
                <p style="margin: 4px 0;"><b>Docente Supervisor(a):</b> {op.professor}</p>
                <p style="margin: 4px 0;"><b>Carga Horária:</b> {r.carga_horaria_horas} horas</p>
                <p style="margin: 4px 0;"><b>Código de Autenticidade:</b> <code style="background-color: #EDF2F7; padding: 2px 6px; border-radius: 4px; color: #1A365D;">{r.certificado_codigo}</code></p>
            </div>

            <p>O seu <b>Certificado de Conclusão oficial em PDF</b> encontra-se anexado a este e-mail.</p>
            <p style="font-size: 12px; color: #718096;">Guarde este documento com segurança para comprovação curricular e processos seletivos de residência médica.</p>

            <hr style="border: 0; border-top: 1px solid #E2E8F0; margin: 20px 0;">
            <p style="font-size: 12px; color: #718096; text-align: center;">
                Direção da Faculdade de Medicina - FAMED / ICM • Universidade Federal do Pará
            </p>
        </div>
        """

        try:
            msg = EmailMultiAlternatives(
                subject=assunto,
                body=corpo_texto,
                from_email=remetente,
                to=[destinatario]
            )
            msg.attach_alternative(corpo_html, "text/html")
            
            # Anexa o Certificado em PDF
            if os.path.exists(pdf_path):
                with open(pdf_path, 'rb') as f_pdf:
                    msg.attach(pdf_filename, f_pdf.read(), 'application/pdf')

            msg.send(fail_silently=False)

            r.email_enviado = True
            r.email_enviado_em = timezone.now()
            r.email_log = f"Certificado enviado para {destinatario} em {r.email_enviado_em.strftime('%d/%m/%Y %H:%M')}"
            r.save()

            enviados_sucesso += 1
            logs_disparo.append({
                'aluno': c.nome,
                'email': destinatario,
                'status': 'Enviado com Sucesso',
                'codigo': r.certificado_codigo,
                'anexo': pdf_filename,
            })
        except Exception as e:
            erros.append({'aluno': c.nome, 'erro': str(e)})

    return {
        'total_aptos': total_aptos,
        'enviados_sucesso': enviados_sucesso,
        'erros': erros,
        'logs': logs_disparo,
        'modo_simulacao': 'filebased' in settings.EMAIL_BACKEND,
    }


# =============================================================================
# 6. EXPORTAÇÃO OFICIAL DO EDITAL (PDF E EXCEL)
# =============================================================================

def gerar_pdf_oficial_edital(edital: Edital, output_path: str) -> str:
    """Gera o documento PDF Oficial (Ofício GEP/HUJBB) a partir dos resultados homologados."""
    opp_dict = {}
    for op in edital.oportunidades.all():
        ciclos_list = [c.strip() for c in op.ciclos_permitidos.split(',') if c.strip()]
        opp_obj = Opportunity(
            id=op.codigo_opcao,
            professor=op.professor,
            local=op.local,
            atividade=op.atividade,
            periodo=op.periodo,
            vagas_total=op.vagas_totais,
            ciclos_permitidos=ciclos_list,
        )
        aprovados = Resultado.objects.filter(edital=edital, oportunidade=op, status='APROVADO').order_by('posicao')
        for res in aprovados:
            c = res.candidato
            st = Student(
                matricula=c.matricula,
                nome=c.nome,
                email=c.email,
                telefone=c.telefone,
                crg=c.crg_oficial,
                op1=c.op1,
                op2_list=[],
                timestamp=c.timestamp_inscricao or timezone.now(),
                genero=c.genero,
                is_cotista=c.is_cotista,
                forma_ingresso=c.forma_ingresso,
                ano_ingresso=c.ano_ingresso,
                semestre_atual=c.semestre,
                ciclo=c.ciclo,
                data_nascimento=c.data_nascimento or datetime.date(2000, 1, 1),
            )
            opp_obj.selecionados.append(st)
        opp_dict[op.codigo_opcao] = opp_obj

    generate_pdf_report(
        opportunities=opp_dict,
        students=[],
        output_pdf_path=output_path,
        edital_titulo=edital.semestre,
        oficio_numero=edital.numero_oficio,
        protocolo=edital.protocolo
    )
    return output_path

def gerar_excel_resultado_edital(edital: Edital, output_path: str) -> str:
    """Gera a planilha Excel oficial contendo as 3 abas essenciais solicitadas."""
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        # Aba 1: Aprovados
        rows_aprovados = []
        for res in Resultado.objects.filter(edital=edital, status='APROVADO').select_related('candidato', 'oportunidade'):
            c = res.candidato
            op = res.oportunidade
            rows_aprovados.append({
                'Nome': c.nome,
                'Matrícula': c.matricula,
                'Professor': op.professor if op else '',
                'Estágio / Local': op.local if op else '',
                'Ciclo': c.ciclo.upper(),
                'Modalidade de Entrada': res.modalidade,
                'Opção Atendida': res.opcao_atendida,
                'CRG Oficial': c.crg_oficial,
                'Gênero': 'Feminino' if c.genero == 'F' else 'Masculino',
                'Cotista': 'Sim' if c.is_cotista else 'Não',
                'E-mail': c.email,
                'Contato': c.telefone,
                'Etiqueta / Critério': res.etiqueta_motivo
            })
        pd.DataFrame(rows_aprovados).to_excel(writer, sheet_name='Aprovados', index=False)

        # Aba 2: Cadastro de Reserva
        rows_reserva = []
        for res in Resultado.objects.filter(edital=edital, status='RESERVA').select_related('candidato'):
            c = res.candidato
            rows_reserva.append({
                'Posição': res.posicao,
                'Nome': c.nome,
                'Matrícula': c.matricula,
                'CRG Oficial': c.crg_oficial,
                'Ciclo': c.ciclo.upper(),
                '1ª Opção': f"Opção {c.op1}",
                '2ª Opção': c.op2,
                'Gênero': 'Feminino' if c.genero == 'F' else 'Masculino',
                'Cotista': 'Sim' if c.is_cotista else 'Não',
                'E-mail': c.email,
                'Contato': c.telefone
            })
        pd.DataFrame(rows_reserva).to_excel(writer, sheet_name='Cadastro de Reserva', index=False)

        # Aba 3: Log de Auditoria
        rows_logs = []
        for l in edital.logs.all():
            rows_logs.append({
                'Registro de Decisão': l.registro,
                'Data/Hora': l.criado_em.strftime('%d/%m/%Y %H:%M:%S')
            })
        pd.DataFrame(rows_logs).to_excel(writer, sheet_name='Log de Auditoria', index=False)

    return output_path

def gerar_oficio_word_edital(edital: Edital, output_path: str) -> str:
    """
    Gera o Ofício Oficial de Encaminhamento em formato Word (.docx)
    para a GEP/HUJBB, com cabeçalho institucional, brasão, texto formal e
    tabelas de alunos selecionados por oportunidade (omitindo as que não tiveram aprovados).
    """
    import docx
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls

    doc = docx.Document()
    
    # Configuração de Margens (2 cm em toda a volta)
    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)

    # 1. Brasão da República / UFPA
    brasao_paths = [
        os.path.join(settings.BASE_DIR, 'Brasao-UFPA-colorido.png'),
        os.path.join(settings.BASE_DIR, 'estagios', 'static', 'img', 'Brasao-UFPA-colorido.png'),
        os.path.join(settings.BASE_DIR, 'ufpa_brasao.png'),
        os.path.join(settings.BASE_DIR, 'estagios', 'static', 'img', 'ufpa_brasao.png'),
    ]
    for bp in brasao_paths:
        if os.path.exists(bp):
            p_img = doc.add_paragraph()
            p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run_img = p_img.add_run()
            run_img.add_picture(bp, width=Inches(0.85))
            break

    # 2. Cabeçalho Governamental
    p_head = doc.add_paragraph()
    p_head.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_head.paragraph_format.space_before = Pt(4)
    p_head.paragraph_format.space_after = Pt(2)
    p_head.paragraph_format.line_spacing = 1.15
    
    r1 = p_head.add_run("MINISTÉRIO DA EDUCAÇÃO\n")
    r1.bold = True
    r1.font.size = Pt(10)
    r1.font.name = "Calibri"
    
    r2 = p_head.add_run("UNIVERSIDADE FEDERAL DO PARÁ\n")
    r2.bold = True
    r2.font.size = Pt(10)
    r2.font.name = "Calibri"
    
    r3 = p_head.add_run("INSTITUTO DE CIÊNCIAS MÉDICAS\nFACULDADE DE MEDICINA - FAMED")
    r3.bold = True
    r3.font.size = Pt(9.5)
    r3.font.name = "Calibri"
    r3.font.color.rgb = RGBColor(45, 55, 72)

    # Linha divisória
    p_hr = doc.add_paragraph()
    p_hr.paragraph_format.space_before = Pt(4)
    p_hr.paragraph_format.space_after = Pt(12)
    p_hr_border = parse_xml(f'<w:pBdr {nsdecls("w")}><w:bottom w:val="single" w:sz="6" w:space="1" w:color="086419"/></w:pBdr>')
    p_hr._p.get_or_add_pPr().append(p_hr_border)

    # 3. Metadados do Ofício
    hoje = datetime.date.today()
    meses = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
             'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
    data_formatada = f"{hoje.day:02d} de {meses[hoje.month - 1]} de {hoje.year}"

    p_meta = doc.add_paragraph()
    p_meta.paragraph_format.space_before = Pt(4)
    p_meta.paragraph_format.space_after = Pt(4)
    p_meta.paragraph_format.line_spacing = 1.15
    
    rm1 = p_meta.add_run(f"OFÍCIO Nº {edital.numero_oficio} - FAMED/ICM (11.85.04)\n")
    rm1.bold = True
    rm1.font.size = Pt(9.5)
    rm1.font.name = "Calibri"

    rm2 = p_meta.add_run(f"Nº do Protocolo SIPAC: {edital.protocolo}\n")
    rm2.font.size = Pt(9)
    rm2.font.name = "Calibri"
    rm2.font.color.rgb = RGBColor(74, 85, 104)

    rm3 = p_meta.add_run(f"Belém-PA, {data_formatada}.")
    rm3.font.size = Pt(9)
    rm3.font.name = "Calibri"

    # Destinatário e Assunto
    p_dest = doc.add_paragraph()
    p_dest.paragraph_format.space_before = Pt(10)
    p_dest.paragraph_format.space_after = Pt(10)
    
    rd1 = p_dest.add_run("À Gerência de Ensino e Pesquisa do HUJBB (GEP/HUJBB/EBSERH)\n")
    rd1.bold = True
    rd1.font.size = Pt(10)
    rd1.font.name = "Calibri"
    
    rd2 = p_dest.add_run(f"Assunto: Estágio de Férias FAMED - {edital.titulo} ({edital.semestre})")
    rd2.bold = True
    rd2.font.size = Pt(10)
    rd2.font.name = "Calibri"
    rd2.font.color.rgb = RGBColor(8, 100, 25)

    # Oportunidades com selecionados
    ops_com_alunos = edital.oportunidades.filter(alocados__status='APROVADO').distinct().order_by('id')
    profs_ativos = sorted(list(set(op.professor for op in ops_com_alunos)))
    profs_str = ", ".join(profs_ativos) if profs_ativos else "Docentes da Faculdade de Medicina"

    # Corpo do Ofício
    p_corpo1 = doc.add_paragraph()
    p_corpo1.paragraph_format.space_before = Pt(6)
    p_corpo1.paragraph_format.space_after = Pt(6)
    p_corpo1.paragraph_format.line_spacing = 1.25
    p_corpo1.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    rc1 = p_corpo1.add_run(
        "Prezados(as), encaminhamos anexo a este documento a listagem oficial com os nomes dos estudantes "
        "da Faculdade de Medicina da Universidade Federal do Pará (FAMED/UFPA) devidamente selecionados "
        "para as vagas de estágio de férias com nossos docentes no Hospital Universitário João de Barros "
        "Barreto (HUJBB) e unidades de saúde conveniadas."
    )
    rc1.font.size = Pt(10)
    rc1.font.name = "Calibri"

    p_corpo2 = doc.add_paragraph()
    p_corpo2.paragraph_format.space_before = Pt(6)
    p_corpo2.paragraph_format.space_after = Pt(6)
    p_corpo2.paragraph_format.line_spacing = 1.25
    p_corpo2.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    rc2_1 = p_corpo2.add_run("Nesta edição, os docentes que ofertaram vagas com estudantes alocados foram: ")
    rc2_1.font.size = Pt(10)
    rc2_1.font.name = "Calibri"
    rc2_2 = p_corpo2.add_run(profs_str + ".")
    rc2_2.bold = True
    rc2_2.font.size = Pt(10)
    rc2_2.font.name = "Calibri"

    p_corpo3 = doc.add_paragraph()
    p_corpo3.paragraph_format.space_before = Pt(6)
    p_corpo3.paragraph_format.space_after = Pt(14)
    p_corpo3.paragraph_format.line_spacing = 1.25
    p_corpo3.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    rc3 = p_corpo3.add_run(
        "As informações detalhadas sobre horários, locais, períodos e contatos de cada grupo de alunos "
        "encontram-se no anexo a este documento. Orientamos os estudantes a se dirigirem à GEP-HUJBB "
        "para as providências administrativas e início tempestivo das atividades."
    )
    rc3.font.size = Pt(10)
    rc3.font.name = "Calibri"

    # Assinatura
    p_sig = doc.add_paragraph()
    p_sig.paragraph_format.space_before = Pt(12)
    p_sig.paragraph_format.space_after = Pt(2)
    p_sig.paragraph_format.line_spacing = 1.15
    
    rs1 = p_sig.add_run("Atenciosamente,\n\n")
    rs1.font.size = Pt(10)
    rs1.font.name = "Calibri"

    rs2 = p_sig.add_run("(Assinado digitalmente)\n")
    rs2.bold = True
    rs2.font.size = Pt(9.5)
    rs2.font.name = "Calibri"

    rs3 = p_sig.add_run("DIREÇÃO DA FACULDADE DE MEDICINA\nPROFESSOR DO MAGISTÉRIO SUPERIOR\nFAMED / ICM - UFPA\nMatrícula SIAPE: ###720#2")
    rs3.font.size = Pt(9)
    rs3.font.name = "Calibri"
    rs3.font.color.rgb = RGBColor(74, 85, 104)

    # Box de autenticidade SIPAC
    p_auth = doc.add_paragraph()
    p_auth.paragraph_format.space_before = Pt(16)
    p_auth.paragraph_format.space_after = Pt(4)
    ra = p_auth.add_run(
        f"Documento oficial autenticado eletronicamente. Para verificar a autenticidade, acesse o portal SIPAC-UFPA "
        f"informando o Ofício nº {edital.numero_oficio}, protocolo {edital.protocolo} e data de emissão: {data_formatada}."
    )
    ra.font.size = Pt(8)
    ra.font.italic = True
    ra.font.name = "Calibri"
    ra.font.color.rgb = RGBColor(113, 128, 150)

    # =========================================================================
    # PÁGINA 2: ANEXO COM OS ALUNOS APROVADOS (OMITE OPORTUNIDADES SEM ALUNOS)
    # =========================================================================
    doc.add_page_break()

    p_anexo_title = doc.add_paragraph()
    p_anexo_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_anexo_title.paragraph_format.space_before = Pt(6)
    p_anexo_title.paragraph_format.space_after = Pt(14)
    rat = p_anexo_title.add_run(f"ANEXO I - ALUNOS SELECIONADOS PARA ESTÁGIO DE FÉRIAS DA FAMED\n{edital.titulo} ({edital.semestre})")
    rat.bold = True
    rat.font.size = Pt(12)
    rat.font.name = "Calibri"
    rat.font.color.rgb = RGBColor(8, 100, 25)

    item_idx = 1
    for op in ops_com_alunos:
        alocados = op.alocados.filter(status='APROVADO').select_related('candidato').order_by('posicao')
        if not alocados.exists():
            continue

        # Título da oportunidade
        p_op = doc.add_paragraph()
        p_op.paragraph_format.space_before = Pt(10)
        p_op.paragraph_format.space_after = Pt(4)
        rop_title = p_op.add_run(f"{item_idx}) Seguem abaixo os selecionados para {op.local}")
        rop_title.bold = True
        rop_title.font.size = Pt(10.5)
        rop_title.font.name = "Calibri"
        rop_title.font.color.rgb = RGBColor(8, 100, 25)

        # Informações da vaga
        p_op_info = doc.add_paragraph()
        p_op_info.paragraph_format.space_before = Pt(0)
        p_op_info.paragraph_format.space_after = Pt(4)
        p_op_info.paragraph_format.line_spacing = 1.15
        
        ri1 = p_op_info.add_run(f"Docente Responsável: {op.professor} | Vagas Ofertadas: {op.vagas_totais}\n")
        ri1.bold = True
        ri1.font.size = Pt(9)
        ri1.font.name = "Calibri"

        ri2 = p_op_info.add_run(f"Atividade: {op.atividade or 'Atividades clínicas supervisionadas'} | Período/Horário: {op.periodo}")
        ri2.font.size = Pt(8.5)
        ri2.font.name = "Calibri"
        ri2.font.color.rgb = RGBColor(74, 85, 104)

        # Tabela Word
        table = doc.add_table(rows=1, cols=4)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False

        col_widths = [Inches(2.5), Inches(1.2), Inches(2.2), Inches(1.3)]
        
        # Cabeçalho da Tabela
        hdr_cells = table.rows[0].cells
        headers = ["Nome Completo", "Matrícula", "E-mail Institucional", "Contato"]
        for c_idx, text in enumerate(headers):
            cell = hdr_cells[c_idx]
            cell.width = col_widths[c_idx]
            p_cell = cell.paragraphs[0]
            p_cell.paragraph_format.space_before = Pt(3)
            p_cell.paragraph_format.space_after = Pt(3)
            r_c = p_cell.add_run(text)
            r_c.bold = True
            r_c.font.size = Pt(8.5)
            r_c.font.name = "Calibri"
            r_c.font.color.rgb = RGBColor(255, 255, 255)
            shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="086419"/>')
            cell._tc.get_or_add_tcPr().append(shd)

        # Linhas de Alunos
        for r_idx, res in enumerate(alocados):
            row_cells = table.add_row().cells
            c = res.candidato
            dados = [
                c.nome,
                c.matricula,
                c.email,
                c.telefone or '-'
            ]
            bg_color = "F8FAFC" if (r_idx % 2 == 1) else "FFFFFF"
            for c_idx, val in enumerate(dados):
                cell = row_cells[c_idx]
                cell.width = col_widths[c_idx]
                p_c = cell.paragraphs[0]
                p_c.paragraph_format.space_before = Pt(2.5)
                p_c.paragraph_format.space_after = Pt(2.5)
                run_v = p_c.add_run(val)
                run_v.font.size = Pt(8.5)
                run_v.font.name = "Calibri"
                shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{bg_color}"/>')
                cell._tc.get_or_add_tcPr().append(shd)

        # Orientações sob a tabela
        p_orient = doc.add_paragraph()
        p_orient.paragraph_format.space_before = Pt(3)
        p_orient.paragraph_format.space_after = Pt(8)
        ro = p_orient.add_run(
            f"Instruções: Os estudantes selecionados deverão apresentar-se ao(à) Prof.(a) {op.professor} "
            f"no local e horário informados munidos do comprovante de matrícula."
        )
        ro.font.size = Pt(8)
        ro.font.italic = True
        ro.font.name = "Calibri"
        ro.font.color.rgb = RGBColor(113, 128, 150)

        item_idx += 1

    doc.save(output_path)
    return output_path

