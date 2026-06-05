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
    path('journal/salvar/<int:op_id>/', views.salvar_journal, name='salvar_journal'),
]
