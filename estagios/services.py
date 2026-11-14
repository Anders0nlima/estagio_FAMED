# -*- coding: utf-8 -*-
"""
Serviços de Negócio da Plataforma de Estágios FAMED/UFPA
Integra a higienização de formulários, auditoria do semáforo, motor de classificação e exportações.
"""

import os
import re
import math
import datetime
from typing import Dict, List, Tuple, Any

import pandas as pd
from django.conf import settings
from django.utils import timezone

from .models import Edital, Oportunidade, Candidato, Resultado, LogDecisao
from classificador import (
    clean_crg,
    clean_matricula,
    clean_phone,
    parse_option_id,
    parse_option_list,
    parse_birth_date,
    guess_gender,
    determine_cycle,
    OPORTUNIDADES_CANONICAS,
    allocate_opportunity,
    sort_candidates,
    Student,
    Opportunity,
    generate_pdf_report,
)

def importar_planilhas_edital(edital: Edital) -> Dict[str, Any]:
    """
    Importa as planilhas de vagas, alunos e CSV de cotas para o banco de dados.
    Classifica automaticamente cada candidato no Semáforo de Auditoria.
    """
    # 1. Carregar Oportunidades no Banco
    # Limpa dados anteriores do edital se houver reimportação
    edital.oportunidades.all().delete()
    edital.candidatos.all().delete()
    edital.resultados.all().delete()
    edital.logs.all().delete()

    vagas_map = {}
    for op in OPORTUNIDADES_CANONICAS:
        obj = Oportunidade.objects.create(
            edital=edital,
            codigo_opcao=op['id'],
            professor=op['professor'],
            local=op['local'],
            atividade=op['atividade'],
            periodo=op['periodo'],
            vagas_totais=op['vagas_total'],
            ciclos_permitidos=",".join(op['ciclos_permitidos']),
        )
        vagas_map[op['id']] = obj

    # 2. Carregar CSV de Forma de Ingresso (Cotas) se enviado
    cotas_dict = {}
    csv_path = edital.arquivo_ingresso.path if edital.arquivo_ingresso else 'forma_ingresso.csv'
    if not os.path.exists(csv_path) and os.path.exists('forma_ingresso.csv'):
        csv_path = 'forma_ingresso.csv'

    PALAVRAS_COTA = ['COTA', 'GRUPO', 'PPI', 'RENDA', 'PCD', 'QUILOMBOLA', 'INDÍGENA', 'INDIGENA',
                     'ESCOLA PUBLICA', 'ESCOLA PÚBLICA', 'L1', 'L2', 'L5', 'L6', 'L9', 'L10', 'L13', 'L14']

    if os.path.exists(csv_path):
        for sep in [';', ',', '\t']:
            try:
                df_csv = pd.read_csv(csv_path, sep=sep, encoding='utf-8')
                if len(df_csv.columns) > 1:
                    break
            except UnicodeDecodeError:
                df_csv = pd.read_csv(csv_path, sep=sep, encoding='latin1')
                if len(df_csv.columns) > 1:
                    break

        col_mat_csv = None
        col_nome_csv = None
        col_forma_csv = None
        col_nasc_csv = None
        for c in df_csv.columns:
            c_low = str(c).lower()
            if 'matr' in c_low:
                col_mat_csv = c
            elif 'nome' in c_low:
                col_nome_csv = c
            elif 'forma' in c_low:
                col_forma_csv = c
            elif 'nasc' in c_low:
                col_nasc_csv = c

        for _, r in df_csv.iterrows():
            m = clean_matricula(r[col_mat_csv]) if col_mat_csv else ''
            n = str(r[col_nome_csv]).strip() if col_nome_csv else ''
            f = str(r[col_forma_csv]).strip() if col_forma_csv else 'Ampla Concorrência'
            dn = r[col_nasc_csv] if col_nasc_csv else None
            is_c = any(kw in f.upper() for kw in PALAVRAS_COTA)
            rec = {'forma': f, 'is_cotista': is_c, 'data_nasc': dn}
            if m:
                cotas_dict[m] = rec
            if n:
                cotas_dict[n.lower()] = rec

    # 3. Carregar Inscrições dos Alunos
    alunos_path = edital.arquivo_alunos.path if edital.arquivo_alunos else 'inscricoes_alunos.xlsx'
    if not os.path.exists(alunos_path) and os.path.exists('inscricoes_alunos.xlsx'):
        alunos_path = 'inscricoes_alunos.xlsx'

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
        c_low = col.lower()
        if 'carimbo' in c_low or 'timestamp' in c_low or 'data/hora' in c_low:
            col_timestamp = col
        elif 'nome completo' in c_low:
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

    if col_timestamp:
        df_alunos[col_timestamp] = pd.to_datetime(df_alunos[col_timestamp])
        df_alunos = df_alunos.sort_values(col_timestamp)

    if col_mat:
        df_alunos['mat_clean_temp'] = df_alunos[col_mat].apply(clean_matricula)
        df_alunos = df_alunos.drop_duplicates(subset=['mat_clean_temp'], keep='last')

    total_importados = 0
    verdes = 0
    amarelos = 0
    vermelhos = 0

    for _, row in df_alunos.iterrows():
        raw_mat = row[col_mat] if col_mat else ''
        mat = clean_matricula(raw_mat)
        nome = str(row[col_nome]).strip() if col_nome else ''
        email = str(row[col_email]).strip().lower() if col_email else ''
        tel = clean_phone(row[col_tel]) if col_tel else ''
        raw_crg = str(row[col_crg]).strip() if col_crg else ''
        link = str(row[col_link]).strip() if col_link else ''
        
        op1 = parse_option_id(row[col_op1]) if col_op1 else '1'
        op2_list = parse_option_list(row[col_op2]) if col_op2 else []
        op2_str = ", ".join(op2_list)
        
        ts = row[col_timestamp] if col_timestamp else timezone.now()
        if pd.isna(ts):
            ts = timezone.now()
        elif timezone.is_naive(ts):
            ts = timezone.make_aware(ts)

        # Determinar status no Semáforo de Auditoria
        crg_calculado = clean_crg(raw_crg)
        status_semaforo = 'VERDE'
        motivo = 'CRG consistente e validado automaticamente.'

        # Critérios para o Semáforo
        if any(t in raw_crg.lower() for t in ['não tenho', 'nao tenho', 'não possuo', 'cursando 1º', 'sem crg']):
            status_semaforo = 'VERMELHO'
            motivo = 'Aluno em 1º semestre / sem nota no SIGAA (CRG preliminar 0.0).'
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
        else:
            verdes += 1

        # Dados de Ingresso
        cotas_info = cotas_dict.get(mat) or cotas_dict.get(nome.lower(), {})
        is_cotista = cotas_info.get('is_cotista', False)
        forma_ingresso = cotas_info.get('forma', 'Ampla Concorrência')

        # Ano e Ciclo
        ano_ingresso = edital.ano
        if mat and len(mat) >= 4 and mat[:4].isdigit():
            y = int(mat[:4])
            if 1990 <= y <= edital.ano:
                ano_ingresso = y
        
        semestre_estimado = max(1, min(12, (edital.ano - ano_ingresso) * 2 + 1))
        ciclo = determine_cycle(semestre_estimado)
        data_nasc = parse_birth_date(cotas_info.get('data_nasc'), ano_ingresso)
        genero = guess_gender(nome)

        Candidato.objects.create(
            edital=edital,
            matricula=mat,
            nome=nome,
            email=email,
            telefone=tel,
            crg_digitado=raw_crg,
            crg_oficial=crg_calculado,
            link_historico=link,
            status_auditoria=status_semaforo,
            motivo_auditoria=motivo,
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

def executar_classificacao_edital(edital: Edital) -> Dict[str, Any]:
    """
    Executa o motor de classificação oficial sobre os candidatos homologados.
    Preenche as vagas em duas rodadas (1ª e 2ª opção) respeitando cotas, gênero e ciclos.
    """
    # 1. Carregar Oportunidades do Edital
    opp_dict = {}
    for op in edital.oportunidades.all():
        ciclos_list = [c.strip() for c in op.ciclos_permitidos.split(',') if c.strip()]
        opp_dict[op.codigo_opcao] = Opportunity(
            id=op.codigo_opcao,
            professor=op.professor,
            local=op.local,
            atividade=op.atividade,
            periodo=op.periodo,
            vagas_total=op.vagas_totais,
            ciclos_permitidos=ciclos_list,
            percentual_cotas=edital.percentual_cotas,
            percentual_mulheres=edital.percentual_mulheres,
        )

    # 2. Carregar Candidatos do Edital
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

    # 3. Rodar a Classificação Oficial em 2 Rodadas
    edital.resultados.all().delete()
    edital.logs.all().delete()

    audit_logs = []
    audit_logs.append("================================================================================")
    audit_logs.append(f"EXECUÇÃO DO MOTOR DE CLASSIFICAÇÃO: {edital.titulo} ({edital.semestre})")
    audit_logs.append("================================================================================")

    # --- RODADA 1: 1ª OPÇÃO ---
    audit_logs.append("\n>>> RODADA 1: ALOCAÇÃO EM 1ª OPÇÃO <<<")
    for opp_id, opp in opp_dict.items():
        candidatos_op1 = [s for s in students_list if not s.alocado and s.op1 == opp_id]
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

    # --- RODADA 2: 2ª OPÇÃO (VAGAS REMANESCENTES) ---
    audit_logs.append("\n>>> RODADA 2: ALOCAÇÃO EM 2ª OPÇÃO (REMANEJAMENTO) <<<")
    for opp_id, opp in opp_dict.items():
        vagas_restantes = opp.vagas_total - len(opp.selecionados)
        if vagas_restantes <= 0:
            continue

        candidatos_op2 = [s for s in students_list if not s.alocado and (opp_id in s.op2_list)]
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

    # 4. Salvar Resultados no Banco de Dados
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
                etiqueta_motivo=etiqueta
            )
            alocados_count += 1

    # Cadastro de Reserva (Alunos que não foram alocados em nenhuma vaga)
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

    # Salvar Trilha de Auditoria
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

def gerar_pdf_oficial_edital(edital: Edital, output_path: str) -> str:
    """Gera o documento PDF Oficial (Ofício GEP/HUJBB) a partir dos resultados homologados."""
    # Prepara dicionário de oportunidades com alunos selecionados
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
        # Buscar aprovados desta oportunidade
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
    """
    Gera a planilha Excel oficial solicitada no Bloco 5 com as 3 abas essenciais:
    - Aba 1 (Aprovados): Nome, Matrícula, Professor/Estágio, Ciclo, Modalidade de Entrada e Opção.
    - Aba 2 (Cadastro de Reserva): Lista ordenada dos alunos que não passaram.
    - Aba 3 (Log de Auditoria): Justificativas transparentes das decisões.
    """
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
