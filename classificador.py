#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
MOTOR DE CLASSIFICAÇÃO DE ESTÁGIO DE FÉRIAS - FAMED / UFPA
=============================================================================
Sistema de Triagem, Classificação e Alocação de Candidatos para Estágios
de Férias da Faculdade de Medicina da Universidade Federal do Pará (UFPA).

Regras Implementadas:
- Passo A: Divisão por Oportunidades, Vagas e Ciclos (Básico, Clínico, Internato)
- Passo B: Critérios de Desempate (CRG decrescente, Idade/Nascimento, Timestamp)
- Passo C: Ampla Concorrência (AC), Cotas e Ação Afirmativa de 50% de Mulheres
  * Preenchimento da Ampla Concorrência (AC) primeiro
  * Garantia de mínimo de 50% de mulheres na AC (com permuta do menor homem pela maior mulher)
  * Preenchimento das Cotas com cotistas remanescentes
  * Garantia de mínimo de 50% de mulheres nas Cotas
  * Reversão de vagas de cotas não preenchidas para a Ampla Concorrência
- Passo D: Remanejamento de 1ª e 2ª Opção (Rodada 1 e Rodada 2)
- Casos de borda: tratamento de dados sujos (CRG com vírgula/texto, números ímpares,
  duplicidades de formulário, matrícula com erro).
- Geração de Ofício Oficial em PDF (padrão GEP/HUJBB - FAMED) e Relatório Excel.
=============================================================================
"""

import os
import sys
import re
import math
import argparse
import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any

import pandas as pd
import numpy as np

# ReportLab imports for PDF generation
from reportlab.lib.pagesizes import A4
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
    PageBreak,
    HRFlowable,
)
from reportlab.pdfgen import canvas

# =============================================================================
# 1. DICIONÁRIO E HEURÍSTICA DE IDENTIFICAÇÃO DE GÊNERO (NOMES BRASILEIROS)
# =============================================================================

# Base abrangente de nomes brasileiros do Censo IBGE (garante funcionamento 100% offline)
NOMES_FEMININOS_BASE = {
    'adriana', 'adriane', 'adriele', 'agata', 'agatha', 'alana', 'alanis', 'alessandra',
    'alice', 'alicia', 'aline', 'amanda', 'ana', 'analice', 'andreia', 'andressa', 'anita',
    'anna', 'anny', 'antonia', 'ariane', 'ariel', 'barbara', 'beatriz', 'bianca', 'bruna',
    'camila', 'camilla', 'camille', 'carla', 'carolina', 'caroline', 'catarina', 'cecilia',
    'clara', 'clarice', 'claudia', 'cris', 'cristiana', 'cristiane', 'cristina', 'daiane',
    'dalva', 'daniela', 'danielle', 'dayane', 'dayanne', 'debora', 'denise', 'diana',
    'eduarda', 'elaine', 'elena', 'elisa', 'elisabete', 'elizabete', 'elizete', 'ellen',
    'eloisa', 'emanoela', 'emanuela', 'emanuele', 'emilly', 'emily', 'erica', 'erika',
    'ester', 'esther', 'eva', 'evelyn', 'fabiana', 'fabricia', 'fatima', 'fernanda',
    'flavia', 'gabriela', 'gabriele', 'gabrielly', 'giovanna', 'gisele', 'giulia', 'helen',
    'helena', 'heloisa', 'iara', 'ingrid', 'isabel', 'isabela', 'isabella', 'isabelle',
    'isadora', 'isis', 'isolda', 'ivana', 'jacqueline', 'janaina', 'jaqueline', 'jessica',
    'jhulie', 'joana', 'jordana', 'josuelem', 'joyce', 'julia', 'juliana', 'juliane',
    'jullyani', 'kaliana', 'kamila', 'karen', 'karina', 'karla', 'karolina', 'kaylana',
    'kelly', 'lais', 'lanna', 'lara', 'larissa', 'laura', 'layla', 'leticia', 'lia',
    'ligia', 'linda', 'livia', 'lorena', 'loren', 'lóren', 'louise', 'luana', 'luciana',
    'luisa', 'luiza', 'luna', 'madalena', 'mahara', 'maira', 'manoela', 'manuela',
    'marcela', 'marcia', 'maria', 'mariana', 'marina', 'marissol', 'marta', 'mayara',
    'melissa', 'milena', 'mirella', 'monica', 'nadia', 'naiara', 'nara', 'natacha',
    'natalia', 'nathalia', 'nicoly', 'nicole', 'noemi', 'olivia', 'paloma', 'pamela',
    'paola', 'patricia', 'paula', 'priscila', 'rafaela', 'raissa', 'raquel', 'rebeca',
    'renata', 'rita', 'roberta', 'rosana', 'sabrina', 'samara', 'sandra', 'sara', 'sarah',
    'silvana', 'silvia', 'simone', 'sofia', 'sophia', 'stefany', 'stephany', 'suelen',
    'suzana', 'tais', 'taissa', 'talita', 'tatiana', 'tayse', 'tereza', 'thaina', 'thais',
    'valeria', 'vanessa', 'vera', 'victoria', 'vitoria', 'vivian', 'viviane', 'yara', 'yasmim',
    'yasmin', 'yuka'
}

NOMES_MASCULINOS_BASE = {
    'afonso', 'airton', 'alberto', 'alessandro', 'alex', 'alexandre', 'alisson', 'allan',
    'alvaro', 'andre', 'antonio', 'arthur', 'artur', 'augusto', 'bernardo', 'breno',
    'bruno', 'caio', 'carlos', 'casimiro', 'cezar', 'claudio', 'daniel', 'danilo', 'davi',
    'david', 'deivison', 'diego', 'diogo', 'douglas', 'eduardo', 'elias', 'emerson',
    'enrico', 'enrique', 'enzo', 'erik', 'evandro', 'fabiano', 'fabio', 'fabricio',
    'felipe', 'fernando', 'filipe', 'flavio', 'francisco', 'gabriel', 'geraldo', 'gilberto',
    'giovanni', 'guilherme', 'gustavo', 'halisson', 'hálisson', 'heitor', 'helio', 'henrique',
    'hugo', 'ian', 'igor', 'isac', 'italo', 'iuri', 'ivan', 'jean', 'joao', 'joão',
    'joaquim', 'jonas', 'jonathan', 'jorge', 'jose', 'josivaldo', 'juliano', 'julio',
    'kaiky', 'kayo', 'keveni', 'leandro', 'leo', 'leonardo', 'luan', 'lucas', 'luciano',
    'luis', 'luiz', 'marcelo', 'marcio', 'marco', 'marcos', 'marcus', 'mateus', 'matheus',
    'mauricio', 'melquisedequi', 'michel', 'miguel', 'murilo', 'nelson', 'nicolas',
    'otavio', 'paulo', 'pedro', 'rafael', 'ramon', 'raul', 'renan', 'renato', 'rhamon',
    'ricardo', 'robert', 'roberto', 'rodrigo', 'rogerio', 'samuel', 'sergio', 'tiago',
    'thiago', 'tonieliton', 'toniéliton', 'victor', 'vinicius', 'vitor', 'wagner',
    'walter', 'wesley', 'williams', 'willian', 'yuri'
}

def remove_accents(text: str) -> str:
    """Remove acentos para comparação uniforme de nomes."""
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

def normalize_name(name: Any) -> str:
    """Normaliza nome completo para cruzamento seguro (sem acentos, minúsculo e sem espaços extras)."""
    if not name or pd.isna(name):
        return ''
    s = str(name).strip()
    if s.lower() in ('nan', 'none', 'null'):
        return ''
    return ' '.join(remove_accents(s).lower().split())

def guess_gender(full_name: str) -> str:
    """
    Prediz o gênero com base no primeiro nome.
    Utiliza biblioteca externa se disponível; caso contrário, recorre a base
    demográfica do Censo IBGE e heurística fonética. Retorna 'F' ou 'M'.
    """
    if not full_name or not isinstance(full_name, str):
        return 'F'  # default neutro
    
    first_name = full_name.strip().split()[0].lower()
    first_name_clean = remove_accents(first_name)
    
    # 1. Verificação direta no dicionário de nomes femininos
    if first_name in NOMES_FEMININOS_BASE or first_name_clean in NOMES_FEMININOS_BASE:
        return 'F'
    
    # 2. Verificação direta no dicionário de nomes masculinos
    if first_name in NOMES_MASCULINOS_BASE or first_name_clean in NOMES_MASCULINOS_BASE:
        return 'M'
    
    # 3. Tentativa de uso do pacote gender-guesser-br se instalado e funcional
    try:
        from gender_guesser_br import Genero
        g = Genero(first_name)
        res = g()
        if res == 'feminino':
            return 'F'
        elif res == 'masculino':
            return 'M'
    except Exception:
        pass
    
    # 4. Heurísticas baseadas em terminações típicas da língua portuguesa
    if first_name_clean.endswith(('a', 'ia', 'ane', 'ete', 'ele', 'elly', 'any', 'ice', 'is', 'na')):
        return 'F'
    if first_name_clean.endswith(('o', 'os', 'or', 'on', 'el', 'er', 'ton', 'son', 'io', 'us')):
        return 'M'
    
    return 'F'  # fallback seguro


# =============================================================================
# 2. PARSERS E LIMPEZA DE DADOS
# =============================================================================

def clean_crg(raw_crg: Any) -> float:
    """
    Limpa e padroniza notas de CRG (Coeficiente de Rendimento Geral).
    Trata:
    - Vírgula como separador decimal (ex: 8,5 -> 8.5)
    - Valores digitados sem ponto decimal (ex: 8192 -> 8.192, 9919 -> 9.919)
    - Textos informativos de alunos (ex: '3.2 (é baixo porque abandonei...)')
    - Textos de alunos sem CRG (ex: 'Não tenho ainda (cursando 1º semestre)' -> 0.0)
    """
    if pd.isna(raw_crg):
        return 0.0
    
    raw_str = str(raw_crg).strip()
    if not raw_str:
        return 0.0
    
    # Termos comuns de alunos recém-ingressos
    nao_tem_termos = ['não possuo', 'nao possuo', 'não tenho', 'nao tenho', 'sem crg', 'cursando', 'nenhum', 'nan']
    if any(t in raw_str.lower() for t in nao_tem_termos):
        return 0.0
    
    # Extrair primeiro padrão numérico da string (permite lidar com observações em parênteses)
    # Ex: '3.2 (é baixo porque...)' -> extrai '3.2'
    match = re.search(r'(\d+[\.,]?\d*)', raw_str)
    if not match:
        return 0.0
    
    num_str = match.group(1).replace(',', '.')
    try:
        val = float(num_str)
    except ValueError:
        return 0.0
    
    # Se o valor for digitado em milhares (ex: 8192, 7725, 9659), ajusta para escala de 0 a 10
    while val > 10.0 and val > 0:
        val /= 10.0
    
    return round(val, 4)

def clean_matricula(raw_mat: Any) -> str:
    """Limpa e formata a matrícula do aluno."""
    if pd.isna(raw_mat):
        return ''
    s = str(raw_mat).strip()
    # se veio como float 202309740124.0
    if s.endswith('.0'):
        s = s[:-2]
    # extrair apenas números
    digits = re.sub(r'\D', '', s)
    return digits if digits else s

def clean_phone(raw_phone: Any) -> str:
    """Padroniza números de telefone para o formato (XX) XXXXX-XXXX ou (XX) XXXX-XXXX."""
    if pd.isna(raw_phone):
        return ''
    s = str(raw_phone).strip()
    if s.endswith('.0'):
        s = s[:-2]
    digits = re.sub(r'\D', '', s)
    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
    elif len(digits) == 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
    elif len(digits) > 11:
        # Se veio com 55 (DDI Brasil)
        if digits.startswith('55') and len(digits) in (12, 13):
            d = digits[2:]
            return clean_phone(d)
        return digits
    return s

def parse_option_id(raw_val: Any) -> Optional[str]:
    """
    Extrai identificador padronizado de opção (ex: 'Opção 9' -> '9', '3.1' -> '3.1',
    '16) Ambulatório...' -> '16', '14' -> '14').
    """
    if pd.isna(raw_val):
        return None
    s = str(raw_val).strip()
    if not s or s.lower() in ('nan', 'none', 'nenhuma', 'não', 'nao', '-'):
        return None
    
    # Caso como 3.1
    m_float = re.match(r'^(\d+\.\d+)', s)
    if m_float:
        return m_float.group(1)
    
    # Extrai o número da opção
    m = re.search(r'(?:op[çc][ãa]o\s*)?(\d+)', s, re.IGNORECASE)
    if m:
        return str(int(m.group(1)))
    return s

def parse_option_list(raw_val: Any) -> List[str]:
    """
    Extrai lista de opções em ordem de preferência quando o aluno digita
    múltiplas escolhas na segunda opção (ex: '14 ou 15 ou 16' -> ['14', '15', '16']).
    """
    if pd.isna(raw_val):
        return []
    s = str(raw_val).strip()
    s_low = s.lower()
    if not s or s_low in ('nan', 'none', 'nenhuma', 'não', 'nao', '-') or 'não tenho interesse' in s_low or 'nao tenho interesse' in s_low:
        return []
    
    # Procura todos os números ou códigos presentes
    tokens = re.split(r'[,;/]|\bou\b|\be\b', s, flags=re.IGNORECASE)
    res = []
    for t in tokens:
        opt = parse_option_id(t)
        if opt and opt not in res:
            res.append(opt)
    return res

def parse_birth_date(raw_date: Any, admission_year: int) -> datetime.date:
    """Converte ou estima a data de nascimento para desempate por idade."""
    if pd.notna(raw_date):
        s = str(raw_date).strip()
        # formatos DD/MM/AAAA ou AAAA-MM-DD
        for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%d/%m/%y'):
            try:
                return datetime.datetime.strptime(s, fmt).date()
            except ValueError:
                continue
    # Fallback seguro: estima nascimento a partir do ano de ingresso (19 anos na entrada)
    safe_year = admission_year - 19 if 1980 <= admission_year <= 2030 else 2002
    return datetime.date(safe_year, 1, 1)

def determine_cycle(semester: int) -> str:
    """
    Determina o ciclo do aluno com base no semestre cursado:
    - Básico: 1º ao 4º semestre (1º e 2º ano)
    - Clínico: 5º ao 8º semestre (3º e 4º ano)
    - Internato: 9º ao 12º semestre (5º e 6º ano)
    """
    if semester <= 4:
        return 'basico'
    elif semester <= 8:
        return 'clinico'
    else:
        return 'internato'

CYCLE_HIERARCHY = ['basico', 'clinico', 'internato']

def parse_semestres_permitidos(text: Any) -> List[int]:
    """
    Interpreta requisitos de semestres a partir de texto livre das vagas ou códigos de ciclo.
    Exemplos:
    - 'Alunos que cursaram do 9º ao 11º semestre em 2026.4.' -> [9, 10, 11]
    - 'Alunos que cursaram 7º ou 8º semestre em 2026.4.' -> [7, 8]
    - 'Alunos que cursaram do 5º ao 8º semestre em 2026.4.' -> [5, 6, 7, 8]
    - 'A partir do 7o semestre' -> [7, 8, 9, 10, 11, 12]
    - 'clinico,internato' -> [5, 6, 7, 8, 9, 10, 11, 12]
    - 'basico' -> [1, 2, 3, 4]
    - 'Qualquer semestre' -> [1, 2, ..., 12]
    """
    if not text:
        return list(range(1, 13))
    t = str(text).lower().strip()
    if 'qualquer' in t or 'todos' in t or t == 'todos os semestres':
        return list(range(1, 13))
    
    # Remove anos letivos como 2026.4, 2026.1, 2026/2, 2026, 2027
    t_clean = re.sub(r'\b20\d{2}(?:[\./]\d+)?\b', ' ', t)
    # Remove datas como 24/7/26, 01/07 a 17/07
    t_clean = re.sub(r'\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b', ' ', t_clean)
    # Remove horários como 8-12h, 15h às 19h, 8h
    t_clean = re.sub(r'\b\d{1,2}(?:h\d{0,2})?\s*(?:às|as|-)\s*\d{1,2}h\b', ' ', t_clean)
    t_clean = re.sub(r'\b\d{1,2}h\b', ' ', t_clean)

    semestres = set()
    # Ciclos de formação
    if 'basico' in t_clean or 'básico' in t_clean:
        semestres.update([1, 2, 3, 4])
    if 'clinico' in t_clean or 'clínico' in t_clean:
        semestres.update([5, 6, 7, 8])
    if 'internato' in t_clean:
        semestres.update([9, 10, 11, 12])
        
    # 'a partir do X'
    m_partir = re.search(r'a partir d[oe]\s*(\d+)', t_clean)
    if m_partir:
        start = int(m_partir.group(1))
        semestres.update(range(start, 13))
        
    # Intervalos: '1o-7o', '5o-7o', '10-11o', '9º ao 11º', '1° ao 7°', '5 a 8'
    range_matches = re.findall(r'(\d+)\s*(?:[ºo°]?\s*(?:ao|a|-)\s*)(\d+)\s*[ºo°]?', t_clean)
    for start_s, end_s in range_matches:
        s_val, e_val = int(start_s), int(end_s)
        if 1 <= s_val <= 12 and 1 <= e_val <= 12 and s_val <= e_val:
            semestres.update(range(s_val, e_val + 1))
            
    # Palavras ordinais
    if 'sétimo' in t_clean or 'setimo' in t_clean: semestres.add(7)
    if 'oitavo' in t_clean: semestres.add(8)
    if 'nono' in t_clean: semestres.add(9)
    if 'décimo' in t_clean or 'decimo' in t_clean: semestres.add(10)

    # Números ordinais ou com palavra 'semestre'
    num_matches = re.findall(r'(\d+)\s*(?:[ºo°]|semestre)', t_clean)
    for n_str in num_matches:
        val = int(n_str)
        if 1 <= val <= 12:
            semestres.add(val)

    # Fallback se apenas números separados por vírgula ou espaço (ex: '7, 8' ou '9 10 11')
    if not semestres:
        for n_str in re.findall(r'\b(\d+)\b', t_clean):
            val = int(n_str)
            if 1 <= val <= 12:
                semestres.add(val)

    return sorted(list(semestres)) if semestres else list(range(1, 13))


# =============================================================================
# 3. ESTRUTURAS DE DADOS
# =============================================================================

@dataclass
class Student:
    matricula: str
    nome: str
    email: str
    telefone: str
    crg: float
    op1: str
    op2_list: List[str]
    timestamp: datetime.datetime
    genero: str  # 'F' ou 'M'
    is_cotista: bool
    forma_ingresso: str
    ano_ingresso: int
    semestre_atual: int
    ciclo: str  # 'basico', 'clinico', 'internato'
    data_nascimento: datetime.date
    
    # Campos de Alocação
    alocado: bool = False
    alocado_em: Optional[str] = None
    alocado_opcao: int = 0  # 1 (1ª opção) ou 2 (2ª opção)
    modalidade: Optional[str] = None  # 'AMPLA', 'COTA', 'AMPLA_GENERO', 'COTA_GENERO'
    motivo_alocacao: str = ''
    historico_auditoria: List[str] = field(default_factory=list)

@dataclass
class Opportunity:
    id: str
    professor: str
    local: str
    atividade: str
    periodo: str
    vagas_total: int
    ciclos_permitidos: List[str]  # ['basico', 'clinico', 'internato']
    semestres_permitidos: List[int] = field(default_factory=list)
    vagas_por_ciclo: Dict[str, int] = field(default_factory=dict)
    percentual_cotas: float = 0.5
    percentual_mulheres: float = 0.5
    dividir_por_ciclo: bool = True
    
    # Alocados finais
    selecionados: List[Student] = field(default_factory=list)
    lista_espera: List[Student] = field(default_factory=list)
    logs: List[str] = field(default_factory=list)


# =============================================================================
# 4. CARREGAMENTO E MAPEAMENTO DE OPORTUNIDADES
# =============================================================================

# Definição canônica das 16 oportunidades oferecidas pelos docentes no edital da FAMED
OPORTUNIDADES_CANONICAS = [
    {
        'id': '1',
        'professor': 'Lucas Lobato Acatauassu Nunes',
        'local': 'Ambulatório de Nefrologia - Hospital Universitário João de Barros Barreto',
        'atividade': 'Ambulatório de nefrologia',
        'periodo': 'Quintas-feiras 06/08 e 13/08 (8-12h e 14-18h) e Sextas-feiras 07/08 e 14/08 (8-12h)',
        'vagas_total': 8,
        'ciclos_permitidos': ['internato'],
    },
    {
        'id': '2',
        'professor': 'Adriana Rodrigues Barretto',
        'local': 'Enfermaria de Pneumologia - Hospital Universitário João de Barros Barreto',
        'atividade': 'Visita em enfermaria de pneumologia',
        'periodo': 'Todo o período (7h às 11h)',
        'vagas_total': 2,
        'ciclos_permitidos': ['clinico', 'internato'],
    },
    {
        'id': '3',
        'professor': 'Yuka Tsuchiyama',
        'local': 'Enfermaria de Pneumologia - Hospital Universitário João de Barros Barreto',
        'atividade': 'Visita em âmbito hospitalar em pacientes internados por comorbidades pulmonares',
        'periodo': '01/07 a 29/07 de segunda a sexta (8h às 12h)',
        'vagas_total': 1,
        'ciclos_permitidos': ['internato'],
    },
    {
        'id': '3.1',
        'professor': 'Yuka Tsuchiyama',
        'local': 'Enfermaria de Pneumologia - Hospital Universitário João de Barros Barreto (Turma Suplementar)',
        'atividade': 'Visita em âmbito hospitalar em pacientes internados por comorbidades pulmonares',
        'periodo': '01/07 a 29/07 de segunda a sexta (8h às 12h)',
        'vagas_total': 1,
        'ciclos_permitidos': ['clinico', 'internato'],
    },
    {
        'id': '4',
        'professor': 'Williams Barra',
        'local': 'Ambulatório de Oncologia UNACON - Hospital Universitário João de Barros Barreto',
        'atividade': 'Atendimento Ambulatorial em Oncologia (Período 1)',
        'periodo': '01/07 a 17/07 (Disponibilidade de 8h diárias)',
        'vagas_total': 1,
        'ciclos_permitidos': ['clinico', 'internato'],
    },
    {
        'id': '5',
        'professor': 'João Alberto Maradei',
        'local': 'Hospital Maradei',
        'atividade': 'Acompanhamento ambulatorial e cirúrgico em ortopedia (Alunos com Ortopedia concluída)',
        'periodo': '24/07 a 23/08: segunda, quarta e sexta (7h às 19h)',
        'vagas_total': 1,
        'ciclos_permitidos': ['clinico', 'internato'],
    },
    {
        'id': '6',
        'professor': 'Simone Regina Souza da Silva Conde',
        'local': 'Enfermaria de Clínica Médica - Hospital Universitário João de Barros Barreto',
        'atividade': 'Enfermaria CM: desenvolvimento de raciocínio clínico dentro da vivência hospitalar',
        'periodo': '01 a 29 de julho (segunda a quinta pela manhã)',
        'vagas_total': 2,
        'ciclos_permitidos': ['internato'],
    },
    {
        'id': '7',
        'professor': 'Simone Regina Souza da Silva Conde',
        'local': 'Ambulatório de Hepatologia - Hospital Universitário João de Barros Barreto',
        'atividade': 'Ambulatório de Hepatologia: experiência dos casos ambulatoriais na temática de hepatologia',
        'periodo': '01 a 29 de julho (sextas-feiras pela manhã)',
        'vagas_total': 3,
        'ciclos_permitidos': ['internato'],
    },
    {
        'id': '8',
        'professor': 'Carla Leonor Melo Vinagre Machado',
        'local': 'Ambulatório de Autismo - Casmuc / UFPA',
        'atividade': 'Atendimento ambulatorial em Transtorno do Espectro Autista (TEA)',
        'periodo': 'Terças à tarde e sextas pela manhã (03/08 a 23/08)',
        'vagas_total': 2,
        'ciclos_permitidos': ['basico', 'clinico'],
    },
    {
        'id': '9',
        'professor': 'Carla Leonor Melo Vinagre Machado',
        'local': 'Ambulatório de Doenças Raras - UREMIA',
        'atividade': 'Atendimento ambulatorial em Doenças Raras',
        'periodo': 'Terças-feiras pela manhã (03/08 a 23/08)',
        'vagas_total': 2,
        'ciclos_permitidos': ['basico', 'clinico'],
    },
    {
        'id': '10',
        'professor': 'Carla Leonor Melo Vinagre Machado',
        'local': 'Ambulatório de Puericultura Pediátrica - Usina da Paz Guamá',
        'atividade': 'Atendimento ambulatorial em Puericultura Pediátrica',
        'periodo': 'Quintas-feiras à tarde (03/08 a 23/08)',
        'vagas_total': 2,
        'ciclos_permitidos': ['basico', 'clinico'],
    },
    {
        'id': '11',
        'professor': 'Williams Barra',
        'local': 'Ambulatório de Oncologia UNACON - Hospital Universitário João de Barros Barreto',
        'atividade': 'Atendimento Ambulatorial em Oncologia (Período 2)',
        'periodo': '03/08 a 21/08 (Disponibilidade de 8h diárias)',
        'vagas_total': 1,
        'ciclos_permitidos': ['clinico', 'internato'],
    },
    {
        'id': '12',
        'professor': 'João Alberto Maradei',
        'local': 'Hospital Maradei',
        'atividade': 'Acompanhamento ambulatorial e cirúrgico em ortopedia (Alunos do Internato)',
        'periodo': '01/07 a 17/07: segunda, quarta e sexta (7h às 19h)',
        'vagas_total': 1,
        'ciclos_permitidos': ['internato'],
    },
    {
        'id': '13',
        'professor': 'Luciano Moura de Assunção',
        'local': 'Enfermaria de Clínica Médica - Hospital Universitário João de Barros Barreto',
        'atividade': 'Enfermaria de Clínica Médica',
        'periodo': '01/07 a 17/07',
        'vagas_total': 1,
        'ciclos_permitidos': ['basico', 'clinico', 'internato'],
    },
    {
        'id': '14',
        'professor': 'Igor Beltrão Duarte Fernandes',
        'local': 'Enfermaria de Clínica Médica - Hospital Universitário João de Barros Barreto',
        'atividade': 'Discussões de casos clínicos da enfermaria, raciocínio clínico e temas relevantes',
        'periodo': '12/07 a 31/07 (15h às 19h) e mês de agosto (15h às 19h)',
        'vagas_total': 1,
        'ciclos_permitidos': ['basico', 'clinico', 'internato'],
    },
    {
        'id': '15',
        'professor': 'Matheus Rocha Maia',
        'local': 'Enfermaria de Clínica Médica - Hospital Universitário João de Barros Barreto',
        'atividade': 'Visita e condutas na enfermaria de clínica médica',
        'periodo': '01/12 a 27/02 (ou período de férias)',
        'vagas_total': 2,
        'ciclos_permitidos': ['clinico', 'internato'],
    },
    {
        'id': '16',
        'professor': 'Nara Lins',
        'local': 'Ambulatório de Clínica Médica - Hospital Universitário João de Barros Barreto',
        'atividade': 'Atendimento ambulatorial em clínica médica',
        'periodo': 'Quintas-feiras à tarde',
        'vagas_total': 2,
        'ciclos_permitidos': ['clinico', 'internato'],
    },
]

def parse_opportunities_docx(docx_path: str) -> List[Dict[str, Any]]:
    """
    Extrai as oportunidades de estágio diretamente do documento Word organizado pela Diretoria
    (ex: 'Estagio_de_Ferias_FAMED_2027_Candidatura.docx').
    Formato esperado nos parágrafos:
      '1) Local – Docente responsável: Prof. Atividades: ... Período: ... Vagas: N ... Perfil do(a) estudante: ...'
    """
    import docx

    doc = docx.Document(docx_path)
    textos = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            row_txt = " ".join(c.text.strip() for c in row.cells if c.text.strip())
            if row_txt:
                textos.append(row_txt)

    parsed_ops: List[Dict[str, Any]] = []
    seen_ids = set()

    # Marcadores flexíveis das seções dentro de cada parágrafo de oportunidade
    sec_pattern = re.compile(
        r'(Docente\s+respons[áa]vel\s*:|Atividades?\s*:|Per[íi]odo\s*:|Vagas?\s*:|Perfil(?:\s+do\(?a\)?\s+estudante)?\s*:)',
        re.IGNORECASE
    )

    for txt in textos:
        m_id = re.match(r'^(\d+(?:\.\d+)?)\)\s*(.+)$', txt)
        if not m_id:
            continue

        op_id = m_id.group(1).strip()
        if op_id in seen_ids:
            continue

        rest = m_id.group(2).strip()
        parts = sec_pattern.split(rest)
        # parts[0] é o local (antes de "Docente responsável:")
        local = re.sub(r'[\s–—-]+$', '', parts[0]).strip() or f"Local da Opção {op_id}"

        sections: Dict[str, str] = {}
        for idx in range(1, len(parts) - 1, 2):
            key_raw = remove_accents(parts[idx].lower())
            val_raw = parts[idx + 1].strip()
            val_clean = re.sub(r'[.\s]+$', '', val_raw).strip()
            if 'docente' in key_raw:
                sections['professor'] = val_clean
            elif 'atividade' in key_raw:
                sections['atividade'] = val_clean
            elif 'periodo' in key_raw:
                sections['periodo'] = val_clean
            elif 'vaga' in key_raw:
                sections['vagas'] = val_clean
            elif 'perfil' in key_raw:
                sections['perfil'] = val_clean

        if not sections.get('professor') and not sections.get('vagas'):
            continue

        professor = sections.get('professor', 'Docente Responsável')
        atividade = sections.get('atividade', '')
        periodo = sections.get('periodo', 'A definir')

        vagas_str = sections.get('vagas', '1')
        m_vaga = re.search(r'(\d+)', vagas_str)
        vagas_total = int(m_vaga.group(1)) if m_vaga else 1

        perfil = sections.get('perfil', '')
        sems = parse_semestres_permitidos(perfil)
        ciclos = sorted(
            list({determine_cycle(s) for s in sems}),
            key=lambda c: CYCLE_HIERARCHY.index(c)
        )

        seen_ids.add(op_id)
        parsed_ops.append({
            'id': op_id,
            'professor': professor,
            'local': local,
            'atividade': atividade,
            'periodo': periodo,
            'vagas_total': vagas_total,
            'ciclos_permitidos': ciclos,
            'semestres_permitidos': sems,
        })

    return parsed_ops

def load_opportunities(vagas_file: Optional[str] = None) -> Dict[str, Opportunity]:
    """
    Carrega as oportunidades de estágio.
    Quando fornecido um arquivo .docx estruturado pela Diretoria, extrai dinamicamente todas as ofertas.
    Caso contrário, utiliza a lista canônica de fallback.
    """
    source_list = OPORTUNIDADES_CANONICAS
    if vagas_file and os.path.exists(vagas_file) and str(vagas_file).lower().endswith('.docx'):
        parsed = parse_opportunities_docx(vagas_file)
        if parsed:
            source_list = parsed

    opp_dict = {}
    for op in source_list:
        sems = op.get('semestres_permitidos')
        if not sems:
            sems = parse_semestres_permitidos(",".join(op['ciclos_permitidos']))
        opp_dict[op['id']] = Opportunity(
            id=op['id'],
            professor=op['professor'],
            local=op['local'],
            atividade=op['atividade'],
            periodo=op['periodo'],
            vagas_total=op['vagas_total'],
            ciclos_permitidos=op['ciclos_permitidos'],
            semestres_permitidos=sems,
            vagas_por_ciclo={},
            percentual_cotas=0.5,
            percentual_mulheres=0.0,
            dividir_por_ciclo=True,
        )
    return opp_dict


# =============================================================================
# 5. CARREGAMENTO E HIGIENIZAÇÃO DOS CANDIDATOS
# =============================================================================

def load_cotas_file(file_path: str) -> Dict[str, Dict[str, Any]]:
    """
    Carrega o arquivo de cotistas / forma de ingresso em Excel (.xlsx/.xls) ou CSV (.csv).
    Suporta dois formatos oficiais:
    1) Planilha Consolidada de Cotistas FAMED (.xlsx com colunas Matrícula e Nome):
       Todos os discentes presentes na lista são considerados Cotistas.
    2) Exportação SIGAA (.csv com coluna Forma de Ingresso):
       Identifica cotistas por palavras-chave na forma de ingresso.
    Indexa tanto pela matrícula limpa quanto pelo nome normalizado (sem acentos/espaços extras).
    """
    cotas_map: Dict[str, Dict[str, Any]] = {}
    if not file_path or not os.path.exists(file_path):
        print(f"[AVISO] Arquivo de cotas '{file_path}' não encontrado. Cotas serão inferidas como Não-Cotista.")
        return cotas_map

    PALAVRAS_COTA = [
        'COTA', 'GRUPO', 'PPI', 'RENDA', 'PCD', 'QUILOMBOLA', 'INDÍGENA', 'INDIGENA',
        'PSEI', 'PSEQ', 'ESCOLA PUBLICA', 'ESCOLA PÚBLICA',
        'L1', 'L2', 'L5', 'L6', 'L9', 'L10', 'L13', 'L14',
    ]

    ext = os.path.splitext(str(file_path).lower())[1]
    df = None
    if ext in ('.xlsx', '.xls'):
        df = pd.read_excel(file_path)
    else:
        for sep in [';', ',', '\t']:
            try:
                df = pd.read_csv(file_path, sep=sep, encoding='utf-8')
                if len(df.columns) > 1:
                    break
            except UnicodeDecodeError:
                df = pd.read_csv(file_path, sep=sep, encoding='latin1')
                if len(df.columns) > 1:
                    break

    if df is None or df.empty:
        return cotas_map

    # Normalizar nomes das colunas
    col_map: Dict[str, Any] = {}
    for col in df.columns:
        c_clean = remove_accents(str(col)).strip().lower()
        if 'matr' in c_clean:
            col_map['matricula'] = col
        elif 'nome' in c_clean:
            col_map['nome'] = col
        elif 'forma' in c_clean:
            col_map['forma_ingresso'] = col
        elif 'ano' in c_clean or 'periodo' in c_clean or 'ingresso' in c_clean:
            col_map['ano_periodo'] = col
        elif 'nasc' in c_clean:
            col_map['data_nascimento'] = col

    has_forma_col = 'forma_ingresso' in col_map

    for _, row in df.iterrows():
        raw_mat = row[col_map['matricula']] if 'matricula' in col_map else ''
        mat = clean_matricula(raw_mat)
        raw_nome = row[col_map['nome']] if 'nome' in col_map else ''
        nome = '' if pd.isna(raw_nome) else str(raw_nome).strip()
        if not mat and not nome:
            continue

        raw_ap = row[col_map['ano_periodo']] if 'ano_periodo' in col_map else ''
        ano_per = '' if pd.isna(raw_ap) else str(raw_ap).strip()
        data_nasc_raw = row[col_map['data_nascimento']] if 'data_nascimento' in col_map else None

        if has_forma_col:
            raw_forma = row[col_map['forma_ingresso']]
            forma = '' if pd.isna(raw_forma) else str(raw_forma).strip()
            is_cotista = any(kw in forma.upper() for kw in PALAVRAS_COTA)
        else:
            # Planilha consolidada exclusiva de cotistas (ex: Cotistas_FAMED_Consolidado.xlsx)
            forma = 'Cotista (Lista Consolidada FAMED)'
            is_cotista = True

        record = {
            'matricula': mat,
            'nome': nome,
            'ano_periodo': ano_per,
            'forma_ingresso': forma,
            'is_cotista': is_cotista,
            'data_nascimento_raw': data_nasc_raw,
        }
        if mat:
            cotas_map[mat] = record
        nome_norm = normalize_name(nome)
        if nome_norm:
            cotas_map[nome_norm] = record
        if nome:
            cotas_map[nome.lower()] = record

    return cotas_map

def load_cotas_csv(csv_path: str) -> Dict[str, Dict[str, Any]]:
    """Compatibilidade retroativa: delega para load_cotas_file (suporta .xlsx, .xls e .csv)."""
    return load_cotas_file(csv_path)

def load_students(excel_path: str, cotas_csv_path: Optional[str] = None, ref_year: int = 2026) -> List[Student]:
    """
    Lê o formulário de inscrições dos alunos, limpa e padroniza dados,
    ignora linhas em branco, elimina envios duplicados mantendo o mais recente
    e enriquece com dados de cotas e ciclo.
    """
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Arquivo de alunos não encontrado: {excel_path}")

    df = pd.read_excel(excel_path)
    
    # Mapear colunas do formulário
    col_timestamp = None
    col_nome = None
    col_mat = None
    col_email = None
    col_tel = None
    col_op1 = None
    col_op2 = None
    col_crg = None

    for col in df.columns:
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

    # Ordenar por timestamp antes da desduplicação
    if col_timestamp:
        df[col_timestamp] = pd.to_datetime(df[col_timestamp], errors='coerce')
        df = df.sort_values(col_timestamp)

    # Descartar linhas fantasma sem nome nem matrícula
    df['mat_clean_temp'] = df[col_mat].apply(clean_matricula) if col_mat else ''
    df['nome_norm_temp'] = df[col_nome].apply(normalize_name) if col_nome else ''
    df = df[(df['mat_clean_temp'] != '') | (df['nome_norm_temp'] != '')].copy()

    if col_mat:
        mask_mat = df['mat_clean_temp'] != ''
        df_com_mat = df[mask_mat].drop_duplicates(subset=['mat_clean_temp'], keep='last')
        df_sem_mat = df[~mask_mat]
        df = pd.concat([df_com_mat, df_sem_mat]).sort_values(col_timestamp) if col_timestamp else pd.concat([df_com_mat, df_sem_mat])
    if col_nome:
        mask_nome = df['nome_norm_temp'] != ''
        df_com_nome = df[mask_nome].drop_duplicates(subset=['nome_norm_temp'], keep='last')
        df_sem_nome = df[~mask_nome]
        df = pd.concat([df_com_nome, df_sem_nome]).sort_values(col_timestamp) if col_timestamp else pd.concat([df_com_nome, df_sem_nome])

    cotas_map = load_cotas_file(cotas_csv_path) if cotas_csv_path else {}

    students = []
    for _, row in df.iterrows():
        raw_mat = row[col_mat] if col_mat else ''
        mat = clean_matricula(raw_mat)
        raw_nome = row[col_nome] if col_nome else ''
        nome = '' if pd.isna(raw_nome) else " ".join(str(raw_nome).split())
        raw_email = row[col_email] if col_email else ''
        email = '' if pd.isna(raw_email) else str(raw_email).strip().lower()
        tel = clean_phone(row[col_tel]) if col_tel else ''
        crg = clean_crg(row[col_crg]) if col_crg else 0.0
        
        op1_raw = row[col_op1] if col_op1 else None
        op2_raw = row[col_op2] if col_op2 else None
        op1 = parse_option_id(op1_raw) or '1'
        op2_list = parse_option_list(op2_raw)
        
        ts = row[col_timestamp] if col_timestamp else datetime.datetime.now()
        if pd.isna(ts):
            ts = datetime.datetime.now()

        # Obter dados de ingresso / cotas
        nome_norm = normalize_name(nome)
        cotas_info = cotas_map.get(mat) or cotas_map.get(nome_norm) or cotas_map.get(nome.lower(), {})
        is_cotista = cotas_info.get('is_cotista', False)
        forma_ingresso = cotas_info.get('forma_ingresso', 'Ampla Concorrência')

        # Determinar ano de ingresso (recupera da lista oficial se houver erro de digitação)
        ano_ingresso = ref_year
        mat_ref = mat
        cotista_mat = cotas_info.get('matricula', '')
        if (not mat or len(mat) != 12 or not (mat[:4].isdigit() and 1990 <= int(mat[:4]) <= ref_year)) and cotista_mat and len(cotista_mat) >= 4:
            mat_ref = cotista_mat
        if mat_ref and len(mat_ref) >= 4 and mat_ref[:4].isdigit():
            y = int(mat_ref[:4])
            if 1990 <= y <= ref_year:
                ano_ingresso = y
        elif 'ano_periodo' in cotas_info and cotas_info['ano_periodo']:
            ap_match = re.search(r'(\d{4})', str(cotas_info['ano_periodo']))
            if ap_match:
                ano_ingresso = int(ap_match.group(1))

        semestre_estimado = max(1, min(12, (ref_year - ano_ingresso) * 2 + 1))
        ciclo = determine_cycle(semestre_estimado)

        # Idade / data de nascimento
        data_nasc_raw = cotas_info.get('data_nascimento_raw', None)
        data_nascimento = parse_birth_date(data_nasc_raw, ano_ingresso)

        # Predição de Gênero
        genero = guess_gender(nome)

        student = Student(
            matricula=mat,
            nome=nome,
            email=email,
            telefone=tel,
            crg=crg,
            op1=op1,
            op2_list=op2_list,
            timestamp=ts,
            genero=genero,
            is_cotista=is_cotista,
            forma_ingresso=forma_ingresso,
            ano_ingresso=ano_ingresso,
            semestre_atual=semestre_estimado,
            ciclo=ciclo,
            data_nascimento=data_nascimento,
        )
        students.append(student)

    return students


# =============================================================================
# 6. O CORAÇÃO DO SISTEMA: MOTOR DE CLASSIFICAÇÃO EM CAMADAS
# =============================================================================

def sort_candidates(candidates: List[Student]) -> List[Student]:
    """
    Passo B: Ordenação Base (Critérios de Desempate)
    1. CRG (decrescente)
    2. Idade (decrescente -> data de nascimento menor/mais antiga)
    3. Timestamp de inscrição (mais antigo primeiro)
    """
    return sorted(
        candidates,
        key=lambda s: (
            -s.crg,
            s.data_nascimento,  # data menor = aluno mais velho
            s.timestamp
        )
    )

def _allocate_pool_standard(
    opp: Opportunity,
    eligible_candidates: List[Student],
    vagas_disponiveis: int,
    rodada_nome: str,
    sufixo_modalidade: str = ""
) -> Tuple[List[Student], List[Student], List[str]]:
    """
    Passo C: Aplicação das Cotas e Gênero (Regra da Ampla Primeiro)
    Preenche as vagas disponíveis para a oportunidade seguindo:
    1. Divisão entre AC e Cotas (ex: 50% / 50% ou 1 AC se vaga única).
    2. Preenchimento da Ampla Concorrência (AC) com os melhores gerais.
    3. Verificação de 50% de Mulheres na AC (com permuta do menor homem pela maior mulher).
    4. Preenchimento das Cotas com cotistas restantes.
    5. Verificação de 50% de Mulheres nas Cotas (com permuta se necessário).
    6. Reversão de sobras de Cotas para a Ampla Concorrência.
    """
    logs = []
    logs.append(f"--- Iniciando Alocação de Sub-pool: Opção {opp.id} ({opp.professor}) | Vagas: {vagas_disponiveis} | {rodada_nome} ---")
    logs.append(f"Candidatos inscritos no pool: {len(eligible_candidates)}")

    if vagas_disponiveis <= 0 or not eligible_candidates:
        logs.append("Nenhuma vaga a preencher ou nenhum candidato elegível no pool.")
        return [], eligible_candidates, logs

    # Ordenação preliminar de todos os candidatos
    pool = sort_candidates(eligible_candidates)

    # 1. Definir quantidade de vagas de AC e Cotas
    # Regra: As vagas serão distribuídas igualmente entre cotistas e não cotistas.
    # Quando o número de vagas for ímpar, a vaga excedente será destinada aos cotistas (math.ceil).
    if opp.percentual_cotas > 0:
        vagas_cotas = math.ceil(vagas_disponiveis * opp.percentual_cotas)
    else:
        vagas_cotas = 0
    vagas_ac = max(0, vagas_disponiveis - vagas_cotas)

    logs.append(f"Divisão de vagas do pool: AC = {vagas_ac}, Cotas = {vagas_cotas}")

    # -------------------------------------------------------------
    # ETAPA 1: Preenchimento da Ampla Concorrência (AC)
    # -------------------------------------------------------------
    ac_selecionados: List[Student] = pool[:vagas_ac]
    pool_restante = pool[vagas_ac:]

    # Se houver menos candidatos que vagas na ampla, as vagas excedentes revertem para cotas
    if len(ac_selecionados) < vagas_ac:
        vagas_sobrando_ac = vagas_ac - len(ac_selecionados)
        vagas_cotas += vagas_sobrando_ac
        logs.append(f"[Reversão AC -> Cotas] {vagas_sobrando_ac} vaga(s) da ampla revertida(s) para cotas por falta de candidatos.")

    logs.append(f"[AC] Seleção preliminar por maior nota: {[f'{s.nome} ({s.genero}, CRG={s.crg:.4f})' for s in ac_selecionados]}")

    # ETAPA 2: Verificação dos 50% de Mulheres na AC (apenas se critério de gênero estiver ativado)
    if opp.percentual_mulheres > 0.0 and ac_selecionados:
        mulheres_alvo_ac = math.ceil(len(ac_selecionados) * opp.percentual_mulheres)
        mulheres_atuais_ac = sum(1 for s in ac_selecionados if s.genero == 'F')
        logs.append(f"[AC Gênero] Mulheres presentes: {mulheres_atuais_ac}/{len(ac_selecionados)} (Meta mínima: {mulheres_alvo_ac})")

        while mulheres_atuais_ac < mulheres_alvo_ac:
            # Encontrar o homem com menor CRG dentro da AC
            homens_ac = [s for s in ac_selecionados if s.genero == 'M']
            if not homens_ac:
                break
            menor_homem = homens_ac[-1]

            # Encontrar a mulher com maior CRG fora da AC
            mulheres_fora = [s for s in pool_restante if s.genero == 'F']
            if not mulheres_fora:
                logs.append("[AC Gênero] Não há candidatas mulheres restantes para substituição na cota de 50%.")
                break
            maior_mulher = mulheres_fora[0]

            # Efetuar a troca
            ac_selecionados.remove(menor_homem)
            pool_restante.append(menor_homem)
            pool_restante = sort_candidates(pool_restante)

            pool_restante.remove(maior_mulher)
            ac_selecionados.append(maior_mulher)
            ac_selecionados = sort_candidates(ac_selecionados)

            mulheres_atuais_ac += 1
            msg_swap = (f"[AC Gênero - Ação Afirmativa] Troca realizada: Aluna {maior_mulher.nome} (CRG {maior_mulher.crg:.4f}) "
                        f"substituiu o aluno {menor_homem.nome} (CRG {menor_homem.crg:.4f}) para cumprir os 50% de mulheres na AC.")
            logs.append(msg_swap)
            maior_mulher.historico_auditoria.append(msg_swap)
    else:
        logs.append("[Gênero AC] Ação afirmativa de gênero desativada ou não aplicável.")

    # -------------------------------------------------------------
    # ETAPA 3: Preenchimento das Vagas de Cotas
    # -------------------------------------------------------------
    cotas_selecionados: List[Student] = []
    vagas_cotas_restantes = vagas_cotas

    if vagas_cotas > 0:
        # Filtrar cotistas no pool restante
        pool_cotistas = [s for s in pool_restante if s.is_cotista]
        logs.append(f"[Cotas] Cotistas concorrendo às vagas reservadas: {len(pool_cotistas)}")

        if pool_cotistas:
            qtd_preencher = min(len(pool_cotistas), vagas_cotas)
            cotas_selecionados = pool_cotistas[:qtd_preencher]
            for s in cotas_selecionados:
                pool_restante.remove(s)
            vagas_cotas_restantes = vagas_cotas - len(cotas_selecionados)
            logs.append(f"[Cotas] Seleção preliminar de cotistas: {[f'{s.nome} ({s.genero}, CRG={s.crg:.4f})' for s in cotas_selecionados]}")

            # ETAPA 4: Verificação dos 50% de Mulheres nas Cotas (apenas se critério de gênero estiver ativado)
            if opp.percentual_mulheres > 0.0 and cotas_selecionados:
                mulheres_alvo_cotas = math.ceil(len(cotas_selecionados) * opp.percentual_mulheres)
                mulheres_atuais_cotas = sum(1 for s in cotas_selecionados if s.genero == 'F')
                logs.append(f"[Cotas Gênero] Mulheres cotistas presentes: {mulheres_atuais_cotas}/{len(cotas_selecionados)} (Meta mínima: {mulheres_alvo_cotas})")

                while mulheres_atuais_cotas < mulheres_alvo_cotas:
                    homens_cotas = [s for s in cotas_selecionados if s.genero == 'M']
                    if not homens_cotas:
                        break
                    menor_homem_cota = homens_cotas[-1]

                    mulheres_cotistas_fora = [s for s in pool_restante if s.is_cotista and s.genero == 'F']
                    if not mulheres_cotistas_fora:
                        logs.append("[Cotas Gênero] Não há mais mulheres cotistas fora da lista para permuta de gênero.")
                        break
                    maior_mulher_cota = mulheres_cotistas_fora[0]

                    cotas_selecionados.remove(menor_homem_cota)
                    pool_restante.append(menor_homem_cota)
                    pool_restante = sort_candidates(pool_restante)

                    pool_restante.remove(maior_mulher_cota)
                    cotas_selecionados.append(maior_mulher_cota)
                    cotas_selecionados = sort_candidates(cotas_selecionados)

                    mulheres_atuais_cotas += 1
                    msg_cota_swap = (f"[Cotas Gênero - Ação Afirmativa] Troca nas cotas: Aluna {maior_mulher_cota.nome} (CRG {maior_mulher_cota.crg:.4f}) "
                                     f"substituiu {menor_homem_cota.nome} (CRG {menor_homem_cota.crg:.4f}) na vaga reservada de cotas.")
                    logs.append(msg_cota_swap)
                    maior_mulher_cota.historico_auditoria.append(msg_cota_swap)
            else:
                logs.append("[Gênero Cotas] Ação afirmativa de gênero desativada ou não aplicável.")

        # ETAPA 5: Reversão de sobras de Cotas para a Ampla Concorrência
        if vagas_cotas_restantes > 0:
            logs.append(f"[Reversão de Cotas] {vagas_cotas_restantes} vaga(s) de cota revertida(s) para Ampla Concorrência por falta de cotistas.")
            vagas_revertidas = min(vagas_cotas_restantes, len(pool_restante))
            if vagas_revertidas > 0:
                revertidos = pool_restante[:vagas_revertidas]
                for s in revertidos:
                    pool_restante.remove(s)
                    ac_selecionados.append(s)
                    msg_rev = f"Aprovado em vaga de cota revertida para ampla concorrência (CRG {s.crg:.4f})."
                    s.historico_auditoria.append(msg_rev)
                    logs.append(f"  -> Candidato remanejado da ampla para vaga revertida: {s.nome} (CRG {s.crg:.4f})")

    # Atribuir modalidades e status aos selecionados
    for s in ac_selecionados:
        s.alocado = True
        s.alocado_em = opp.id
        s.modalidade = f'Ampla Concorrência{sufixo_modalidade}'
        if not s.motivo_alocacao:
            s.motivo_alocacao = f"Classificado na Ampla Concorrência{sufixo_modalidade} ({rodada_nome}) - CRG: {s.crg:.4f}"

    for s in cotas_selecionados:
        s.alocado = True
        s.alocado_em = opp.id
        s.modalidade = f'Cota Reservada{sufixo_modalidade}'
        if not s.motivo_alocacao:
            s.motivo_alocacao = f"Classificado na Vaga Reservada de Cota{sufixo_modalidade} ({rodada_nome}) - CRG: {s.crg:.4f}"

    todos_selecionados = ac_selecionados + cotas_selecionados
    lista_espera = pool_restante

    logs.append(f"Total de aprovados no pool {rodada_nome}: {len(todos_selecionados)}/{vagas_disponiveis}")
    return todos_selecionados, lista_espera, logs

def allocate_opportunity(
    opp: Opportunity,
    eligible_candidates: List[Student],
    vagas_disponiveis: int,
    rodada_nome: str = "1ª Opção"
) -> Tuple[List[Student], List[Student], List[str]]:
    """
    Orquestra a alocação de vagas da oportunidade considerando:
    1. Divisão equitativa por ciclo de formação (se habilitado e se a vaga abranger múltiplos ciclos).
       Vagas ímpares são atribuídas ao ciclo mais avançado (Internato > Clínico > Básico).
       Transbordo de vagas não preenchidas para os demais ciclos.
    2. Caso desabilitado ou se houver apenas 1 ciclo, aloca diretamente por CRG e cotas.
    """
    logs = []
    logs.append(f"--- Iniciando Alocação: Opção {opp.id} ({opp.professor}) | Vagas: {vagas_disponiveis} | {rodada_nome} ---")
    logs.append(f"Candidatos elegíveis inscritos: {len(eligible_candidates)}")

    if vagas_disponiveis <= 0 or not eligible_candidates:
        logs.append("Nenhuma vaga a preencher ou nenhum candidato elegível.")
        return [], eligible_candidates, logs

    # Se a divisão por ciclo estiver desativada, aloca pelo método padrão diretamente
    if not opp.dividir_por_ciclo:
        logs.append("[Divisão por Ciclo Desativada] Concorrência ampla entre todos os semestres elegíveis por CRG.")
        sel, esp, l = _allocate_pool_standard(opp, eligible_candidates, vagas_disponiveis, rodada_nome)
        logs.extend(l)
        return sel, esp, logs

    # Identificar quais ciclos estão autorizados nesta oportunidade
    if opp.semestres_permitidos:
        cycles_opp = {determine_cycle(s) for s in opp.semestres_permitidos}
    else:
        cycles_opp = {str(c).lower().strip() for c in opp.ciclos_permitidos if c}

    active_cycles = [c for c in CYCLE_HIERARCHY if c in cycles_opp]

    # Se houver apenas 1 ciclo (ou nenhum mapeado), não há divisão entre múltiplos ciclos
    if len(active_cycles) <= 1:
        if active_cycles:
            logs.append(f"[Ciclo Único: {active_cycles[0].capitalize()}] Oportunidade destinada a apenas 1 ciclo. Alocação direta.")
        sel, esp, l = _allocate_pool_standard(opp, eligible_candidates, vagas_disponiveis, rodada_nome)
        logs.extend(l)
        return sel, esp, logs

    # Divisão de vagas entre múltiplos ciclos com prioridade da vaga ímpar para o mais avançado
    k = len(active_cycles)
    base = vagas_disponiveis // k
    rem = vagas_disponiveis % k
    vagas_part = {c: base for c in active_cycles}
    for i in range(rem):
        most_advanced_cycle = active_cycles[-(i + 1)]
        vagas_part[most_advanced_cycle] += 1

    dist_str = ", ".join(f"{c.capitalize()}: {vagas_part[c]} vaga(s)" for c in active_cycles)
    logs.append(f"[Divisão por Ciclo Ativada] {vagas_disponiveis} vaga(s) distribuída(s): {dist_str} (vaga ímpar atribuída ao ciclo mais avançado).")

    all_selecionados: List[Student] = []
    total_sobras = 0

    # Alocação preliminar de cada ciclo
    for c in active_cycles:
        cands_c = [s for s in eligible_candidates if str(s.ciclo).lower().strip() == c and not s.alocado]
        v_c = vagas_part[c]
        if v_c > 0 and cands_c:
            sel_c, _, logs_c = _allocate_pool_standard(
                opp=opp,
                eligible_candidates=cands_c,
                vagas_disponiveis=v_c,
                rodada_nome=f"{rodada_nome} - {c.capitalize()}",
                sufixo_modalidade=f" - {c.capitalize()}"
            )
            all_selecionados.extend(sel_c)
            logs.extend(logs_c)
            if len(sel_c) < v_c:
                sobras_c = v_c - len(sel_c)
                total_sobras += sobras_c
                logs.append(f"[Ciclo {c.capitalize()}] Sobraram {sobras_c} vaga(s) não preenchida(s) por falta de candidatos.")
        elif v_c > 0 and not cands_c:
            logs.append(f"[Ciclo {c.capitalize()}] Nenhum candidato elegível inscrito para as {v_c} vaga(s) reservadas do ciclo.")
            total_sobras += v_c

    # Transbordo (Spillover): Se sobraram vagas não preenchidas em algum ciclo, transfere para os demais
    if total_sobras > 0:
        pool_sobras = [s for s in eligible_candidates if s not in all_selecionados and not s.alocado]
        if pool_sobras:
            logs.append(f"[Transbordo entre Ciclos] {total_sobras} vaga(s) remanescente(s) redistribuída(s) para os demais ciclos.")
            # Ordena com prioridade para ciclo mais avançado, depois CRG decrescente e maior idade
            pool_sobras = sorted(
                pool_sobras,
                key=lambda s: (
                    CYCLE_HIERARCHY.index(str(s.ciclo).lower().strip()) if str(s.ciclo).lower().strip() in CYCLE_HIERARCHY else 0,
                    s.crg,
                    s.data_nascimento
                ),
                reverse=True
            )
            sel_sob, _, logs_sob = _allocate_pool_standard(
                opp=opp,
                eligible_candidates=pool_sobras,
                vagas_disponiveis=total_sobras,
                rodada_nome=f"{rodada_nome} - Transbordo",
                sufixo_modalidade=" - Transbordo"
            )
            all_selecionados.extend(sel_sob)
            logs.extend(logs_sob)

    lista_espera = [s for s in eligible_candidates if s not in all_selecionados]
    lista_espera = sort_candidates(lista_espera)
    logs.append(f"Total de aprovados na oportunidade {opp.id}: {len(all_selecionados)}/{vagas_disponiveis}")
    return all_selecionados, lista_espera, logs

def run_classification(
    opportunities: Dict[str, Opportunity],
    students: List[Student]
) -> Tuple[Dict[str, Opportunity], List[Student], List[str]]:
    """
    Passo D: Remanejamento de 1ª e 2ª Opção.
    Executa a classificação completa em duas rodadas:
    - Rodada 1: Alocação em 1ª Opção
    - Rodada 2: Alocação em 2ª Opção para vagas remanescentes
    """
    audit_trail = []
    audit_trail.append("================================================================================")
    audit_trail.append("RODADA 1: ALOCAÇÃO EM 1ª OPÇÃO")
    audit_trail.append("================================================================================")

    # -------------------------------------------------------------
    # RODADA 1: 1ª OPÇÃO
    # -------------------------------------------------------------
    for opp_id, opp in opportunities.items():
        # Filtra alunos que escolheram esta oportunidade como 1ª opção
        candidatos_op1 = [s for s in students if not s.alocado and s.op1 == opp_id]
        
        # Filtra por semestres permitidos (ou ciclo como fallback)
        if opp.semestres_permitidos:
            candidatos_elegiveis = [s for s in candidatos_op1 if s.semestre_atual in opp.semestres_permitidos]
            descartados = [s for s in candidatos_op1 if s.semestre_atual not in opp.semestres_permitidos]
            for d in descartados:
                msg_sem = (f"[Semestre Incompatível] Aluno(a) {d.nome} ({d.semestre_atual}º semestre) "
                           f"não atende aos requisitos da Opção {opp.id} (Semestres permitidos: {opp.semestres_permitidos}).")
                d.historico_auditoria.append(msg_sem)
                audit_trail.append(msg_sem)
        else:
            candidatos_elegiveis = [s for s in candidatos_op1 if s.ciclo in opp.ciclos_permitidos]
            descartados_ciclo = [s for s in candidatos_op1 if s.ciclo not in opp.ciclos_permitidos]
            for d in descartados_ciclo:
                msg_ciclo = (f"[Ciclo Incompatível] Aluno(a) {d.nome} (Semestre {d.semestre_atual}, Ciclo {d.ciclo}) "
                             f"não é elegível para a Opção {opp.id} (Ciclos permitidos: {opp.ciclos_permitidos}).")
                d.historico_auditoria.append(msg_ciclo)
                audit_trail.append(msg_ciclo)

        selecionados, espera, logs = allocate_opportunity(
            opp=opp,
            eligible_candidates=candidatos_elegiveis,
            vagas_disponiveis=opp.vagas_total,
            rodada_nome="1ª Opção"
        )
        opp.selecionados = selecionados
        opp.lista_espera = espera
        opp.logs.extend(logs)
        audit_trail.extend(logs)
        
        for s in selecionados:
            s.alocado_opcao = 1

    # -------------------------------------------------------------
    # RODADA 2: 2ª OPÇÃO (REMANEJAMENTO PARA VAGAS RESTANTES)
    # -------------------------------------------------------------
    audit_trail.append("\n================================================================================")
    audit_trail.append("RODADA 2: ALOCAÇÃO EM 2ª OPÇÃO (VAGAS REMANESCENTES)")
    audit_trail.append("================================================================================")

    for opp_id, opp in opportunities.items():
        vagas_restantes = opp.vagas_total - len(opp.selecionados)
        if vagas_restantes <= 0:
            continue

        audit_trail.append(f"\nOpção {opp_id} possui {vagas_restantes} vaga(s) remanescente(s). Buscando 2ª opção...")
        
        # Candidatos que não foram alocados na 1ª opção e colocaram esta oportunidade como 2ª opção
        candidatos_op2 = [
            s for s in students 
            if not s.alocado and (opp_id in s.op2_list)
        ]
        
        if opp.semestres_permitidos:
            candidatos_elegiveis = [s for s in candidatos_op2 if s.semestre_atual in opp.semestres_permitidos]
            descartados = [s for s in candidatos_op2 if s.semestre_atual not in opp.semestres_permitidos]
            for d in descartados:
                msg_sem = (f"[Semestre Incompatível na 2ª Opção] Aluno(a) {d.nome} ({d.semestre_atual}º semestre) "
                           f"não atende aos requisitos da Opção {opp.id}.")
                d.historico_auditoria.append(msg_sem)
        else:
            candidatos_elegiveis = [s for s in candidatos_op2 if s.ciclo in opp.ciclos_permitidos]
            descartados_ciclo = [s for s in candidatos_op2 if s.ciclo not in opp.ciclos_permitidos]
            for d in descartados_ciclo:
                msg_ciclo = (f"[Ciclo Incompatível na 2ª Opção] Aluno(a) {d.nome} (Ciclo {d.ciclo}) "
                             f"não elegível para Opção {opp.id}.")
                d.historico_auditoria.append(msg_ciclo)

        if candidatos_elegiveis:
            novos_selecionados, nova_espera, logs = allocate_opportunity(
                opp=opp,
                eligible_candidates=candidatos_elegiveis,
                vagas_disponiveis=vagas_restantes,
                rodada_nome="2ª Opção"
            )
            for s in novos_selecionados:
                s.alocado_opcao = 2
            opp.selecionados.extend(novos_selecionados)
            opp.lista_espera.extend(nova_espera)
            opp.logs.extend(logs)
            audit_trail.extend(logs)
        else:
            audit_trail.append(f"Nenhum candidato apto em 2ª opção para a Opção {opp_id}.")

    return opportunities, students, audit_trail


# =============================================================================
# 7. GERADOR DE OFÍCIO OFICIAL EM PDF (PADRÃO FAMED / GEP-HUJBB)
# =============================================================================

class NumberedCanvas(canvas.Canvas):
    """Adiciona numeração de página no formato 'Página X de Y'."""
    def __init__(self, *args, **kwargs):
        super(NumberedCanvas, self).__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            super(NumberedCanvas, self).showPage()
        super(NumberedCanvas, self).save()

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#4A5568"))
        page_text = f"Página {self._pageNumber} de {page_count}"
        self.drawRightString(200 * mm, 12 * mm, page_text)
        self.drawString(18 * mm, 12 * mm, "Faculdade de Medicina - FAMED/UFPA | Sistema de Estágio de Férias")
        self.restoreState()

def generate_pdf_report(
    opportunities: Dict[str, Opportunity],
    students: List[Student],
    output_pdf_path: str = "resultado_final.pdf",
    edital_titulo: str = "2026.1",
    oficio_numero: str = "414 / 2026",
    protocolo: str = "23073.092158/2026-14",
    data_emissao: Optional[str] = None
) -> None:
    """
    Gera o PDF oficial idêntico ao modelo institucional da FAMED / UFPA
    ('Oficio - Estagio de Ferias FAMED de Dez.2025 a FEV.2026 GEP_HUJBB .pdf').
    """
    if data_emissao is None:
        hoje = datetime.date.today()
        meses = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
                 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
        data_emissao = f"{hoje.day:02d} de {meses[hoje.month - 1]} de {hoje.year}"

    doc = SimpleDocTemplate(
        output_pdf_path,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=15 * mm,
        bottomMargin=20 * mm
    )

    styles = getSampleStyleSheet()

    # Estilos customizados
    style_header_gov = ParagraphStyle(
        'HeaderGov',
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        alignment=1,  # Centralizado
        textColor=colors.HexColor('#1A202C')
    )
    style_header_sub = ParagraphStyle(
        'HeaderSub',
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        alignment=1,
        textColor=colors.HexColor('#2D3748')
    )
    style_oficio_meta = ParagraphStyle(
        'OficioMeta',
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#2D3748')
    )
    style_body = ParagraphStyle(
        'BodyCustom',
        fontName='Helvetica',
        fontSize=9.5,
        leading=14.5,
        alignment=4,  # Justificado
        textColor=colors.HexColor('#2D3748')
    )
    style_body_bold = ParagraphStyle(
        'BodyCustomBold',
        parent=style_body,
        fontName='Helvetica-Bold'
    )
    style_opp_title = ParagraphStyle(
        'OppTitle',
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor('#1A365D')
    )
    style_opp_info = ParagraphStyle(
        'OppInfo',
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor('#2D3748')
    )
    style_table_header = ParagraphStyle(
        'TableHeader',
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=10,
        textColor=colors.white
    )
    style_table_cell = ParagraphStyle(
        'TableCell',
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#1A202C')
    )
    style_signature = ParagraphStyle(
        'SigStyle',
        fontName='Helvetica',
        fontSize=8.5,
        leading=11.5,
        alignment=0,
        textColor=colors.HexColor('#2D3748')
    )

    story = []

    # =========================================================================
    # PÁGINA 1: OFÍCIO INSTITUCIONAL
    # =========================================================================
    # Brasão da República / UFPA
    brasao_candidates = ["Brasao-UFPA-colorido.png", "estagios/static/img/Brasao-UFPA-colorido.png", "ufpa_brasao.png"]
    brasao_path = next((p for p in brasao_candidates if os.path.exists(p)), None)
    if brasao_path:
        story.append(Image(brasao_path, width=1.5 * cm, height=2.1 * cm))
        story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("MINISTÉRIO DA EDUCAÇÃO", style_header_gov))
    story.append(Paragraph("UNIVERSIDADE FEDERAL DO PARÁ", style_header_gov))
    story.append(Paragraph("FACULDADE DE MEDICINA - FAMED/ICM", style_header_sub))
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph(f"<b>OFÍCIO Nº {oficio_numero} - FAMED/ICM (11.85.04)</b>", style_oficio_meta))
    story.append(Paragraph(f"Nº do Protocolo: {protocolo}", style_oficio_meta))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(f"Belém-PA, {data_emissao}.", style_oficio_meta))
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph("<b>À Gerência de Ensino e Pesquisa do HUJBB (GEP/HUJBB)</b>", style_body_bold))
    story.append(Paragraph("<b>Assunto: Estágio de férias da FAMED-UFPA</b>", style_body_bold))
    story.append(Spacer(1, 6 * mm))

    # Professores participantes únicos com alunos alocados
    profs_ativos = sorted(list(set(
        opp.professor for opp in opportunities.values() if len(opp.selecionados) > 0
    )))
    profs_str = ", ".join(profs_ativos)

    p1 = ("Prezados(as), encaminho a listagem em anexo com os nomes dos nossos alunos que foram "
          "selecionados para o estágio de férias com nossos professores que atuam no Hospital Universitário "
          "João de Barros Barreto (HUJBB) e unidades conveniadas.")
    story.append(Paragraph(p1, style_body))
    story.append(Spacer(1, 4 * mm))

    p2 = (f"Desta vez, os professores que demonstraram interesse e ofertaram vagas para os alunos foram: "
          f"<b>{profs_str}</b>.")
    story.append(Paragraph(p2, style_body))
    story.append(Spacer(1, 4 * mm))

    p3 = ("Os detalhes de horários, locais, períodos e contatos encontram-se no anexo a este documento. "
          "Orientamos os estudantes selecionados a se dirigirem à GEP-HUJBB para as providências administrativas "
          "necessárias ao início tempestivo das atividades práticas.")
    story.append(Paragraph(p3, style_body))
    story.append(Spacer(1, 10 * mm))

    story.append(Paragraph("Atenciosamente,", style_body))
    story.append(Spacer(1, 12 * mm))

    story.append(Paragraph("<b>(Assinado digitalmente)</b>", style_signature))
    story.append(Paragraph("<b>DIREÇÃO DA FACULDADE DE MEDICINA</b>", style_signature))
    story.append(Paragraph("PROFESSOR DO MAGISTÉRIO SUPERIOR", style_signature))
    story.append(Paragraph("FAMED / ICM - UFPA", style_signature))
    story.append(Paragraph("Matrícula SIAPE: ###720#2", style_signature))
    story.append(Spacer(1, 6 * mm))

    # Rodapé institucional de autenticação digital SIPAC
    auth_box = [
        [Paragraph(f"Visualize o documento original autenticado informando seu número: <b>{oficio_numero.split('/')[0].strip()}</b>, "
                   f"ano: <b>{oficio_numero.split('/')[-1].strip()}</b>, tipo: <b>OFÍCIO</b> e data de emissão: <b>{data_emissao}</b> "
                   f"no portal SIPAC-UFPA.", style_opp_info)]
    ]
    t_auth = Table(auth_box, colWidths=[174 * mm])
    t_auth.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F7FAFC')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E0')),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(t_auth)

    # =========================================================================
    # PÁGINA 2+: ANEXO COM LISTAGEM DOS SELECIONADOS POR OPORTUNIDADE
    # =========================================================================
    story.append(PageBreak())

    titulo_anexo = Paragraph(f"<b>Alunos Selecionados para Estágio de Férias da FAMED {edital_titulo}</b>", ParagraphStyle(
        'AnexoHeader',
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        alignment=1,
        textColor=colors.HexColor('#1A365D')
    ))
    story.append(titulo_anexo)
    story.append(Spacer(1, 6 * mm))

    item_num = 1
    for opp_id in sorted(opportunities.keys(), key=lambda x: float(x) if x.replace('.', '').isdigit() else 999):
        opp = opportunities[opp_id]
        if not opp.selecionados:
            continue

        opp_story = []
        
        # Título do item da oportunidade
        titulo_item = f"<b>{item_num}) Seguem abaixo os selecionados para {opp.local}</b>"
        opp_story.append(Paragraph(titulo_item, style_opp_title))
        opp_story.append(Spacer(1, 2.5 * mm))

        # Tabela com Alunos Selecionados
        table_data = [
            [
                Paragraph("<b>Nome</b>", style_table_header),
                Paragraph("<b>E-mail</b>", style_table_header),
                Paragraph("<b>Contato</b>", style_table_header),
            ]
        ]

        for s in opp.selecionados:
            table_data.append([
                Paragraph(s.nome, style_table_cell),
                Paragraph(s.email, style_table_cell),
                Paragraph(s.telefone, style_table_cell),
            ])

        t_alunos = Table(table_data, colWidths=[65 * mm, 65 * mm, 44 * mm])
        t_alunos.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1A365D')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]))
        opp_story.append(t_alunos)
        opp_story.append(Spacer(1, 3 * mm))

        # Bloco de Orientações aos Estudantes
        orientacoes_texto = (
            f"Os alunos selecionados deverão entrar em contato direto com o(a) docente responsável a partir da publicação "
            f"deste ofício para alinhamento e orientações. Devem apresentar-se a(o) <b>{opp.professor}</b> para o início das atividades.<br/>"
            f"<b>Local:</b> {opp.local}<br/>"
            f"<b>Período/Carga Horária:</b> {opp.periodo}"
        )
        opp_story.append(Paragraph(orientacoes_texto, style_opp_info))
        opp_story.append(Spacer(1, 6 * mm))

        story.append(KeepTogether(opp_story))
        item_num += 1

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"[OK] Ofício oficial em PDF gerado com sucesso: '{output_pdf_path}'")


# =============================================================================
# 8. EXPORTADOR DE AUDITORIA E RELATÓRIO EXCEL
# =============================================================================

def export_excel_audit(
    opportunities: Dict[str, Opportunity],
    students: List[Student],
    audit_trail: List[str],
    output_excel_path: str = "resultado_detalhado.xlsx"
) -> None:
    """Gera planilha Excel rica com todas as listas, cotas, auditorias e classificação detalhada."""
    with pd.ExcelWriter(output_excel_path, engine='openpyxl') as writer:
        # Aba 1: Aprovados Finais
        rows_aprovados = []
        for opp_id, opp in opportunities.items():
            for idx, s in enumerate(opp.selecionados, 1):
                rows_aprovados.append({
                    'Opção': opp.id,
                    'Docente': opp.professor,
                    'Local': opp.local,
                    'Posição': idx,
                    'Matrícula': s.matricula,
                    'Nome': s.nome,
                    'E-mail': s.email,
                    'Telefone': s.telefone,
                    'CRG': s.crg,
                    'Gênero': 'Feminino' if s.genero == 'F' else 'Masculino',
                    'Cotista': 'Sim' if s.is_cotista else 'Não',
                    'Forma de Ingresso': s.forma_ingresso,
                    'Ciclo': s.ciclo.upper(),
                    'Opção Usada': f"{s.alocado_opcao}ª Opção",
                    'Modalidade': s.modalidade,
                    'Motivo Alocação': s.motivo_alocacao
                })
        pd.DataFrame(rows_aprovados).to_excel(writer, sheet_name='Alunos_Aprovados', index=False)

        # Aba 2: Ranking Geral Completo de Inscritos
        rows_geral = []
        for s in sort_candidates(students):
            rows_geral.append({
                'Matrícula': s.matricula,
                'Nome': s.nome,
                'CRG': s.crg,
                'Gênero': 'F' if s.genero == 'F' else 'M',
                'Cotista': 'Sim' if s.is_cotista else 'Não',
                'Forma de Ingresso': s.forma_ingresso,
                'Ano Ingresso': s.ano_ingresso,
                'Semestre': s.semestre_atual,
                'Ciclo': s.ciclo.upper(),
                '1ª Opção': s.op1,
                '2ª Opção': ", ".join(s.op2_list),
                'Status': 'Aprovado' if s.alocado else 'Lista de Espera',
                'Opção Alocada': s.alocado_em if s.alocado else '-',
                'Modalidade': s.modalidade if s.alocado else '-',
                'Opção Atendida': f"{s.alocado_opcao}ª Opção" if s.alocado else '-',
                'Auditoria': " | ".join(s.historico_auditoria)
            })
        pd.DataFrame(rows_geral).to_excel(writer, sheet_name='Classificacao_Geral', index=False)

        # Aba 3: Resumo das Oportunidades
        rows_opp = []
        for opp_id, opp in opportunities.items():
            qtd_aprovados = len(opp.selecionados)
            mulheres = sum(1 for s in opp.selecionados if s.genero == 'F')
            cotistas = sum(1 for s in opp.selecionados if s.is_cotista)
            rows_opp.append({
                'Opção': opp.id,
                'Docente': opp.professor,
                'Local': opp.local,
                'Vagas Totais': opp.vagas_total,
                'Vagas Preenchidas': qtd_aprovados,
                'Vagas Ociosas': max(0, opp.vagas_total - qtd_aprovados),
                'Total Mulheres': mulheres,
                'Percentual Mulheres (%)': round((mulheres / qtd_aprovados * 100), 1) if qtd_aprovados > 0 else 0.0,
                'Total Cotistas': cotistas,
                'Percentual Cotistas (%)': round((cotistas / qtd_aprovados * 100), 1) if qtd_aprovados > 0 else 0.0,
                'Ciclos Aceitos': ", ".join(opp.ciclos_permitidos)
            })
        pd.DataFrame(rows_opp).to_excel(writer, sheet_name='Resumo_Oportunidades', index=False)

        # Aba 4: Trilha de Auditoria (Logs Imutáveis)
        pd.DataFrame({'Registro de Decisão': audit_trail}).to_excel(writer, sheet_name='Trilha_Auditoria', index=False)

    print(f"[OK] Relatório detalhado de auditoria gerado em Excel: '{output_excel_path}'")


# =============================================================================
# 9. EXECUÇÃO PRINCIPAL (CLI)
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Classificador de Estágios de Férias FAMED/UFPA")
    parser.add_argument('--vagas', type=str, default="vagas_professores.xlsx",
                        help="Planilha Excel de vagas ofertadas pelos docentes")
    parser.add_argument('--alunos', type=str, default="inscricoes_alunos.xlsx",
                        help="Planilha Excel de inscrições dos estudantes")
    parser.add_argument('--csv-ingresso', type=str, default="forma_ingresso.csv",
                        help="Arquivo CSV com dados de forma de ingresso e cotas dos estudantes")
    parser.add_argument('--pdf', type=str, default="resultado_final.pdf",
                        help="Caminho do Ofício em PDF a ser gerado")
    parser.add_argument('--excel', type=str, default="resultado_detalhado.xlsx",
                        help="Caminho do relatório de auditoria em Excel a ser gerado")
    parser.add_argument('--edital', type=str, default="2026.1",
                        help="Identificação do edital/período")
    args = parser.parse_args()

    # Fallback automático para nomes originais do projeto se o nome padrão não existir
    vagas_path = args.vagas
    if not os.path.exists(vagas_path):
        alt_vagas = "Estágio de Férias FAMED 2026.3 - Triagem de Oportunidades (respostas).xlsx"
        if os.path.exists(alt_vagas):
            vagas_path = alt_vagas

    alunos_path = args.alunos
    if not os.path.exists(alunos_path):
        alt_alunos = "Estágio de Férias FAMED JULHO 2026 - Candidatura 15.05.26 - 20.05.26 (respostas).xlsx"
        if os.path.exists(alt_alunos):
            alunos_path = alt_alunos

    csv_path = args.csv_ingresso

    print("=" * 80)
    print(" SISTEMA DE CLASSIFICAÇÃO DE ESTÁGIO DE FÉRIAS - FAMED / UFPA")
    print("=" * 80)
    print(f"Planilha de Vagas:       {vagas_path}")
    print(f"Planilha de Alunos:      {alunos_path}")
    print(f"CSV de Forma de Ingresso:{csv_path}")
    print(f"Saída PDF:               {args.pdf}")
    print(f"Saída Excel:             {args.excel}")
    print("-" * 80)

    # 1. Carregar Oportunidades
    opps = load_opportunities(vagas_path)
    total_vagas = sum(o.vagas_total for o in opps.values())
    print(f"[CARGA] {len(opps)} oportunidades registradas, totalizando {total_vagas} vagas ofertadas.")

    # 2. Carregar e Higienizar Candidatos
    students = load_students(alunos_path, csv_path)
    print(f"[CARGA] {len(students)} estudantes únicos processados após deduplicação e limpeza.")

    # Estatísticas de candidatos
    cotistas_count = sum(1 for s in students if s.is_cotista)
    mulheres_count = sum(1 for s in students if s.genero == 'F')
    print(f"        -> Cotistas: {cotistas_count} ({cotistas_count/len(students)*100:.1f}%) | "
          f"Não-cotistas: {len(students)-cotistas_count}")
    print(f"        -> Mulheres: {mulheres_count} ({mulheres_count/len(students)*100:.1f}%) | "
          f"Homens: {len(students)-mulheres_count}")

    # 3. Rodar Motor de Classificação
    opps, students, audit = run_classification(opps, students)

    total_alocados = sum(len(o.selecionados) for o in opps.values())
    alocados_op1 = sum(1 for s in students if s.alocado_opcao == 1)
    alocados_op2 = sum(1 for s in students if s.alocado_opcao == 2)
    mulheres_alocadas = sum(1 for s in students if s.alocado and s.genero == 'F')
    cotistas_alocados = sum(1 for s in students if s.alocado and s.is_cotista)

    print("-" * 80)
    print(" RESULTADO DA SELEÇÃO:")
    print(f" Total de Alunos Alocados: {total_alocados} / {total_vagas} vagas")
    print(f"  * Atendidos em 1ª Opção: {alocados_op1}")
    print(f"  * Atendidos em 2ª Opção: {alocados_op2}")
    if total_alocados > 0:
        print(f"  * Mulheres Selecionadas: {mulheres_alocadas} ({mulheres_alocadas/total_alocados*100:.1f}%)")
        print(f"  * Cotistas Selecionados: {cotistas_alocados} ({cotistas_alocados/total_alocados*100:.1f}%)")
    print("-" * 80)

    # 4. Gerar Ofício Oficial em PDF
    generate_pdf_report(
        opportunities=opps,
        students=students,
        output_pdf_path=args.pdf,
        edital_titulo=args.edital
    )

    # 5. Gerar Relatório de Auditoria em Excel
    export_excel_audit(
        opportunities=opps,
        students=students,
        audit_trail=audit,
        output_excel_path=args.excel
    )

    print("=" * 80)
    print(" Processo finalizado com sucesso!")
    print("=" * 80)

if __name__ == '__main__':
    main()
