from django.db import models

# Create your models here.

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
    resultado_intervalo_pontos = models.DecimalField(
        max_digits=10, decimal_places=2, default=0)
    resultado_intervalo_pct = models.DecimalField(
        max_digits=8, decimal_places=2, default=0)

    # Resultados financeiros (R$)
    resultado_operacao = models.DecimalField(
        max_digits=10, decimal_places=2, default=0)
    resultado_operacao_pct = models.DecimalField(
        max_digits=8, decimal_places=2, default=0)

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
        return f'{self.ativo} {self.get_lado_display()} — {self.abertura:%d/%m/%Y %H:%M} — R$ {self.resultado_operacao}'

    @property
    def is_win(self):
        return self.resultado_operacao > 0

    @property
    def duracao_minutos(self):
        delta = self.fechamento - self.abertura
        return round(delta.total_seconds() / 60, 1)
