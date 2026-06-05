from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse

from .models import ImportacaoArquivo, SessaoOperacao, Operacao, ParametrosTrader, JournalOperacao


@admin.register(ImportacaoArquivo)
class ImportacaoArquivoAdmin(admin.ModelAdmin):
    list_display = ['arquivo_nome', 'importado_em', 'total_operacoes']
    readonly_fields = ['importado_em']


@admin.register(SessaoOperacao)
class SessaoOperacaoAdmin(admin.ModelAdmin):
    list_display = ['data_sessao', 'resultado_total',
                    'total_operacoes', 'total_wins', 'total_losses']
    list_filter = ['data_sessao']


@admin.register(Operacao)
class OperacaoAdmin(admin.ModelAdmin):
    list_display = ['abertura', 'ativo', 'lado',
                    'resultado_operacao', 'total_acumulado']
    list_filter = ['ativo', 'lado']
    search_fields = ['ativo']


@admin.register(ParametrosTrader)
class ParametrosTraderAdmin(admin.ModelAdmin):
    fieldsets = [
        ('Limites Operacionais', {
            'fields': ['tempo_minimo_entre_trades', 'max_operacoes_dia']
        }),
    ]

    def changelist_view(self, request, extra_context=None):
        obj, _ = ParametrosTrader.objects.get_or_create(pk=1)
        return HttpResponseRedirect(
            reverse('admin:trades_parametrostrader_change', args=[obj.pk])
        )

    def has_add_permission(self, request):
        return not ParametrosTrader.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(JournalOperacao)
class JournalOperacaoAdmin(admin.ModelAdmin):
    list_display = ['operacao', 'setup', 'emocao',
                    'qualidade_entrada', 'qualidade_saida', 'criado_em']
    list_filter = ['emocao', 'setup']
    search_fields = ['setup', 'tags', 'anotacao']
    readonly_fields = ['criado_em', 'atualizado_em']
