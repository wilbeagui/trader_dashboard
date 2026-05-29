from django.contrib import admin
from .models import ImportacaoArquivo, SessaoOperacao, Operacao


@admin.register(ImportacaoArquivo)
class ImportacaoArquivoAdmin(admin.ModelAdmin):
    list_display = ['arquivo_nome', 'importado_em', 'total_operacoes']
    readonly_fields = ['importado_em']


@admin.register(SessaoOperacao)
class SessaoOperacaoAdmin(admin.ModelAdmin):
    list_display = ['data_sessao', 'total_operacoes',
                    'total_wins', 'total_losses', 'resultado_total']
    list_filter = ['data_sessao']


@admin.register(Operacao)
class OperacaoAdmin(admin.ModelAdmin):
    list_display = ['ativo', 'lado', 'abertura',
                    'fechamento', 'resultado_operacao', 'total_acumulado']
    list_filter = ['ativo', 'lado']
    ordering = ['abertura']
