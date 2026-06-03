from django.contrib import admin
from .models import ImportacaoArquivo, Operacao, ParametrosTrader, SessaoOperacao


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


@admin.register(ParametrosTrader)
class ParametrosTraderAdmin(admin.ModelAdmin):
    """
    Admin do singleton ParametrosTrader.

    - Oculta o botão "Adicionar" (só existe um registro)
    - Redireciona a listagem direto para o formulário de edição
    - Exibe campos agrupados por indicador comportamental
    """

    fieldsets = [
        ('Revenge Trading', {
            'fields': ['tempo_minimo_entre_trades'],
            'description': (
                'Operação aberta em menos deste tempo (em minutos) após um loss '
                'é marcada como suspeita de revenge trading.'
            ),
        }),
        ('Overtrading', {
            'fields': ['max_operacoes_dia'],
            'description': (
                'Dias com mais operações que este valor são '
                'sinalizados como possível overtrading.'
            ),
        }),
    ]

    def has_add_permission(self, request):
        """Impede criação de um segundo registro pelo Admin."""
        return not ParametrosTrader.objects.exists()

    def has_delete_permission(self, request, obj=None):
        """Impede exclusão do singleton pelo Admin."""
        return False

    def changelist_view(self, request, extra_context=None):
        """Redireciona a listagem direto para o formulário de edição do pk=1."""
        from django.shortcuts import redirect
        obj, _ = ParametrosTrader.objects.get_or_create(pk=1)
        return redirect(
            f'/admin/trades/parametrostrader/{obj.pk}/change/'
        )
