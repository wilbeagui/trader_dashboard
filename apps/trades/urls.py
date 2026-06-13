from django.urls import path
from . import views

app_name = "trades"

urlpatterns = [
    path("",                 views.dashboard,       name="dashboard"),
    path("operacoes/",       views.operacoes,        name="operacoes"),
    path("importar/",        views.importar,         name="importar"),
    path("dia/",             views.dia,              name="dia"),
    path("comportamental/",  views.comportamental,   name="comportamental"),
    path('journal/',         views.journal,         name='journal'),
    path('journal/salvar/<int:op_id>/',
         views.salvar_journal, name='salvar_journal'),
    path('relatorio-mensal/', views.relatorio_mensal, name='relatorio_mensal'),
    path('analise-setup/',    views.analise_setup,    name='analise_setup'),
    path('comparativo/',      views.comparativo,      name='comparativo'),
    path('relatorio-anual/',  views.relatorio_anual, name='relatorio_anual'),
]
