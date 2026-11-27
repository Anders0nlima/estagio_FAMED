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
    parse_semestres_permitidos,
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

def test_parse_semestres_permitidos():
    """Valida o parser de requisitos de semestre segundo o documento FAMED 2027."""
    assert parse_semestres_permitidos("Alunos que cursaram do 9º ao 11º semestre em 2026.4.") == [9, 10, 11]
    assert parse_semestres_permitidos("Alunos que cursaram 7º ou 8º semestre em 2026.4.") == [7, 8]
    assert parse_semestres_permitidos("Alunos que cursaram do 5º ao 8º semestre em 2026.4.") == [5, 6, 7, 8]
    assert parse_semestres_permitidos("A partir do 7o semestre") == [7, 8, 9, 10, 11, 12]
    assert parse_semestres_permitidos("clinico") == [5, 6, 7, 8]
    assert parse_semestres_permitidos("internato") == [9, 10, 11, 12]
    assert parse_semestres_permitidos("basico") == [1, 2, 3, 4]
    assert parse_semestres_permitidos("9,10,11") == [9, 10, 11]

def test_cotas_vaga_impar_para_cotista():
    """
    Diretriz FAMED 2027:
    Quando o número de vagas for ímpar, a vaga excedente será destinada aos cotistas.
    Vagas disponíveis: 1 -> 1 cota.
    Vagas disponíveis: 3 -> 2 cotas, 1 ampla.
    """
    c_cotista = Student(
        matricula="101", nome="Aluno Cotista", email="", telefone="", crg=8.0, op1="OP1", op2_list=[],
        timestamp=datetime.datetime.now(), genero="M", is_cotista=True, forma_ingresso="Cota",
        ano_ingresso=2023, semestre_atual=7, ciclo="clinico", data_nascimento=datetime.date(2001, 1, 1)
    )
    c_ampla = Student(
        matricula="102", nome="Aluno Ampla Mais Alto", email="", telefone="", crg=9.5, op1="OP1", op2_list=[],
        timestamp=datetime.datetime.now(), genero="M", is_cotista=False, forma_ingresso="Ampla",
        ano_ingresso=2023, semestre_atual=7, ciclo="clinico", data_nascimento=datetime.date(2001, 1, 1)
    )

    opp_1vaga = Opportunity(
        id="OP1", professor="Prof", local="L", atividade="", periodo="", vagas_total=1,
        ciclos_permitidos=["clinico"], percentual_cotas=0.5, percentual_mulheres=0.0
    )

    # 1 vaga ímpar com cotista concorrendo -> vaga vai para o cotista!
    sel, esp, logs = allocate_opportunity(opp_1vaga, [c_cotista, c_ampla], vagas_disponiveis=1, rodada_nome="1ª Opção")
    assert len(sel) == 1
    assert sel[0].nome == "Aluno Cotista"
    assert sel[0].modalidade == "Cota Reservada"

    # Se NÃO houver cotista, a vaga ímpar reverte para a ampla concorrência!
    opp_1vaga_sem_cota = Opportunity(
        id="OP1", professor="Prof", local="L", atividade="", periodo="", vagas_total=1,
        ciclos_permitidos=["clinico"], percentual_cotas=0.5, percentual_mulheres=0.0
    )
    sel_rev, esp_rev, logs_rev = allocate_opportunity(opp_1vaga_sem_cota, [c_ampla], vagas_disponiveis=1, rodada_nome="1ª Opção")
    assert len(sel_rev) == 1
    assert sel_rev[0].nome == "Aluno Ampla Mais Alto"
    assert sel_rev[0].modalidade == "Ampla Concorrência"

def test_criterio_genero_desativado():
    """
    Quando o critério de gênero está desativado (percentual_mulheres=0.0),
    não há permutas afirmativas de gênero; prevalece estritamente o CRG.
    """
    homem_maior = Student(
        matricula="201", nome="Carlos Homem Alto", email="", telefone="", crg=9.0, op1="OP1", op2_list=[],
        timestamp=datetime.datetime.now(), genero="M", is_cotista=False, forma_ingresso="Ampla",
        ano_ingresso=2023, semestre_atual=7, ciclo="clinico", data_nascimento=datetime.date(2001, 1, 1)
    )
    mulher_menor = Student(
        matricula="202", nome="Mariana Mulher Baixa", email="", telefone="", crg=7.5, op1="OP1", op2_list=[],
        timestamp=datetime.datetime.now(), genero="F", is_cotista=False, forma_ingresso="Ampla",
        ano_ingresso=2023, semestre_atual=7, ciclo="clinico", data_nascimento=datetime.date(2001, 1, 1)
    )

    opp = Opportunity(
        id="OP1", professor="Prof", local="L", atividade="", periodo="", vagas_total=2,
        ciclos_permitidos=["clinico"], percentual_cotas=0.0, percentual_mulheres=0.0
    )

    sel, esp, logs = allocate_opportunity(opp, [homem_maior, mulher_menor], vagas_disponiveis=1, rodada_nome="1ª Opção")
    assert len(sel) == 1
    assert sel[0].nome == "Carlos Homem Alto"

def test_filtro_semestres_especificos():
    """
    Testa o filtro estrito de semestres (ex: 9º ao 11º semestre).
    Alunos fora do intervalo exigido são descartados com log de auditoria.
    """
    s_incompativel = Student(
        matricula="301", nome="Aluno do 8º Semestre", email="", telefone="", crg=9.8, op1="OP1", op2_list=[],
        timestamp=datetime.datetime.now(), genero="M", is_cotista=False, forma_ingresso="Ampla",
        ano_ingresso=2023, semestre_atual=8, ciclo="clinico", data_nascimento=datetime.date(2001, 1, 1)
    )
    s_compativel = Student(
        matricula="302", nome="Aluno do 10º Semestre", email="", telefone="", crg=8.5, op1="OP1", op2_list=[],
        timestamp=datetime.datetime.now(), genero="M", is_cotista=False, forma_ingresso="Ampla",
        ano_ingresso=2022, semestre_atual=10, ciclo="internato", data_nascimento=datetime.date(2000, 1, 1)
    )

    opp = Opportunity(
        id="OP1", professor="Prof. Nefro", local="HUJBB", atividade="Nefro", periodo="Fev",
        vagas_total=1, ciclos_permitidos=["internato"], semestres_permitidos=[9, 10, 11]
    )

    opps, students, logs = run_classification({"OP1": opp}, [s_incompativel, s_compativel])
    
    assert len(opp.selecionados) == 1
    assert opp.selecionados[0].nome == "Aluno do 10º Semestre"
    assert any("[Semestre Incompatível]" in l for l in logs)

def test_divisao_por_ciclo_4_vagas():
    """
    Testa a divisão equitativa de 4 vagas entre Clínico e Internato (2 para cada).
    Mesmo os alunos do Clínico tendo CRGs maiores, os do Internato garantem suas 2 vagas.
    """
    c1 = Student("1", "Clinico Alto 1", "", "", 9.8, "OP1", [], datetime.datetime.now(), "M", False, "Ampla", 2024, 7, "clinico", datetime.date(2002, 1, 1))
    c2 = Student("2", "Clinico Alto 2", "", "", 9.5, "OP1", [], datetime.datetime.now(), "M", False, "Ampla", 2024, 7, "clinico", datetime.date(2002, 1, 1))
    i1 = Student("3", "Internato 1", "", "", 8.0, "OP1", [], datetime.datetime.now(), "M", False, "Ampla", 2022, 10, "internato", datetime.date(2000, 1, 1))
    i2 = Student("4", "Internato 2", "", "", 7.5, "OP1", [], datetime.datetime.now(), "M", False, "Ampla", 2022, 10, "internato", datetime.date(2000, 1, 1))

    opp = Opportunity(
        id="OP1", professor="Prof", local="L", atividade="", periodo="", vagas_total=4,
        ciclos_permitidos=["clinico", "internato"], semestres_permitidos=[7, 8, 9, 10, 11],
        percentual_cotas=0.0, percentual_mulheres=0.0, dividir_por_ciclo=True
    )

    sel, esp, logs = allocate_opportunity(opp, [c1, c2, i1, i2], vagas_disponiveis=4, rodada_nome="1ª Opção")
    
    assert len(sel) == 4
    nomes_sel = {s.nome for s in sel}
    assert "Clinico Alto 1" in nomes_sel
    assert "Clinico Alto 2" in nomes_sel
    assert "Internato 1" in nomes_sel
    assert "Internato 2" in nomes_sel

def test_divisao_por_ciclo_vaga_impar():
    """
    Testa a atribuição de vaga ímpar ao ciclo mais avançado (Internato > Clínico).
    - Com 3 vagas: 2 vão para o Internato e 1 para o Clínico.
    - Com 1 vaga: 1 vai para o Internato e 0 para o Clínico.
    """
    cands_clinico = [
        Student(f"C{i}", f"Clinico {i}", "", "", 9.5 - i*0.1, "OP1", [], datetime.datetime.now(), "M", False, "Ampla", 2024, 7, "clinico", datetime.date(2002, 1, 1))
        for i in range(3)
    ]
    cands_internato = [
        Student(f"I{i}", f"Internato {i}", "", "", 8.5 - i*0.1, "OP1", [], datetime.datetime.now(), "M", False, "Ampla", 2022, 10, "internato", datetime.date(2000, 1, 1))
        for i in range(3)
    ]

    # Teste com 3 vagas
    opp_3 = Opportunity(
        id="OP1", professor="Prof", local="L", atividade="", periodo="", vagas_total=3,
        ciclos_permitidos=["clinico", "internato"], semestres_permitidos=[7, 8, 9, 10, 11],
        percentual_cotas=0.0, percentual_mulheres=0.0, dividir_por_ciclo=True
    )
    sel_3, _, _ = allocate_opportunity(opp_3, cands_clinico + cands_internato, vagas_disponiveis=3)
    internatos_sel = [s for s in sel_3 if s.ciclo == "internato"]
    clinicos_sel = [s for s in sel_3 if s.ciclo == "clinico"]
    assert len(internatos_sel) == 2, "Vaga ímpar de 3 deve dar 2 para o Internato"
    assert len(clinicos_sel) == 1, "Vaga de 3 deve dar 1 para o Clínico"

    # Reset status
    for s in cands_clinico + cands_internato:
        s.alocado = False
        s.alocado_em = None
        s.motivo_alocacao = ""

    # Teste com 1 vaga única
    opp_1 = Opportunity(
        id="OP1", professor="Prof", local="L", atividade="", periodo="", vagas_total=1,
        ciclos_permitidos=["clinico", "internato"], semestres_permitidos=[7, 8, 9, 10, 11],
        percentual_cotas=0.0, percentual_mulheres=0.0, dividir_por_ciclo=True
    )
    sel_1, _, _ = allocate_opportunity(opp_1, cands_clinico + cands_internato, vagas_disponiveis=1)
    assert len(sel_1) == 1
    assert sel_1[0].ciclo == "internato", "Vaga única (ímpar) deve ir para o mais avançado (Internato)"

def test_divisao_por_ciclo_transbordo():
    """
    Testa transbordo de vagas remanescentes:
    Se uma oportunidade tem 4 vagas (2 Internato, 2 Clínico), mas nenhum aluno do Internato se inscreveu,
    as 2 vagas do Internato migram para o Clínico (sem desperdício de vagas).
    """
    cands_clinico = [
        Student(f"C{i}", f"Clinico {i}", "", "", 9.5 - i*0.1, "OP1", [], datetime.datetime.now(), "M", False, "Ampla", 2024, 7, "clinico", datetime.date(2002, 1, 1))
        for i in range(4)
    ]
    opp = Opportunity(
        id="OP1", professor="Prof", local="L", atividade="", periodo="", vagas_total=4,
        ciclos_permitidos=["clinico", "internato"], semestres_permitidos=[7, 8, 9, 10, 11],
        percentual_cotas=0.0, percentual_mulheres=0.0, dividir_por_ciclo=True
    )
    sel, _, logs = allocate_opportunity(opp, cands_clinico, vagas_disponiveis=4)
    assert len(sel) == 4
    assert all(s.ciclo == "clinico" for s in sel)
    assert any("[Transbordo entre Ciclos]" in l for l in logs)

def test_divisao_por_ciclo_desativada():
    """
    Testa o botão desligado (dividir_por_ciclo = False).
    A concorrência ocorre puramente por CRG entre todos os semestres autorizados.
    """
    c1 = Student("1", "Clinico 1", "", "", 9.8, "OP1", [], datetime.datetime.now(), "M", False, "Ampla", 2024, 7, "clinico", datetime.date(2002, 1, 1))
    c2 = Student("2", "Clinico 2", "", "", 9.7, "OP1", [], datetime.datetime.now(), "M", False, "Ampla", 2024, 7, "clinico", datetime.date(2002, 1, 1))
    i1 = Student("3", "Internato 1", "", "", 8.0, "OP1", [], datetime.datetime.now(), "M", False, "Ampla", 2022, 10, "internato", datetime.date(2000, 1, 1))
    i2 = Student("4", "Internato 2", "", "", 7.5, "OP1", [], datetime.datetime.now(), "M", False, "Ampla", 2022, 10, "internato", datetime.date(2000, 1, 1))

    opp = Opportunity(
        id="OP1", professor="Prof", local="L", atividade="", periodo="", vagas_total=2,
        ciclos_permitidos=["clinico", "internato"], semestres_permitidos=[7, 8, 9, 10, 11],
        percentual_cotas=0.0, percentual_mulheres=0.0, dividir_por_ciclo=False
    )
    sel, esp, logs = allocate_opportunity(opp, [c1, c2, i1, i2], vagas_disponiveis=2)
    assert len(sel) == 2
    assert sel[0].nome == "Clinico 1"
    assert sel[1].nome == "Clinico 2"
    assert any("[Divisão por Ciclo Desativada]" in l for l in logs)

def test_gerar_certificado_word_conteudo_e_layout(tmp_path):
    """
    Testa a geração do Certificado oficial em Word (.docx) no formato A4 normal:
    - Valida dimensões A4 (8.27 x 11.69 polegadas)
    - Valida texto padrão exato solicitado pela diretoria
    - Valida carga horária personalizada
    - Valida assinatura final do Diretor da FAMED
    """
    import os
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
    django.setup()

    import docx
    from docx.shared import Inches
    from estagios.models import Edital, Oportunidade, Candidato, Resultado
    from estagios.services import gerar_certificado_individual_word, salvar_frequencias_em_lote

    edital = Edital.objects.create(
        titulo="Estágio de Férias FAMED",
        semestre="2027.1",
        numero_oficio="414/2027",
        protocolo="23073.012345/2027-89",
    )
    try:
        op = Oportunidade.objects.create(
            edital=edital,
            codigo_opcao="5",
            professor="João Alberto Maradei",
            local="Hospital Maradei",
            atividade="Acompanhamento ortopédico",
            periodo="24/07 a 23/08: segunda, quarta e sexta (7h às 19h)",
            vagas_totais=1,
        )
        cand = Candidato.objects.create(
            edital=edital,
            matricula="202309740093",
            nome="Louise Vitória Dias Pena Costa",
            email="louise.costa@icm.ufpa.br",
            telefone="(91) 98888-0000",
            crg_oficial=8.85,
            semestre=7,
            ciclo="clinico",
            op1=5,
        )
        resultado = Resultado.objects.create(
            edital=edital,
            candidato=cand,
            oportunidade=op,
            status="APROVADO",
            concluiu_estagio=True,
            frequencia_percentual=100.0,
            carga_horaria_horas=45,  # Horas customizadas
        )

        docx_file = str(tmp_path / "teste_certificado.docx")
        gerar_certificado_individual_word(resultado, docx_file)

        assert os.path.exists(docx_file), "O arquivo .docx deve ter sido criado com sucesso."
        
        doc = docx.Document(docx_file)
        section = doc.sections[0]
        
        # Valida formato A4 (aproximadamente 8.27 x 11.69 polegadas)
        assert abs(section.page_width.inches - 8.27) < 0.05
        assert abs(section.page_height.inches - 11.69) < 0.05

        # Concatena todo o texto do documento
        doc_text = " ".join(p.text for p in doc.paragraphs)

        # Valida que o cabeçalho ministerial foi removido conforme solicitação da diretoria
        assert "REPÚBLICA FEDERATIVA DO BRASIL" not in doc_text
        assert "MINISTÉRIO DA EDUCAÇÃO" not in doc_text

        # Valida título
        assert "CERTIFICADO DE ESTÁGIO VOLUNTÁRIO" in doc_text

        # Valida texto padrão exato do discente e carga horária
        assert "LOUISE VITÓRIA DIAS PENA COSTA" in doc_text
        assert "202309740093" in doc_text
        assert "ESTÁGIO DE FÉRIAS DA FAMED-UFPA" in doc_text
        assert "serviço do Hospital Maradei" in doc_text
        assert "João Alberto Maradei" in doc_text
        assert "24/07 a 23/08: segunda, quarta e sexta (7h às 19h)" in doc_text
        assert "45 horas" in doc_text

        # Valida assinatura do Diretor da FAMED no final
        assert "Prof. Dr. Cezar Augusto Muniz Caldas" in doc_text
        assert "Diretor da Faculdade de Medicina" in doc_text
        assert "FAMED / ICM – UFPA" in doc_text
    finally:
        edital.delete()

def test_salvar_carga_horaria_em_lote():
    """
    Testa a atualização da carga horária personalizada submetida pelo Diretor
    através da função salvar_frequencias_em_lote.
    """
    import os
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
    django.setup()

    from estagios.models import Edital, Oportunidade, Candidato, Resultado
    from estagios.services import salvar_frequencias_em_lote

    edital = Edital.objects.create(
        titulo="Edital Teste Carga",
        semestre="2027.2",
    )
    try:
        op = Oportunidade.objects.create(
            edital=edital,
            codigo_opcao="1",
            professor="Prof Teste",
            local="HUJBB",
            periodo="Integral",
            vagas_totais=1,
        )
        cand = Candidato.objects.create(
            edital=edital,
            matricula="202300001",
            nome="Aluno Teste",
            crg_oficial=8.0,
            semestre=8,
            ciclo="clinico",
            op1=1,
        )
        res = Resultado.objects.create(
            edital=edital,
            candidato=cand,
            oportunidade=op,
            status="APROVADO",
            carga_horaria_horas=36,
        )

        dados_post = {
            f"status_{res.id}": "APTO",
            f"freq_{res.id}": "90",
            f"carga_{res.id}": "48",  # Diretor editou para 48h
        }

        salvar_frequencias_em_lote(edital, dados_post)

        res.refresh_from_db()
        assert res.carga_horaria_horas == 48
        assert res.frequencia_percentual == 90.0
        assert res.concluiu_estagio is True
    finally:
        edital.delete()


def test_parse_opportunities_docx_padrao_2027():
    """Valida a extração automática das 21 oportunidades a partir do documento .docx do Diretor."""
    import os
    from classificador import parse_opportunities_docx

    docx_path = os.path.join("teste_fluxo", "Estagio_de_Ferias_FAMED_2027_Candidatura.docx")
    ops = parse_opportunities_docx(docx_path)

    assert len(ops) == 21
    assert sum(op["vagas_total"] for op in ops) == 60
    assert ops[0]["id"] == "1"
    assert ops[0]["professor"] == "Lucas Lobato Acatauassu Nunes"
    assert ops[0]["semestres_permitidos"] == [9, 10, 11]
    assert ops[6]["id"] == "7"
    assert ops[6]["semestres_permitidos"] == [7, 8]
    assert ops[20]["id"] == "21"
    assert ops[20]["professor"] == "Cyane Costa"


def test_load_cotas_file_excel_consolidado():
    """Valida o carregamento da planilha consolidada de cotistas (.xlsx) com busca por matrícula e nome."""
    import os
    from classificador import load_cotas_file, normalize_name

    xlsx_path = os.path.join("teste_fluxo", "Cotistas_FAMED_Consolidado.xlsx")
    cotas = load_cotas_file(xlsx_path)

    assert "202209740050" in cotas
    assert cotas["202209740050"]["is_cotista"] is True
    assert normalize_name("Aluizio Ramos Pereira neto ") in cotas
    assert cotas[normalize_name("Aluizio Ramos Pereira neto ")]["matricula"] == "202209740154"


def test_importacao_novos_arquivos_padrao_2027():
    """Valida a importação conjunta dos 3 novos arquivos padrão (docx vagas, xlsx alunos sem CRG, xlsx cotistas)."""
    import os
    import django
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
    django.setup()

    from estagios.models import Edital
    from estagios.services import importar_planilhas_edital

    edital = Edital.objects.create(
        titulo="Estágio de Férias FAMED - Janeiro e Fevereiro de 2027",
        semestre="2027.1",
        ano=2027,
    )
    try:
        res = importar_planilhas_edital(edital)
        assert res["oportunidades"] == 21
        assert res["ignorados_vazios"] == 5
        assert res["tem_coluna_crg"] is False
        assert res["vermelhos"] == res["total"]

        # Sem candidatos fantasma e sem duplicatas por erro de matrícula (ex: Ageu, Aluizio, Erik)
        assert not edital.candidatos.filter(nome__iexact="none").exists()
        assert edital.candidatos.filter(nome__icontains="Aluizio Ramos Pereira").count() == 1
        assert edital.candidatos.filter(nome__icontains="Ageu Salgado Santos").count() == 1
        assert edital.candidatos.filter(nome__icontains="Erik Renan da Silva Pina").count() == 1

        # Cotistas identificados e matrícula corrigida quando necessário (ex: Gustavo Sales Andreatta)
        gustavo = edital.candidatos.get(nome__icontains="Gustavo Sales Andreatta")
        assert gustavo.is_cotista is True
        assert gustavo.matricula == "202309740046"
        assert gustavo.semestre == 8
    finally:
        edital.delete()


def test_extrair_dados_historico_pdf_sigaa():
    """Valida a extração automática de Matrícula, Nome e CRG do PDF real do SIGAA."""
    import os
    import django
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
    django.setup()

    from estagios.services import extrair_dados_historico_pdf

    pdf_path = os.path.join("teste_fluxo", "historico_201909740072 (1) - Allyson Santos.pdf")
    with open(pdf_path, "rb") as f:
        dados = extrair_dados_historico_pdf(f.read(), filename=os.path.basename(pdf_path))

    assert dados["ok"] is True
    assert dados["matricula"] == "201909740072"
    assert dados["nome"] == "ALLYSON MICHEL MIRANDA SANTOS"
    assert dados["crg"] == 4.9765


def test_importar_crgs_historicos_zip():
    """Valida o processamento em lote de um .zip com histórico PDF do SIGAA e uma imagem ignorada."""
    import os
    import zipfile
    from io import BytesIO
    import django
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
    django.setup()

    from django.core.files.uploadedfile import SimpleUploadedFile
    from estagios.models import Edital
    from estagios.services import importar_planilhas_edital, importar_crgs_historicos_zip_ou_pdfs

    edital = Edital.objects.create(
        titulo="Estágio de Férias FAMED - Teste PDF ZIP",
        semestre="2027.1",
        ano=2027,
    )
    try:
        importar_planilhas_edital(edital)

        pdf_path = os.path.join("teste_fluxo", "historico_201909740072 (1) - Allyson Santos.pdf")
        zip_buf = BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.write(pdf_path, arcname="historico_201909740072 (1) - Allyson Santos.pdf")
            zf.writestr("foto_celular_aluno.jpg", b"fake-jpeg-bytes")

        zip_file = SimpleUploadedFile("historicos.zip", zip_buf.getvalue(), content_type="application/zip")
        res = importar_crgs_historicos_zip_ou_pdfs(edital, [zip_file])

        assert res["pdfs_lidos"] == 1
        assert res["atualizados"] == 1
        assert res["imagens_ignoradas"] == 1

        allyson = edital.candidatos.get(matricula="201909740072")
        assert allyson.crg_oficial == 4.9765
        assert allyson.status_auditoria == "VERDE"
        assert allyson.auditado_pelo_diretor is True
    finally:
        edital.delete()


def test_importar_crgs_dos_links_drive():
    """
    Testa a extração paralela a partir de links do Google Drive:
    - Link aberto retornando PDF do SIGAA: preenche CRG e valida (Verde)
    - Link restrito (HTML de login): contabiliza como restrito sem travar
    - Link com imagem/foto: contabiliza imagem e mantém em Revisão
    """
    import os
    from unittest.mock import patch
    import django
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
    django.setup()

    from estagios.models import Edital, Candidato
    from estagios.services import _extract_gdrive_file_id, importar_crgs_dos_links_drive

    assert _extract_gdrive_file_id("https://drive.google.com/open?id=1jrdSU8SzNf0-gruDZiTIdzuCFe5cF_yT") == "1jrdSU8SzNf0-gruDZiTIdzuCFe5cF_yT"
    assert _extract_gdrive_file_id("https://drive.google.com/file/d/ABC_123-xyz/view?usp=sharing") == "ABC_123-xyz"

    pdf_path = os.path.join("teste_fluxo", "historico_201909740072 (1) - Allyson Santos.pdf")
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    edital = Edital.objects.create(titulo="Edital Teste Links Drive", semestre="2027.1", ano=2027)
    try:
        c_ok = Candidato.objects.create(
            edital=edital, matricula="201909740072", nome="Allyson Santos",
            crg_digitado="Não informado no Forms", crg_oficial=0.0,
            status_auditoria="VERMELHO", auditado_pelo_diretor=False,
            op1="3", link_historico="https://drive.google.com/open?id=ID_OK"
        )
        c_rest = Candidato.objects.create(
            edital=edital, matricula="202300000001", nome="Aluno Restrito",
            crg_digitado="Não informado no Forms", crg_oficial=0.0,
            status_auditoria="VERMELHO", auditado_pelo_diretor=False,
            op1="8", link_historico="https://drive.google.com/open?id=ID_RESTRITO"
        )
        c_img = Candidato.objects.create(
            edital=edital, matricula="202300000002", nome="Aluno Foto",
            crg_digitado="Não informado no Forms", crg_oficial=0.0,
            status_auditoria="VERMELHO", auditado_pelo_diretor=False,
            op1="8", link_historico="https://drive.google.com/open?id=ID_IMAGEM"
        )

        def fake_download(url, session=None):
            if "ID_OK" in url:
                return {"ok": True, "bytes": pdf_bytes}
            if "ID_RESTRITO" in url:
                return {"ok": False, "reason": "restrito"}
            return {"ok": False, "reason": "imagem"}

        with patch("estagios.services._download_gdrive_pdf_bytes", side_effect=fake_download):
            res = importar_crgs_dos_links_drive(edital)

        assert res["total_links"] == 3
        assert res["atualizados"] == 1
        assert res["restritos"] == 1
        assert res["imagens"] == 1

        c_ok.refresh_from_db()
        c_rest.refresh_from_db()
        c_img.refresh_from_db()
        assert c_ok.crg_oficial == 4.9765
        assert c_ok.status_auditoria == "VERDE"
        assert c_ok.auditado_pelo_diretor is True
        assert c_rest.status_auditoria == "VERMELHO"
        assert c_img.status_auditoria == "VERMELHO"
    finally:
        edital.delete()


def test_upload_planilhas_view_extrai_crgs_automaticamente():
    """
    Valida que ao enviar as planilhas sem coluna de CRG, a view já dispara
    a extração automática dos links do Google Drive antes mesmo de abrir a auditoria.
    """
    import os
    from unittest.mock import patch
    import django
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
    django.setup()

    from django.test import Client
    from django.core.files.uploadedfile import SimpleUploadedFile
    from estagios.models import Edital

    pdf_path = os.path.join("teste_fluxo", "historico_201909740072 (1) - Allyson Santos.pdf")
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    edital = Edital.objects.create(titulo="Edital Teste Auto CRG Upload", semestre="2027.1", ano=2027)
    try:
        allyson_url = "https://drive.google.com/open?id=1jrdSU8SzNf0-gruDZiTIdzuCFe5cF_yT"
        def fake_dl(url, session=None):
            # Retorna o PDF válido do Allyson quando encontrar a matrícula/link do Allyson na planilha
            return {"ok": True, "bytes": pdf_bytes} if "18kSS93SxZEGxTPRCrglmHiJrStTz4V8-" not in url else {"ok": False, "reason": "imagem"}

        vagas_path = os.path.join("teste_fluxo", "Estagio_de_Ferias_FAMED_2027_Candidatura.docx")
        alunos_path = os.path.join("teste_fluxo", "Estágio de Férias FAMED Jan-Fev 2027 (respostas).xlsx")
        cotas_path = os.path.join("teste_fluxo", "Cotistas_FAMED_Consolidado.xlsx")

        with open(vagas_path, "rb") as fv, open(alunos_path, "rb") as fa, open(cotas_path, "rb") as fc:
            with patch("estagios.services._download_gdrive_pdf_bytes", side_effect=fake_dl):
                res = Client().post(
                    f"/edital/{edital.id}/upload/",
                    {
                        "arquivo_vagas": SimpleUploadedFile("vagas.docx", fv.read()),
                        "arquivo_alunos": SimpleUploadedFile("alunos.xlsx", fa.read()),
                        "arquivo_ingresso": SimpleUploadedFile("cotas.xlsx", fc.read()),
                    },
                    follow=False,
                )

        assert res.status_code == 302
        allyson = edital.candidatos.get(matricula="201909740072")
        assert allyson.crg_oficial == 4.9765
        assert allyson.status_auditoria == "VERDE"
        assert allyson.auditado_pelo_diretor is True
    finally:
        edital.delete()

