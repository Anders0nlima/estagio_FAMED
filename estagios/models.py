from django.db import models
from django.utils import timezone
import os

class Edital(models.Model):
    STATUS_CHOICES = [
        ('CRIADO', 'Edital Criado'),
        ('IMPORTADO', 'Planilhas Importadas'),
        ('AUDITADO', 'Históricos Auditados'),
        ('CLASSIFICADO', 'Resultado Homologado'),
    ]

    titulo = models.CharField(max_length=255, verbose_name="Título do Edital")
    semestre = models.CharField(max_length=50, default="2026.1", verbose_name="Semestre Letivo")
    ano = models.IntegerField(default=2026, verbose_name="Ano")
    numero_oficio = models.CharField(max_length=100, default="414 / 2026", verbose_name="Número do Ofício")
    protocolo = models.CharField(max_length=100, default="23073.092158/2026-14", verbose_name="Protocolo SIPAC")
    
    # Parâmetros de Seleção
    percentual_cotas = models.FloatField(default=0.5, verbose_name="Percentual de Cotas (0.0 a 1.0)")
    percentual_mulheres = models.FloatField(default=0.5, verbose_name="Mínimo de Mulheres (0.0 a 1.0)")
    
    # Arquivos
    arquivo_vagas = models.FileField(upload_to='editais/vagas/', null=True, blank=True, verbose_name="Planilha dos Professores (Vagas)")
    arquivo_alunos = models.FileField(upload_to='editais/alunos/', null=True, blank=True, verbose_name="Planilha dos Alunos (Inscrições)")
    arquivo_ingresso = models.FileField(upload_to='editais/ingresso/', null=True, blank=True, verbose_name="CSV de Forma de Ingresso (Cotas)")
    
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='CRIADO')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.titulo} ({self.semestre})"

    @property
    def total_vagas(self):
        return sum(op.vagas_totais for op in self.oportunidades.all())

    @property
    def total_candidatos(self):
        return self.candidatos.count()

    @property
    def pendencias_auditoria_count(self):
        return self.candidatos.filter(status_auditoria__in=['AMARELO', 'VERMELHO'], auditado_pelo_diretor=False).count()

class Oportunidade(models.Model):
    edital = models.ForeignKey(Edital, on_delete=models.CASCADE, related_name='oportunidades')
    codigo_opcao = models.CharField(max_length=50, verbose_name="Código da Opção")
    professor = models.CharField(max_length=255, verbose_name="Professor Responsável")
    local = models.CharField(max_length=255, verbose_name="Local do Estágio")
    atividade = models.TextField(blank=True, verbose_name="Descrição da Atividade")
    periodo = models.CharField(max_length=255, verbose_name="Período e Horários")
    vagas_totais = models.IntegerField(default=1, verbose_name="Total de Vagas")
    ciclos_permitidos = models.CharField(max_length=255, default="basico,clinico,internato", verbose_name="Ciclos Permitidos")
    vagas_preenchidas = models.IntegerField(default=0)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"Opção {self.codigo_opcao} - {self.professor} ({self.local})"

class Candidato(models.Model):
    STATUS_SEMAFORO = [
        ('VERDE', 'Validado Automaticamente'),
        ('AMARELO', 'Divergência de Nota'),
        ('VERMELHO', 'Revisão Manual Necessária'),
    ]

    edital = models.ForeignKey(Edital, on_delete=models.CASCADE, related_name='candidatos')
    matricula = models.CharField(max_length=50, verbose_name="Matrícula")
    nome = models.CharField(max_length=255, verbose_name="Nome Completo")
    email = models.EmailField(blank=True, verbose_name="E-mail")
    telefone = models.CharField(max_length=50, blank=True, verbose_name="Telefone")
    
    crg_digitado = models.CharField(max_length=255, blank=True, verbose_name="CRG Digitado no Forms")
    crg_oficial = models.FloatField(default=0.0, verbose_name="CRG Homologado")
    link_historico = models.CharField(max_length=500, blank=True, verbose_name="Link do Histórico Escolar")
    
    status_auditoria = models.CharField(max_length=20, choices=STATUS_SEMAFORO, default='VERDE')
    motivo_auditoria = models.CharField(max_length=255, blank=True)
    auditado_pelo_diretor = models.BooleanField(default=False)
    
    op1 = models.CharField(max_length=50, verbose_name="1ª Opção")
    op2 = models.CharField(max_length=255, blank=True, verbose_name="2ª Opção")
    
    genero = models.CharField(max_length=1, choices=[('F', 'Feminino'), ('M', 'Masculino')], default='F')
    is_cotista = models.BooleanField(default=False)
    forma_ingresso = models.CharField(max_length=255, default="Ampla Concorrência")
    ano_ingresso = models.IntegerField(default=2024)
    semestre = models.IntegerField(default=5)
    ciclo = models.CharField(max_length=50, default="clinico")
    data_nascimento = models.DateField(null=True, blank=True)
    timestamp_inscricao = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-crg_oficial', 'data_nascimento']

    def __str__(self):
        return f"{self.nome} ({self.matricula}) - CRG: {self.crg_oficial}"

    @property
    def crg_oficial_dot(self):
        return f"{self.crg_oficial:.4f}"

class Resultado(models.Model):
    STATUS_RESULTADO = [
        ('APROVADO', 'Aprovado'),
        ('RESERVA', 'Cadastro de Reserva'),
    ]

    edital = models.ForeignKey(Edital, on_delete=models.CASCADE, related_name='resultados')
    candidato = models.ForeignKey(Candidato, on_delete=models.CASCADE, related_name='resultados')
    oportunidade = models.ForeignKey(Oportunidade, on_delete=models.CASCADE, null=True, blank=True, related_name='alocados')
    
    status = models.CharField(max_length=20, choices=STATUS_RESULTADO, default='RESERVA')
    posicao = models.IntegerField(default=1)
    modalidade = models.CharField(max_length=100, default="Ampla Concorrência")
    opcao_atendida = models.CharField(max_length=50, blank=True)  # "1ª Opção", "2ª Opção"
    etiqueta_motivo = models.CharField(max_length=255, blank=True)

    # --- Campos de Frequência e Pós-Estágio ---
    frequencia_percentual = models.FloatField(null=True, blank=True, verbose_name="% de Frequência")
    concluiu_estagio = models.BooleanField(default=False, verbose_name="Concluiu com Frequência Suficiente (>=75%)")
    justificativa_frequencia = models.CharField(max_length=255, blank=True, default="Pendente de confirmação")
    carga_horaria_horas = models.IntegerField(default=36, verbose_name="Carga Horária (horas)")
    
    # --- Certificado e Autenticidade ---
    certificado_arquivo = models.FileField(upload_to='certificados/', null=True, blank=True)
    certificado_codigo = models.CharField(max_length=64, blank=True, verbose_name="Código de Autenticidade Único")
    certificado_gerado_em = models.DateTimeField(null=True, blank=True)
    
    # --- Envio por E-mail ---
    email_enviado = models.BooleanField(default=False, verbose_name="Certificado Enviado por E-mail")
    email_enviado_em = models.DateTimeField(null=True, blank=True)
    email_log = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['oportunidade__id', 'posicao', '-candidato__crg_oficial']

    def __str__(self):
        return f"{self.candidato.nome} - {self.status} na Opção {self.oportunidade.codigo_opcao if self.oportunidade else 'N/A'}"

    @property
    def status_conclusao(self):
        if self.concluiu_estagio:
            return 'APTO'
        if self.frequencia_percentual is not None or (self.justificativa_frequencia and 'reprovad' in self.justificativa_frequencia.lower()):
            return 'REPROVADO'
        return 'PENDENTE'

class LogDecisao(models.Model):
    edital = models.ForeignKey(Edital, on_delete=models.CASCADE, related_name='logs')
    registro = models.TextField()
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"Log #{self.id} - {self.registro[:60]}"
