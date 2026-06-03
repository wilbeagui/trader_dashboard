# Projeto: Trader Dashboard
# Data de início: maio/2026

## Descrição Geral da Aplicação

**Trader Dashboard** é uma aplicação web desenvolvida em Python/Django
para análise de performance de operações realizadas na B3 (Bolsa de
Valores Brasileira).

A aplicação permite importar o relatório de operações exportado pelo
aplicativo Profitchart (formato CSV), armazenando os dados em banco
de dados relacional e apresentando-os em um dashboard visual moderno
com gráficos interativos.

### Objetivo Principal
Oferecer ao trader uma visão analítica completa da sua performance,
identificando padrões de comportamento, horários mais lucrativos,
ativos com melhor resultado, eficiência por estratégia (setup) e
indicadores comportamentais como revenge trading e disciplina
operacional.

### Público-alvo
- Uso próprio do desenvolvedor (fase inicial)
- Traders brasileiros que operam na B3 via Profitchart (fase comercial)

### Funcionalidades Planejadas
- Importação de CSV do Profitchart com tratamento automático dos dados
- Dashboard com curva de capital e principais métricas
- Análise de performance por horário, ativo, dia da semana e setup
- Heat map de resultado por dia da semana × horário
- Indicadores comportamentais (revenge trading, disciplina)
- Relatório exportável em PDF

## Stack
- Python 3.12.7 + Django 6.0.5
- Banco: SQLite (desenvolvimento) → PostgreSQL (produção)
- Processamento: Pandas
- Gráficos: Plotly
- Frontend: Templates Django + Bootstrap 5
- Variáveis de ambiente: python-decouple
- Timezone: pytz

## Apps Django
- `core` → configurações gerais
- `apps.trades` → app principal (operações, importação, dashboard)

## Estrutura de Pastas

trader_dashboard/
├── .venv/
├── apps/                     ← pasta que agrupa todos os apps
│   ├── __init__.py
│   └── trades/               ← app principal
│       ├── migrations/
│       ├── admin.py
│       ├── apps.py
│       ├── models.py
│       ├── services.py
│       ├── urls.py
│       └── views.py
├── core/                     ← configurações do projeto
│   ├── settings/
│   │   ├── __init__.py
│   │   ├── base.py           ← configurações comuns
│   │   ├── development.py    ← SQLite, DEBUG=True
│   │   └── production.py     ← PostgreSQL, DEBUG=False
│   ├── asgi.py
│   ├── urls.py
│   └── wsgi.py
├── static/
├── media/
├── templates/
│   ├── base.html
│   └── trades/
│       ├── comportamental.html  ← NOVO (a criar)
│       ├── dashboard.html
│       ├── dia.html
│       ├── importar.html
│       └── operacoes.html
├── .env
├── .gitignore
├── CONTEXTO_PROJETO.md
├── manage.py
└── requirements.txt

## Configurações aplicadas
- `INSTALLED_APPS`: app `apps.trades` registrado
- `LANGUAGE_CODE`: pt-br
- `TIME_ZONE`: America/Sao_Paulo
- `TEMPLATES DIRS`: BASE_DIR / 'templates'
- `STATIC_URL`: /static/
- `STATICFILES_DIRS`: BASE_DIR / 'static'
- `STATIC_ROOT`: BASE_DIR / 'staticfiles'
- `MEDIA_URL`: /media/
- `MEDIA_ROOT`: BASE_DIR / 'media'
- `BASE_DIR`: Path(__file__).resolve().parent.parent.parent
- `SECRET_KEY`: carregada do .env via python-decouple
- `DEBUG`: carregado do .env via python-decouple

## Ambiente de desenvolvimento
- Editor: VSCode com extensão Python
- Interpretador: .venv (Python 3.12.7)
- Terminal: PowerShell com .venv ativado automaticamente
- Criar arquivos vazios no PowerShell: New-Item nomedoarquivo

## Models definidos — arquivo: apps/trades/models.py

### ImportacaoArquivo
Controla cada arquivo CSV importado do Profitchart.
- `arquivo_nome` → CharField(255)
- `importado_em` → DateTimeField(auto_now_add=True)
- `total_operacoes` → IntegerField(default=0)
- `observacao` → TextField(blank, null)

### SessaoOperacao
Agrupa operações por dia de pregão.
- `importacao` → FK(ImportacaoArquivo, cascade) related_name='sessoes'
- `data_sessao` → DateField
- `resultado_total` → DecimalField(10,2)
- `total_operacoes` → IntegerField
- `total_wins` → IntegerField
- `total_losses` → IntegerField
- unique_together: ['importacao', 'data_sessao']
- @property win_rate → (total_wins / total_operacoes) * 100

### Operacao
Cada trade individual importado do Profitchart.
- `sessao` → FK(SessaoOperacao, cascade) related_name='operacoes'
- `importacao` → FK(ImportacaoArquivo, cascade) related_name='operacoes'
- `ativo` → CharField(20)
- `lado` → CharField(1, choices: C/V)
- `houve_preco_medio` → BooleanField(default=False)
- `abertura` → DateTimeField (salvo em UTC no banco)
- `fechamento` → DateTimeField (salvo em UTC no banco)
- `tempo_operacao` → CharField(20)
- `tempo_entre_trades` → CharField(20, blank, null)
- `qtd_compra` → IntegerField
- `qtd_venda` → IntegerField
- `preco_compra` → DecimalField(12,2)
- `preco_venda` → DecimalField(12,2)
- `preco_mercado` → DecimalField(12,2)
- `preco_medio` → DecimalField(12,2, blank, null)
- `mep` → DecimalField(10,2)
- `men` → DecimalField(10,2)
- `resultado_intervalo_pontos` → DecimalField(10,2)
- `resultado_intervalo_pct` → DecimalField(8,2)
- `resultado_operacao` → DecimalField(10,2)
- `resultado_operacao_pct` → DecimalField(8,2)
- `ganho_maximo` → DecimalField(10,2)
- `perda_maxima` → DecimalField(10,2)
- `total_acumulado` → DecimalField(10,2)
- @property is_win → resultado_operacao > 0
- @property duracao_minutos → (fechamento - abertura).total_seconds() / 60

### ParametrosTrader  ← NOVO (a criar)
Configuração singleton do trader. Editável via Django Admin.
Preparado para futura migração a multi-usuário (adicionar FK User).
- `tempo_minimo_entre_trades` → IntegerField(default=2)  ← minutos; limiar para Revenge Trading
- `max_operacoes_dia`         → IntegerField(default=5)  ← limiar para Overtrading
- Meta.verbose_name = "Parâmetros do Trader"
- save() força pk=1 (singleton)
- classmethod carregar() → get_or_create(pk=1)

## Arquivos criados e o que fazem
- `core/settings/base.py` → configurações comuns a todos os ambientes
- `core/settings/development.py` → configurações de desenvolvimento
- `core/settings/production.py` → configurações de produção (PostgreSQL)
- `core/urls.py` → URLs principais, inclui apps.trades.urls com namespace 'trades'
- `core/wsgi.py` → aponta para core.settings.development
- `core/asgi.py` → aponta para core.settings.development
- `manage.py` → aponta para core.settings.development
- `apps/trades/models.py` → 4 models: ImportacaoArquivo, SessaoOperacao, Operacao, ParametrosTrader
- `apps/trades/migrations/0001_initial.py` → migração inicial
- `apps/trades/admin.py` → registra os 4 models no Django Admin
- `apps/trades/views.py` → 5 views:
  - dashboard() → métricas base + Expectativa Matemática + Payoff Ratio + 4 gráficos Plotly
  - importar() → upload CSV + exclusão de operações por data/ativo
  - operacoes() → listagem com filtros por período e instrumento, paginação (10/20/50/100 por página, padrão 10), métricas calculadas sobre o total (não só a página visível), acumulado recalculado pelo período filtrado
  - dia() → análise detalhada de um dia de pregão: KPIs em 4 linhas (resultado, risco, destaques, Payoff Ratio do dia), 3 gráficos (curva intraday, barras por horário, execução MEP/MEN), tabela do dia; acumulado recalculado via cumsum() apenas do dia
  - comportamental() → NOVA: indicadores comportamentais com ParametrosTrader
- `apps/trades/urls.py` → namespace='trades'; rotas: / (dashboard), /importar/, /operacoes/, /dia/, /comportamental/
- `apps/trades/services.py` → lógica de importação do CSV do Profitchart
  - converter_decimal() → converte string brasileira para Decimal
  - converter_datetime() → converte string para datetime com pytz
  - converter_bool_medio() → converte campo Médio para booleano
  - converter_tet() → trata campo TET (Tempo Entre Trades)
  - importar_csv() → função principal de importação
- `templates/base.html` → template base com sidebar fixa, topbar, Bootstrap 5 + Bootstrap Icons, JetBrains Mono + DM Sans, Plotly.js carregado uma vez no head; sidebar contém bloco nav_dia_seletor para exibir seletor de data na página dia; link para /comportamental/ no sidebar
- `templates/trades/dashboard.html` → filter bar, linha 1 de cards (Resultado, Win Rate, Operações, Wins/Losses), linha 2 de cards (Expectativa Matemática, Payoff Ratio), 4 slots de gráficos Plotly
- `templates/trades/dia.html` → análise detalhada do dia: KPIs linha 1 (Resultado, Win Rate, Fator de Lucro), linha 2 (Drawdown, Exposição Negativa, Operações), linha 3 (Maior Gain, Maior Loss, Tempo Médio Winners, Tempo Médio Losers), linha 4 (Payoff Ratio do dia); curva de capital intraday, resultado por horário, gráfico de execução MEP/MEN, tabela completa do dia
- `templates/trades/importar.html` → upload com drag-and-drop, histórico de importações, instruções do Profitchart, seção "Gerenciar Dados" com exclusão por data+ativo (seletor dinâmico JS, preview, checkbox de confirmação, confirm() no browser)
- `templates/trades/operacoes.html` → listagem com filtros por período e instrumento, seletor de itens por página, 4 cards totalizadores, tabela com badge WIN/LOSS, paginação numérica << < 1 2 3 > >>
- `templates/trades/comportamental.html` → NOVA: página dedicada a indicadores comportamentais
- `.env` → variáveis de ambiente (SECRET_KEY, DEBUG)
- `.gitignore` → arquivos ignorados pelo Git

## Decisões tomadas
- Usar SQLite no desenvolvimento por simplicidade
- Arquivo de importação: CSV exportado pelo Profitchart (encoding latin-1, separador ;)
- Encoding lido via io.StringIO antes de passar ao Pandas
- Comportamento de reimportação: substituir dias existentes
- Django Admin ativado para verificação dos dados
- Apps organizados dentro da pasta apps/
- Settings separados em base/development/production
- Variáveis sensíveis no .env via python-decouple
- Criar arquivos vazios no PowerShell: New-Item nomedoarquivo
- Datas do CSV tratadas com fuso horário America/Sao_Paulo via pytz no momento da importação
- Datas salvas no banco em UTC; sempre converter para America/Sao_Paulo antes de usar
- Paleta de cores: Azul Meia-Noite (#0d1117 fundo, #161b22 cards, #b8c4ce texto)
- Cores de resultado: #3fb68b (positivo) e #e05c5c (negativo)
- Agrupamento de ativos futuros por prefixo via dicionário AGRUPAMENTO_ATIVOS:
  WIN, WDO, IND, DOL → 3 caracteres; ativos não listados usam nome completo
- Curva de capital: três traces separados usando numpy para máscaras:
  1. Área positiva (fill='tozeroy', verde rgba(63,182,139,0.12), line width=0, hoverinfo skip)
  2. Área negativa (fill='tozeroy', vermelha rgba(224,92,92,0.12), line width=0, hoverinfo skip)
  3. Linha principal (cor dinâmica: verde se acumulado final >= 0, vermelha se negativo)
  Requer import numpy as np. Máscaras: np.where(array > 0, array, 0) e np.where(array < 0, array, 0)
  DECISÃO FINAL: esta abordagem resolve o preenchimento por região sem descontinuidade visual,
  pois as áreas são calculadas diretamente via numpy (não por interpolação entre pontos)
- Heat map: colorscale divergente com zmid=0 (centro fixo no zero);
  cor central = #161b22 (fundo do card) → células com valor zero ficam invisíveis,
  evitando falsa impressão de resultado negativo em horários sem negociação
- Expectativa Matemática: calculada na função _calcular_metricas_avancadas();
  EM = (win_rate × gain_médio) + (loss_rate × loss_médio); exibida no Dashboard (visão geral)
  e omitida da página Dia por ter baixo valor estatístico com poucas operações
- Payoff Ratio: gain_médio / |loss_médio|; exibido no Dashboard e na página Dia (linha 4 de KPIs)
  com subtítulo mostrando gain médio e loss médio; fallback "—" quando sem wins ou losses
- ParametrosTrader: singleton (pk=1 forçado no save()); editável via Django Admin;
  preparado para migração futura a multi-usuário adicionando FK User e trocando
  carregar() por get(usuario=request.user)
- Indicadores comportamentais em página dedicada /comportamental/ (não no dashboard),
  pois têm narrativa própria e crescerão independentemente das métricas de performance
- Exclusão de dados: integrada à página Importar; filtra por data + ativo (opcional);
  após delete limpa SessaoOperacao e ImportacaoArquivo órfãos; dupla confirmação
  (checkbox + confirm() JS) para evitar exclusão acidental

## Regras críticas — OBRIGATÓRIO seguir em qualquer alteração de views.py

### Timezone
- Datas no banco estão em UTC
- Sempre converter para America/Sao_Paulo antes de usar:
  df['abertura'] = pd.to_datetime(df['abertura'], utc=True).dt.tz_convert('America/Sao_Paulo')
- Para filtros de data no queryset usar abertura__date__gte/lte
- Para gráficos Plotly converter datas para string após tz_convert:
  datas_str = df['abertura'].dt.strftime('%d/%m/%Y %H:%M')
  E usar type='category' no xaxis do Plotly

### Plotly e gráficos
- include_plotlyjs=False em todos os to_html()
- Plotly.js carregado uma única vez no <head> do base.html via CDN:
  <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
- Nunca usar datas com timezone diretamente no Plotly (causa bugs visuais)
- Sempre usar strftime para converter antes de passar ao Plotly
- Curva de capital: requer import numpy as np; usar np.where para gerar as máscaras
  de área positiva e negativa; calcular ymin/ymax com range explícito no yaxis
- Heat map: usar zmid=0 no go.Heatmap e cor central #161b22 no colorscale;
  NUNCA usar #1c2330 ou outro tom como cor central (zero ficaria colorido)

### Views
- NUNCA fazer duas chamadas Operacao.objects.all() na mesma view
- Aplicar filtros ANTES de passar o queryset para o DataFrame
- Buscar todos os campos necessários em uma única chamada .values()
- Importar QuerySet do Django: from django.db.models import QuerySet

### Agrupamento de ativos
- Usar dicionário AGRUPAMENTO_ATIVOS para agrupar futuros por prefixo:
  AGRUPAMENTO_ATIVOS = {'WIN': 3, 'WDO': 3, 'IND': 3, 'DOL': 3}
- Ativos não listados usam nome completo

### Paginação
- Usar django.core.paginator.Paginator na view operacoes()
- Parâmetros GET: pagina (número da página) e por_pagina (10/20/50/100)
- query_string sem 'pagina' preservado nos links para não quebrar filtros ativos
- Métricas dos cards calculadas sobre TODOS os registros filtrados, não só a página

### Acumulado
- O campo total_acumulado do banco reflete o histórico completo desde a primeira operação
- NUNCA usar total_acumulado do banco diretamente em páginas filtradas por período ou dia
- Em operacoes(): recalcular via soma progressiva sobre os registros do período, na ordem
  cronológica, sobrescrevendo o valor do banco antes de exibir
- Em dia(): recalcular via df['total_acumulado'] = df['resultado_operacao'].cumsum()
  após ordenar o DataFrame por abertura; montar a tabela a partir do DataFrame corrigido

### ParametrosTrader
- Sempre carregar via ParametrosTrader.carregar() no início das views que precisam dos parâmetros
- Nunca instanciar diretamente; usar o classmethod carregar() que garante o singleton
- Nas views, referenciar como params.tempo_minimo_entre_trades, params.max_operacoes_dia etc.

### PowerShell
- Criar arquivos vazios: New-Item nomedoarquivo (não usar "type nul >")

## Estado atual do banco
- 39 operações importadas
- 15 dias de pregão
- Período: novembro/2025 até maio/2026
- Instrumento: WIN (mini índice) em vários vencimentos

## Gráficos implementados no Dashboard
1. Curva de Capital → três traces: área positiva (verde), área negativa (vermelha) e linha
   principal com cor dinâmica; máscaras via numpy (np.where); range do yaxis explícito
2. Resultado por Horário → barras verticais coloridas individualmente por resultado
3. Resultado por Ativo → barras horizontais agrupadas por instrumento (AGRUPAMENTO_ATIVOS)
4. Heat map Dia × Horário → colorscale divergente verde/vermelho, zmid=0,
   cor central #161b22 para que células com valor zero fiquem invisíveis

## Gráficos implementados na página Dia
1. Curva de Capital intraday → mesma lógica do dashboard com três traces e numpy;
   eixo X com HH:MM; linha principal com markers nos pontos das operações
2. Resultado por Horário → barras verticais por HH:MM (não hora cheia como no dashboard)
3. Análise de Execução → barras horizontais por operação mostrando resultado final (barra),
   MEP (marcador triângulo verde) e MEN (marcador triângulo vermelho); altura dinâmica

## Métricas avançadas implementadas
- Expectativa Matemática → função _calcular_metricas_avancadas(df) em views.py;
  retorna None quando não há wins e losses simultaneamente; exibida no Dashboard
- Payoff Ratio (R Múltiplo Médio) → mesma função; exibido no Dashboard e página Dia;
  subtítulo mostra gain_medio e loss_medio para contexto

## Indicadores comportamentais planejados (página /comportamental/)
Todos consomem ParametrosTrader.carregar() para os limiares configuráveis.

1. Revenge Trading
   - Detecta: operação iniciada em menos de params.tempo_minimo_entre_trades minutos após loss
   - Exibe: episódios no período, resultado acumulado nesses trades, destaque na tabela

2. Overtrading
   - Detecta: dias com mais de params.max_operacoes_dia operações
   - Exibe: média de ops/dia, dias acima do limiar, gráfico operações × resultado

3. Aproveitamento do MEP (nas vencedoras)
   - Detecta: razão resultado/MEP nas wins (1.0 = saiu no topo; < 1 = deixou na mesa)
   - Exibe: aproveitamento médio %, operações com maior "desperdício"

4. Gestão de Stop — MEN (nas perdedoras)
   - Detecta: razão |MEN|/|resultado| nas losses (alto = segurou demais antes de sair)
   - Exibe: razão média, operações onde saiu próximo ao pior momento

5. Consistência / Disciplina
   - Detecta: desvio padrão do resultado diário, sequência atual de dias W/L consecutivos
   - Exibe: % dias positivos, desvio padrão, sequência atual

## Próximos passos planejados
- Implementar página /comportamental/ com os 5 indicadores + ParametrosTrader
- Relatório exportável em PDF