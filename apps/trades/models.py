from django.db import models


class ImportacaoArquivo(models.Model):
    """Controla cada arquivo CSV importado do Profitchart."""

    arquivo_nome = models.CharField(max_length=255)
    importado_em = models.DateTimeField(auto_now_add=True)
    total_operacoes = models.IntegerField(default=0)
    observacao = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = 'Importação de Arquivo'
        verbose_name_plural = 'Importações de Arquivos'
        ordering = ['-importado_em']

    def __str__(self):
        return f'{self.arquivo_nome} ({self.importado_em:%d/%m/%Y %H:%M})'


class SessaoOperacao(models.Model):
    """Agrupa operações por dia de pregão."""

    importacao = models.ForeignKey(
        ImportacaoArquivo,
        on_delete=models.CASCADE,
        related_name='sessoes'
    )
    data_sessao = models.DateField()
    resultado_total = models.DecimalField(
        max_digits=10, decimal_places=2, default=0)
    total_operacoes = models.IntegerField(default=0)
    total_wins = models.IntegerField(default=0)
    total_losses = models.IntegerField(default=0)

    class Meta:
        verbose_name = 'Sessão de Operação'
        verbose_name_plural = 'Sessões de Operações'
        ordering = ['-data_sessao']
        unique_together = ['importacao', 'data_sessao']

    def __str__(self):
        return f'Sessão {self.data_sessao:%d/%m/%Y} — R$ {self.resultado_total}'

    @property
    def win_rate(self):
        if self.total_operacoes == 0:
            return 0
        return round((self.total_wins / self.total_operacoes) * 100, 1)


class Operacao(models.Model):
    """Cada operação individual importada do Profitchart."""

    LADO_CHOICES = [
        ('C', 'Comprado'),
        ('V', 'Vendido'),
    ]

    sessao = models.ForeignKey(
        SessaoOperacao,
        on_delete=models.CASCADE,
        related_name='operacoes'
    )
    importacao = models.ForeignKey(
        ImportacaoArquivo,
        on_delete=models.CASCADE,
        related_name='operacoes'
    )

    # Identificação
    ativo = models.CharField(max_length=20)
    lado = models.CharField(max_length=1, choices=LADO_CHOICES)
    houve_preco_medio = models.BooleanField(default=False)

    # Datas e tempos
    abertura = models.DateTimeField()
    fechamento = models.DateTimeField()
    tempo_operacao = models.CharField(max_length=20)
    tempo_entre_trades = models.CharField(max_length=20, blank=True, null=True)

    # Quantidades
    qtd_compra = models.IntegerField()
    qtd_venda = models.IntegerField()

    # Preços
    preco_compra = models.DecimalField(max_digits=12, decimal_places=2)
    preco_venda = models.DecimalField(max_digits=12, decimal_places=2)
    preco_mercado = models.DecimalField(max_digits=12, decimal_places=2)
    preco_medio = models.DecimalField(
        max_digits=12, decimal_places=2, blank=True, null=True)

    # Excursões
    mep = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    men = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Resultados em pontos
    resultado_operacao_pontos = models.DecimalField(
        max_digits=10, decimal_places=2, default=0)

    # Resultados financeiros (R$)
    resultado_operacao = models.DecimalField(
        max_digits=10, decimal_places=2, default=0)

    # Ganho e perda máximos possíveis
    ganho_maximo = models.DecimalField(
        max_digits=10, decimal_places=2, default=0)
    perda_maxima = models.DecimalField(
        max_digits=10, decimal_places=2, default=0)

    # Acumulado
    total_acumulado = models.DecimalField(
        max_digits=10, decimal_places=2, default=0)

    class Meta:
        verbose_name = 'Operação'
        verbose_name_plural = 'Operações'
        ordering = ['abertura']

    def __str__(self):
        return (
            f'{self.ativo} {self.get_lado_display()} — '
            f'{self.abertura:%d/%m/%Y %H:%M} — R$ {self.resultado_operacao}'
        )

    @property
    def is_win(self):
        return self.resultado_operacao > 0

    @property
    def duracao_minutos(self):
        delta = self.fechamento - self.abertura
        return round(delta.total_seconds() / 60, 1)


class ParametrosTrader(models.Model):
    """
    Configuração singleton do trader.

    Garante uma única instância via pk=1 forçado no save().
    Editável via Django Admin.

    Migração futura para multi-usuário:
      1. Adicionar: usuario = models.OneToOneField(User, on_delete=models.CASCADE)
      2. Trocar carregar() por: get(usuario=request.user)
      3. Criar página de configurações para o usuário editar os próprios parâmetros.
    """

    # ── Revenge Trading ────────────────────────────────────────────
    tempo_minimo_entre_trades = models.IntegerField(
        default=2,
        verbose_name='Tempo mínimo entre trades (min)',
        help_text=(
            'Operação aberta em menos deste tempo após um loss '
            'é marcada como suspeita de revenge trading.'
        ),
    )

    # ── Overtrading ────────────────────────────────────────────────
    max_operacoes_dia = models.IntegerField(
        default=5,
        verbose_name='Máximo de operações por dia',
        help_text=(
            'Dias com mais operações que este valor são '
            'sinalizados como possível overtrading.'
        ),
    )

    capital_inicial = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0
    )

    class Meta:
        verbose_name = 'Parâmetros do Trader'
        verbose_name_plural = 'Parâmetros do Trader'

    def __str__(self):
        return (
            f'Parâmetros: revenge < {self.tempo_minimo_entre_trades}min · '
            f'overtrading > {self.max_operacoes_dia} ops/dia'
        )

    def save(self, *args, **kwargs):
        """Força singleton: sempre salva com pk=1."""
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Impede exclusão do singleton pelo Admin."""
        pass

    @classmethod
    def carregar(cls):
        """Retorna a instância singleton, criando com defaults se não existir."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class JournalOperacao(models.Model):
    EMOCAO_CHOICES = [
        ('calmo',      'Calmo'),
        ('ansioso',    'Ansioso'),
        ('confiante',  'Confiante'),
        ('frustrado',  'Frustrado'),
        ('neutro',     'Neutro'),
    ]

    operacao = models.OneToOneField(
        Operacao, on_delete=models.CASCADE, related_name='journal'
    )
    setup = models.CharField(max_length=50, blank=True)
    tags = models.CharField(max_length=200, blank=True,
                            help_text='Tags separadas por vírgula')
    emocao = models.CharField(
        max_length=20, choices=EMOCAO_CHOICES, blank=True)
    qualidade_entrada = models.IntegerField(null=True, blank=True)
    qualidade_saida = models.IntegerField(null=True, blank=True)
    anotacao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Journal de Operação'
        verbose_name_plural = 'Journal de Operações'
        ordering = ['-operacao__abertura']

    def __str__(self):
        return f'Journal #{self.operacao.pk} — {self.operacao.ativo}'

    def tags_lista(self):
        """Retorna lista de tags limpas."""
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(',') if t.strip()]


class AnotacaoDia(models.Model):
    EMOCAO_CHOICES = [
        ('calmo',      'Calmo'),
        ('ansioso',    'Ansioso'),
        ('confiante',  'Confiante'),
        ('frustrado',  'Frustrado'),
        ('neutro',     'Neutro'),
    ]

    data_sessao = models.DateField(unique=True)
    contexto_mercado = models.TextField(blank=True)
    estado_emocional = models.CharField(
        max_length=20, choices=EMOCAO_CHOICES, blank=True)
    score_dia = models.IntegerField(null=True, blank=True)  # manual, 1–10
    observacao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Anotação do Dia'
        verbose_name_plural = 'Anotações do Dia'
        ordering = ['-data_sessao']

    def __str__(self):
        return f'Anotação {self.data_sessao}'
