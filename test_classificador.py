# -*- coding: utf-8 -*-
"""
Suíte de Testes Automatizados para o Motor de Classificação (classificador.py)
Testa casos difíceis: empates de CRG, idade, números ímpares, cotas, 50% mulheres e dados sujos.
"""

import pytest
import datetime
from classificador import (
    clean_crg,
    clean_matricula,
    clean_phone,
    parse_option_id,
    parse_option_list,
    guess_gender,
    determine_cycle,
    sort_candidates,
    allocate_opportunity,
    run_classification,
    Student,
    Opportunity,
)

def test_clean_crg():
    assert clean_crg("8,5") == 8.5
    assert clean_crg(8.5) == 8.5
    assert clean_crg("7.9884") == 7.9884
    assert clean_crg(" 8.3064 ") == 8.3064
    # Números sem vírgula/ponto digitados na casa dos milhares
    assert clean_crg(8192) == 8.192
    assert clean_crg("7725") == 7.725
    assert clean_crg(9919) == 9.919
    # Observações de texto com número
    assert clean_crg("3.2 (é baixo porque abandonei...)") == 3.2
    # Alunos do primeiro semestre sem CRG
    assert clean_crg("Não tenho ainda (cursando 1º semestre)") == 0.0
    assert clean_crg("não possuo CRG até o momento da inscrição ") == 0.0
    assert clean_crg(None) == 0.0
    assert clean_crg("") == 0.0

def test_clean_matricula():
    assert clean_matricula("202309740124.0") == "202309740124"
    assert clean_matricula(202309740124) == "202309740124"
    assert clean_matricula(" 202409740010 ") == "202409740010"
    assert clean_matricula("MAT-2023-01") == "202301"

def test_clean_phone():
    assert clean_phone(91982335200.0) == "(91) 98233-5200"
    assert clean_phone("91982335200") == "(91) 98233-5200"
    assert clean_phone("9182335200") == "(91) 8233-5200"
    assert clean_phone("5591982335200") == "(91) 98233-5200"

def test_parse_options():
    assert parse_option_id("Opção 9") == "9"
    assert parse_option_id("Opcao 14") == "14"
    assert parse_option_id(14) == "14"
    assert parse_option_id("16) Ambulatório de Clínica Médica.") == "16"
    assert parse_option_id("Opção 5 (Ortopedia)") == "5"
    assert parse_option_id("3.1") == "3.1"
    assert parse_option_id(" 3.1 ") == "3.1"
    
    # Múltiplas opções na 2ª opção
    assert parse_option_list("14 ou 15 ou 16") == ["14", "15", "16"]
    assert parse_option_list("15 ou 16") == ["15", "16"]
    assert parse_option_list("Opção 10") == ["10"]
    assert parse_option_list(None) == []

def test_guess_gender():
    assert guess_gender("Maria Clara Silva") == "F"
    assert guess_gender("Ana Laura Sá") == "F"
    assert guess_gender("Beatriz Brilhante") == "F"
    assert guess_gender("João Pedro Oliveira") == "M"
    assert guess_gender("Carlos Eduardo Santos") == "M"
    assert guess_gender("Lucas Lobato") == "M"
    assert guess_gender("Felipe Kiyoshi") == "M"
    assert guess_gender("Stephany Cristina") == "F"

def test_determine_cycle():
    assert determine_cycle(1) == 'basico'
    assert determine_cycle(4) == 'basico'
    assert determine_cycle(5) == 'clinico'
    assert determine_cycle(8) == 'clinico'
    assert determine_cycle(9) == 'internato'
    assert determine_cycle(12) == 'internato'

def test_tie_break_crg_and_age():
    """Teste de desempate: CRG igual, o aluno mais velho (data de nascimento menor) deve vencer."""
    s1 = Student(
        matricula="1", nome="Candidato Mais Novo", email="novo@ufpa.br", telefone="91999999999",
        crg=8.5000, op1="1", op2_list=[], timestamp=datetime.datetime(2026, 5, 1, 10, 0),
        genero="M", is_cotista=False, forma_ingresso="Ampla", ano_ingresso=2024,
        semestre_atual=5, ciclo="clinico", data_nascimento=datetime.date(2003, 5, 10)
    )
    s2 = Student(
        matricula="2", nome="Candidato Mais Velho", email="velho@ufpa.br", telefone="91988888888",
        crg=8.5000, op1="1", op2_list=[], timestamp=datetime.datetime(2026, 5, 1, 11, 0),
        genero="M", is_cotista=False, forma_ingresso="Ampla", ano_ingresso=2024,
        semestre_atual=5, ciclo="clinico", data_nascimento=datetime.date(1999, 1, 15)
    )
    sorted_list = sort_candidates([s1, s2])
    # O mais velho (1999) deve ficar em 1º lugar
    assert sorted_list[0].nome == "Candidato Mais Velho"

def test_50_percent_women_rule_in_ac():
    """
    Caso difícil: 2 vagas na Ampla Concorrência.
    Candidatos:
    - Homem A (CRG 9.5)
    - Homem B (CRG 9.0)
    - Mulher C (CRG 8.8)
    Sem a cota, Homem A e Homem B entrariam.
    Com a regra dos 50% de mulheres, Homem B (menor homem) deve ser substituído por Mulher C!
    """
    h_a = Student(
        matricula="1", nome="Homem A", email="ha@ufpa.br", telefone="", crg=9.5, op1="1", op2_list=[],
        timestamp=datetime.datetime.now(), genero="M", is_cotista=False, forma_ingresso="Ampla",
        ano_ingresso=2024, semestre_atual=5, ciclo="clinico", data_nascimento=datetime.date(2002, 1, 1)
    )
    h_b = Student(
        matricula="2", nome="Homem B", email="hb@ufpa.br", telefone="", crg=9.0, op1="1", op2_list=[],
        timestamp=datetime.datetime.now(), genero="M", is_cotista=False, forma_ingresso="Ampla",
        ano_ingresso=2024, semestre_atual=5, ciclo="clinico", data_nascimento=datetime.date(2002, 1, 1)
    )
    m_c = Student(
        matricula="3", nome="Mulher C", email="mc@ufpa.br", telefone="", crg=8.8, op1="1", op2_list=[],
        timestamp=datetime.datetime.now(), genero="F", is_cotista=False, forma_ingresso="Ampla",
        ano_ingresso=2024, semestre_atual=5, ciclo="clinico", data_nascimento=datetime.date(2002, 1, 1)
    )

    opp = Opportunity(
        id="1", professor="Prof. Teste", local="HUJBB", atividade="Clinica",
        periodo="Julho", vagas_total=2, ciclos_permitidos=["clinico"],
        percentual_cotas=0.0,  # 2 vagas na AC
        percentual_mulheres=0.5
    )

    selecionados, espera, logs = allocate_opportunity(opp, [h_a, h_b, m_c], vagas_disponiveis=2, rodada_nome="1ª Opção")

    nomes_aprovados = [s.nome for s in selecionados]
    assert "Homem A" in nomes_aprovados
    assert "Mulher C" in nomes_aprovados
    assert "Homem B" not in nomes_aprovados  # foi permutado pela mulher

def test_cotista_with_high_grade_goes_to_ampla():
    """
    Regra legal: Cotista com nota alta ocupa vaga na Ampla Concorrência
    sem gastar a vaga reservada para cotas.
    Vagas: 2 (1 AC, 1 Cota).
    Candidatos:
    - Cotista A (CRG 9.8) -> deve entrar na AC
    - Ampla B (CRG 8.5)   -> fica de fora (a vaga seguinte é reservada de cota)
    - Cotista C (CRG 7.5) -> entra na vaga reservada de Cota
    """
    c_a = Student(
        matricula="1", nome="Cotista A (Alta Nota)", email="ca@ufpa.br", telefone="", crg=9.8, op1="1", op2_list=[],
        timestamp=datetime.datetime.now(), genero="F", is_cotista=True, forma_ingresso="Cota PPI",
        ano_ingresso=2024, semestre_atual=5, ciclo="clinico", data_nascimento=datetime.date(2002, 1, 1)
    )
    a_b = Student(
        matricula="2", nome="Ampla B (Nota Média)", email="ab@ufpa.br", telefone="", crg=8.5, op1="1", op2_list=[],
        timestamp=datetime.datetime.now(), genero="M", is_cotista=False, forma_ingresso="Ampla",
        ano_ingresso=2024, semestre_atual=5, ciclo="clinico", data_nascimento=datetime.date(2002, 1, 1)
    )
    c_c = Student(
        matricula="3", nome="Cotista C (Nota Menor)", email="cc@ufpa.br", telefone="", crg=7.5, op1="1", op2_list=[],
        timestamp=datetime.datetime.now(), genero="F", is_cotista=True, forma_ingresso="Cota Renda",
        ano_ingresso=2024, semestre_atual=5, ciclo="clinico", data_nascimento=datetime.date(2002, 1, 1)
    )

    opp = Opportunity(
        id="1", professor="Prof. Teste", local="HUJBB", atividade="Clinica",
        periodo="Julho", vagas_total=2, ciclos_permitidos=["clinico"],
        percentual_cotas=0.5,
        percentual_mulheres=0.5
    )

    selecionados, espera, logs = allocate_opportunity(opp, [c_a, a_b, c_c], vagas_disponiveis=2, rodada_nome="1ª Opção")

    assert len(selecionados) == 2
    assert selecionados[0].nome == "Cotista A (Alta Nota)"
    assert selecionados[0].modalidade == "Ampla Concorrência"
    assert selecionados[1].nome == "Cotista C (Nota Menor)"
    assert selecionados[1].modalidade == "Cota Reservada"

def test_cota_reversion_to_ampla():
    """
    Reversão de cotas: Se uma vaga de cota não tem cotista inscrito,
    a vaga reverte para a Ampla Concorrência e não fica ociosa.
    """
    a1 = Student(
        matricula="1", nome="Ampla 1", email="a1@ufpa.br", telefone="", crg=9.0, op1="1", op2_list=[],
        timestamp=datetime.datetime.now(), genero="F", is_cotista=False, forma_ingresso="Ampla",
        ano_ingresso=2024, semestre_atual=5, ciclo="clinico", data_nascimento=datetime.date(2002, 1, 1)
    )
    a2 = Student(
        matricula="2", nome="Ampla 2", email="a2@ufpa.br", telefone="", crg=8.0, op1="1", op2_list=[],
        timestamp=datetime.datetime.now(), genero="M", is_cotista=False, forma_ingresso="Ampla",
        ano_ingresso=2024, semestre_atual=5, ciclo="clinico", data_nascimento=datetime.date(2002, 1, 1)
    )

    opp = Opportunity(
        id="1", professor="Prof. Teste", local="HUJBB", atividade="Clinica",
        periodo="Julho", vagas_total=2, ciclos_permitidos=["clinico"],
        percentual_cotas=0.5,
        percentual_mulheres=0.5
    )

    # 2 vagas (1 AC e 1 Cota), mas só há candidatos da Ampla
    selecionados, espera, logs = allocate_opportunity(opp, [a1, a2], vagas_disponiveis=2, rodada_nome="1ª Opção")
    assert len(selecionados) == 2
    assert "Ampla 1" in [s.nome for s in selecionados]
    assert "Ampla 2" in [s.nome for s in selecionados]

def test_second_option_round():
    """
    Remanejamento de 2ª Opção:
    Candidato não aprovado na 1ª opção é alocado na vaga ociosa de sua 2ª opção.
    """
    s_competitivo = Student(
        matricula="1", nome="Estudante Muito Concorrido", email="", telefone="", crg=9.9, op1="OP1", op2_list=["OP2"],
        timestamp=datetime.datetime.now(), genero="F", is_cotista=False, forma_ingresso="Ampla",
        ano_ingresso=2024, semestre_atual=5, ciclo="clinico", data_nascimento=datetime.date(2002, 1, 1)
    )
    s_segundo = Student(
        matricula="2", nome="Estudante Remanejado", email="", telefone="", crg=8.9, op1="OP1", op2_list=["OP2"],
        timestamp=datetime.datetime.now(), genero="F", is_cotista=False, forma_ingresso="Ampla",
        ano_ingresso=2024, semestre_atual=5, ciclo="clinico", data_nascimento=datetime.date(2002, 1, 1)
    )

    opp1 = Opportunity(id="OP1", professor="Prof 1", local="L1", atividade="", periodo="", vagas_total=1, ciclos_permitidos=["clinico"])
    opp2 = Opportunity(id="OP2", professor="Prof 2", local="L2", atividade="", periodo="", vagas_total=1, ciclos_permitidos=["clinico"])

    opps = {"OP1": opp1, "OP2": opp2}
    opps, students, logs = run_classification(opps, [s_competitivo, s_segundo])

    # OP1 preenchida pelo mais alto na 1ª opção
    assert len(opps["OP1"].selecionados) == 1
    assert opps["OP1"].selecionados[0].nome == "Estudante Muito Concorrido"
    assert opps["OP1"].selecionados[0].alocado_opcao == 1

    # OP2 não teve candidatos em 1ª opção, mas recebeu o segundo estudante na 2ª opção
    assert len(opps["OP2"].selecionados) == 1
    assert opps["OP2"].selecionados[0].nome == "Estudante Remanejado"
    assert opps["OP2"].selecionados[0].alocado_opcao == 2
