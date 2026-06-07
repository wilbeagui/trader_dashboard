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
- Indicadores comportamentais (revenge trading, disciplina) ← IMPLEMENTADO
- Journal de Operações ← IMPLEMENTADO (Passo 1)
- Retorno % sobre Capital + Drawdown no Dashboard ← IMPLEMENTADO (Passo 2)
- Resultado em Pontos ← IMPLEMENTADO (Passo 3)
- Relatório Mensal com comparativo histórico ← IMPLEMENTADO (Passo 4)
- Relatório exportável em PDF ← PLANEJADO (ver Próximos Passos)

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
├── apps/
│   ├── __init__.py
│   └── trades/
│       ├── migrations/
│       ├── admin.py
│       ├── apps.py
│       ├── models.py
│       ├── services.py
│       ├── urls.py
│       └── views.py
├── core/
│   ├── settings/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── development.py
│   │   └── production.py
│   ├── asgi.py
│   ├── urls.py
│   └── wsgi.py
├── static/
├── media/
├── templates/
│   ├── base.html
│   └── trades/
│       ├── comportamental.html
│       ├── dashboard.html
│       ├── dia.html
│       ├── importar.html
│       ├── operacoes.html
│       ├── journal.html          ← CRIADO (Passo 1)
│       └── relatorio_mensal.html ← CRIADO (Passo 4)
├── .env
├── .gitignore
├── CONTEXTO_PROJETO.md
├── manage.py
└── requirements.txt

## Configurações aplicadas
- `INSTALLED_APPS`: app `apps.trades` registrado
- `INSTALLED_APPS`: inclui `django.contrib.humanize` (adicionado no Passo 4)
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

### Operacao ← ATUALIZADO (Passo 3)
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
- `resultado_operacao_pontos` → DecimalField(10,2) ← RENOMEADO/CORRIGIDO (Passo 3)
  fonte CSV: coluna 'Res. Operação (%)' — para futuros representa pontos,
  para ações representa percentual
- `resultado_operacao` → DecimalField(10,2)
  fonte CSV: coluna 'Res. Operação' — resultado em R$
- `ganho_maximo` → DecimalField(10,2)
- `perda_maxima` → DecimalField(10,2)
- `total_acumulado` → DecimalField(10,2)
- @property is_win → resultado_operacao > 0
- @property duracao_minutos → (fechamento - abertura).total_seconds() / 60

Campos REMOVIDOS no Passo 3:
- ~~resultado_intervalo_pontos~~ → substituído por resultado_operacao_pontos
- ~~resultado_intervalo_pct~~ → removido (redundante)
- ~~resultado_operacao_pct~~ → removido (redundante)

### ParametrosTrader ← ATUALIZADO (Passo 2)
Configuração singleton do trader. Editável via Django Admin.
Preparado para futura migração a multi-usuário (adicionar FK User).
- `tempo_minimo_entre_trades` → IntegerField(default=2)
- `max_operacoes_dia`         → IntegerField(default=5)
- `capital_inicial`           → DecimalField(12,2, default=0) ← ADICIONADO (Passo 2)
- `meta_resultado_mensal`     → DecimalField(10,2, default=0) ← A ADICIONAR (Passo 20)
- `drawdown_maximo_permitido` → DecimalField(10,2, default=0) ← A ADICIONAR (Passo 20)
- Meta.verbose_name = "Parâmetros do Trader"
- save() força pk=1 (singleton); delete() bloqueado
- classmethod carregar() → get_or_create(pk=1)

### JournalOperacao ← IMPLEMENTADO (Passo 1)
Anotações qualitativas vinculadas a uma Operacao.
- `operacao` → OneToOneField(Operacao, cascade) related_name='journal'
- `setup` → CharField(50, blank) — nome do setup/estratégia usado
- `tags` → CharField(200, blank) — tags livres separadas por vírgula
  ex: "seguiu_plano,impulso,setup_A"
- `emocao` → CharField(20, choices, blank)
  choices: calmo, ansioso, confiante, frustrado, neutro
- `qualidade_entrada` → IntegerField(null, blank) — nota 1 a 10
- `qualidade_saida`   → IntegerField(null, blank) — nota 1 a 10
- `anotacao`          → TextField(blank) — texto livre do trader
- `criado_em`         → DateTimeField(auto_now_add=True)
- `atualizado_em`     → DateTimeField(auto_now=True)
- tags_lista() → método que retorna lista de tags limpas

### AnotacaoDia ← A CRIAR (Passo 6)
Observações do trader sobre o pregão como um todo.
- `data_sessao` → DateField(unique=True)
- `contexto_mercado` → TextField(blank) — o que estava acontecendo no mercado
- `estado_emocional`  → CharField(20, choices, blank)
  choices: calmo, ansioso, confiante, frustrado, neutro
- `score_dia`         → IntegerField(null, blank) — nota 1 a 10 (manual ou calculado)
- `observacao`        → TextField(blank) — texto livre
- `criado_em`         → DateTimeField(auto_now_add=True)
- `atualizado_em`     → DateTimeField(auto_now=True)

## Arquivos criados e o que fazem

- `core/settings/base.py` → configurações comuns a todos os ambientes
- `core/settings/development.py` → configurações de desenvolvimento
- `core/settings/production.py` → configurações de produção (PostgreSQL)
- `core/urls.py` → URLs principais, inclui apps.trades.urls com namespace 'trades'
- `core/wsgi.py` → aponta para core.settings.development
- `core/asgi.py` → aponta para core.settings.development
- `manage.py` → aponta para core.settings.development
- `apps/trades/models.py` → 5 models ativos (Operacao atualizado no Passo 3;
  JournalOperacao implementado; ParametrosTrader atualizado) + 1 a criar (AnotacaoDia)
- `apps/trades/migrations/0001_initial.py` → migração inicial
- `apps/trades/migrations/0002_parametrostrader.py` → migração ParametrosTrader
- `apps/trades/migrations/0003_journaloperacao.py` → migração JournalOperacao (Passo 1)
- `apps/trades/migrations/0004_parametrostrader_capital_inicial.py` → migração capital_inicial (Passo 2)
- `apps/trades/migrations/0005_operacao_passo3.py` → migração Passo 3: remove campos
  obsoletos, renomeia resultado_intervalo_pontos → resultado_operacao_pontos
- `apps/trades/admin.py` → registra os 5 models; ParametrosTraderAdmin com fieldsets
  "Limites Operacionais" e "Capital"; redireciona listagem direto para edição,
  impede criação de segundo registro e impede exclusão;
  JournalOperacaoAdmin com filtros por emocao e setup
- `apps/trades/views.py` → 8 views ativas + helpers de cálculo e gráficos
- `apps/trades/urls.py` → namespace='trades'; rotas ativas:
  / (dashboard), /operacoes/, /importar/, /dia/, /comportamental/,
  /journal/, /journal/salvar/<op_id>/, /relatorio-mensal/
- `apps/trades/services.py` → lógica de importação do CSV do Profitchart;
  mapeamento corrigido no Passo 3: resultado_operacao_pontos ← 'Res. Operação (%)',
  resultado_operacao ← 'Res. Operação'; chamada corrigida na view importar():
  importar_csv(arquivo, arquivo.name) com retorno tratado como dict
- `templates/base.html` → sidebar com todos os links de navegação incluindo Journal
  e Rel. Mensal; .alert-warning e .val-warn no CSS global
- `templates/trades/dashboard.html` → filter bar; 2 linhas de cards (linha 1:
  Resultado Total com subtítulo pts, Win Rate, Retorno %, Drawdown Máx.;
  linha 2: Operações, Wins/Losses, EM, Payoff Ratio); 4 gráficos Plotly
- `templates/trades/dia.html` → 4 linhas de KPIs; 3 gráficos; tabela com coluna Pts
- `templates/trades/importar.html` → upload drag-and-drop + exclusão por data/ativo
- `templates/trades/operacoes.html` → listagem com filtros, paginação, 4 cards;
  coluna Pts na tabela; coluna Journal com botão por linha; offcanvas drawer Bootstrap
- `templates/trades/comportamental.html` → 5 seções de indicadores comportamentais
- `templates/trades/journal.html` → página dedicada com filtros e métricas por setup
- `templates/trades/relatorio_mensal.html` → página de relatório mensal: 8 cards de KPI
  do mês selecionado, 2 gráficos Plotly (barras de resultado + linha de win rate),
  tabela histórica comparativa com delta mês a mês colorido (Passo 4)
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
- Datas do CSV tratadas com fuso horário America/Sao_Paulo via pytz
- Datas salvas no banco em UTC; sempre converter para America/Sao_Paulo antes de usar
- Paleta de cores: Azul Meia-Noite (#0d1117 fundo, #161b22 cards, #b8c4ce texto)
- Cores de resultado: #3fb68b (positivo) e #e05c5c (negativo)
- Agrupamento de ativos futuros por prefixo via dicionário AGRUPAMENTO_ATIVOS
- Curva de capital: três traces com numpy (área positiva, negativa, linha principal)
- Heat map: zmid=0, cor central #161b22
- Expectativa Matemática exibida no Dashboard; omitida do Dia (baixo valor estatístico)
- Payoff Ratio exibido no Dashboard e Dia (linha 4 de KPIs)
- ParametrosTrader: singleton pk=1; editável via Admin; preparado para multi-usuário
- Indicadores comportamentais em página dedicada /comportamental/
- Exclusão de dados integrada à página Importar com dupla confirmação
- Ícones Bootstrap Icons 1.11.3: bi-brain inexistente → bi-person-check
- Journal: salvo via AJAX (fetch + JsonResponse); drawer fecha automaticamente após 900ms
- Journal: journals_map via query única com __in para não fazer N queries por operação
- Journal: setups existentes passados ao template para autocomplete client-side
- Journal: ícone da coluna muda para bi-journal-check (verde) ao anotar, sem reload
- Drawdown: calculado via helper _drawdown_maximo(df); cumsum + cummax sobre df ordenado
- Retorno %: exibido com sinal explícito (+/-); exibe "—" se capital_inicial == 0
- Win Rate no Dashboard: cor baseada na EM (positiva = verde) em vez de limiar 50%
- Dashboard linha 1: Resultado Total · Win Rate · Retorno % · Drawdown Máx.
- Dashboard linha 2: Operações · Wins/Losses · Expect. Matemática · Payoff Ratio
- Pontos (resultado_operacao_pontos): coluna 'Res. Operação (%)' do CSV do Profitchart;
  para futuros (WIN/WDO) representa pontos; para ações representa percentual;
  exibido com 0 casas decimais nas tabelas; somado e exibido no subtítulo do card
  Resultado Total do dashboard
- importar_csv(): retorna dict {'sucesso', 'total_operacoes', ...}; view trata como dict
- Relatório Mensal: agrupamento por Period('M') do Pandas; delta mês a mês calculado
  para resultado, win rate, total de ops e EM; drawdown calculado inline por mês
  (escopo mensal, não acumulado histórico); django.contrib.humanize adicionado ao
  INSTALLED_APPS para uso futuro de filtros como intcomma


## Regras críticas — OBRIGATÓRIO seguir em qualquer alteração de views.py

### Timezone
- Datas no banco estão em UTC
- Sempre converter para America/Sao_Paulo antes de usar:
  df['abertura'] = pd.to_datetime(df['abertura'], utc=True).dt.tz_convert('America/Sao_Paulo')
- Para filtros de data no queryset usar abertura__date__gte/lte
- Para gráficos Plotly converter datas para string após tz_convert e usar type='category'

### Plotly e gráficos
- include_plotlyjs=False em todos os to_html()
- Plotly.js carregado uma única vez no base.html via CDN (plotly-2.27.0.min.js)
- Nunca usar datas com timezone diretamente no Plotly
- Curva de capital: numpy np.where para máscaras; range explícito no yaxis
- Heat map: zmid=0, cor central #161b22 no colorscale
- Gráfico overtrading: eixo duplo yaxis2 (overlaying='y', side='right')

### Views
- NUNCA fazer duas chamadas Operacao.objects.all() na mesma view
- Aplicar filtros ANTES de passar o queryset para o DataFrame
- Buscar todos os campos em uma única chamada .values()
- Importar QuerySet do Django: from django.db.models import QuerySet

### Agrupamento de ativos
- AGRUPAMENTO_ATIVOS = {'WIN': 3, 'WDO': 3, 'IND': 3, 'DOL': 3}
- Ativos não listados usam nome completo

### Paginação (operacoes)
- Paginator com parâmetros GET: pagina e por_pagina (10/20/50/100)
- Métricas dos cards sobre TODOS os registros filtrados, não só a página

### Acumulado
- NUNCA usar total_acumulado do banco em páginas filtradas
- operacoes(): soma progressiva cronológica
- dia(): df['total_acumulado'] = df['resultado_operacao'].cumsum()

### ParametrosTrader
- Sempre carregar via ParametrosTrader.carregar()
- Referenciar como params.tempo_minimo_entre_trades, params.max_operacoes_dia,
  params.capital_inicial etc.

### Drawdown (adicionado no Passo 2)
- Helper _drawdown_maximo(df): ordena por abertura, cumsum, cummax, retorna max(pico - atual)
- Reutilizar _drawdown_maximo() em qualquer view que precisar de drawdown acumulado
- NUNCA recalcular drawdown inline nas views para o dashboard; sempre usar o helper
- Exceção: relatorio_mensal() calcula drawdown inline por mês (escopo mensal isolado,
  não usa o helper pois o acumulado é reiniciado a cada mês)

### Resultado em Pontos (adicionado no Passo 3)
- Campo no model: resultado_operacao_pontos (DecimalField 10,2)
- Fonte CSV: coluna 'Res. Operação (%)' — NÃO é percentual para futuros, são pontos
- NUNCA referenciar resultado_intervalo_pontos (removido), resultado_intervalo_pct
  (removido) ou resultado_operacao_pct (removido)
- Sempre incluir 'resultado_operacao_pontos' na lista campos[] das views
- Exibir com floatformat:0 nas tabelas (WIN/WDO operam em pontos inteiros)

### importar_csv() (corrigido no Passo 3)
- Assinatura: importar_csv(arquivo, nome_arquivo) — dois argumentos obrigatórios
- Retorna dict: {'sucesso': bool, 'total_operacoes': int, ...}
- Na view importar(): chamar como importar_csv(arquivo, arquivo.name)
- Tratar retorno como dict: importacao['total_operacoes'], não importacao.total_operacoes

### Journal (regras adicionadas no Passo 1)
- Enriquecer registros de operacoes() com dados do journal via query única:
  journals_map = {j.operacao_id: j for j in JournalOperacao.objects.filter(operacao_id__in=todos_ids)}
- NUNCA buscar journal dentro de loop por operação (N+1 queries)
- setups_existentes passados no context de operacoes() para autocomplete
- salvar_journal() retorna JsonResponse({'ok': True, ...}); nunca redireciona
- URL de salvar: /journal/salvar/<op_id>/ (sem prefixo extra — namespace trades está na raiz /)
- r["pk"] = r["id"] obrigatório no loop de operacoes() para expor pk ao template

### Bootstrap Icons
- Versão em uso: 1.11.3
- Verificar existência antes de usar; bi-brain NÃO existe → usar bi-person-check

### PowerShell
- Criar arquivos vazios: New-Item nomedoarquivo

## Estado atual do banco
- Operações reimportadas após limpeza no Passo 3
- 15 dias de pregão
- Período: novembro/2025 até maio/2026
- Instrumento: WIN (mini índice) em vários vencimentos


## Gráficos implementados

### Dashboard
1. Curva de Capital → três traces numpy; área positiva/negativa; linha dinâmica
2. Resultado por Horário → barras verticais coloridas individualmente
3. Resultado por Ativo → barras horizontais agrupadas por instrumento
4. Heat Map Dia × Horário → colorscale divergente, zmid=0, cor central #161b22

### Página Dia
1. Curva de Capital intraday → mesma lógica dashboard; HH:MM; markers nos pontos
2. Resultado por Horário → barras por HH:MM
3. Análise de Execução → MEP/MEN/Resultado; barras horizontais; altura dinâmica

### Página Relatório Mensal
1. Resultado por Mês → barras verticais coloridas individualmente; tickprefix R$
2. Evolução do Win Rate → linha com fill tozeroy; linha de referência 50% tracejada amarela

### Página Comportamental
1. Overtrading → eixo duplo: barras resultado + linha qtd ops; limiar amarelo tracejado
2. Consistência → barras resultado por dia; linha zero destacada

## Métricas avançadas implementadas
- Expectativa Matemática → _calcular_metricas_avancadas(df); Dashboard
- Payoff Ratio → mesma função; Dashboard e Dia
- Drawdown Máximo → _drawdown_maximo(df); Dashboard (Passo 2)
- Retorno % sobre Capital → dashboard(); requer capital_inicial > 0 (Passo 2)
- Resultado em Pontos → resultado_operacao_pontos; Dashboard (subtítulo), Dia e Operações (Passo 3)
- Relatório Mensal → agrupamento por Period('M'); delta mês a mês; retorno % sobre capital (Passo 4)

## Indicadores comportamentais implementados
1. Revenge Trading — limiar: tempo_minimo_entre_trades
2. Overtrading — limiar: max_operacoes_dia
3. Aproveitamento MEP — resultado/MEP × 100 nas winners
4. Gestão de Stop MEN — |MEN|/|resultado| × 100 nas losers
5. Consistência/Disciplina — % dias positivos, desvio padrão, sequência W/L

---

## PRÓXIMOS PASSOS PLANEJADOS — Roadmap de Comercialização

Ordenados por prioridade de impacto comercial. Cada passo descreve
o que fazer, quais arquivos alterar e os detalhes de implementação.

---

### PASSO 1 — Journal de Operações ★★★★★ ✅ CONCLUÍDO
**O que foi implementado:**
- Model `JournalOperacao` (OneToOne com Operacao): setup, tags, emocao,
  qualidade_entrada, qualidade_saida, anotacao, criado_em, atualizado_em; tags_lista()
- Migração `0003_journaloperacao.py`
- `JournalOperacaoAdmin` registrado com filtros por emocao e setup
- View `journal()` → /journal/ com filtros, métricas por setup, listagem com badges
- View `salvar_journal()` → POST /journal/salvar/<op_id>/; JsonResponse; get_or_create
- `operacoes.html` → coluna Journal; offcanvas drawer com formulário completo; AJAX
- `journal.html` → página dedicada completa
- Link "Journal" no sidebar do base.html
- operacoes(): journals_map (query única __in), setups_existentes, r["pk"] = r["id"]

**Bugs corrigidos:**
- r["pk"] = r["id"]: dicts de .values() usam "id", template precisava de "pk"
- {% csrf_token %} dentro do offcanvas: POST retornava 403 sem o token

---

### PASSO 2 — Retorno % sobre Capital + Drawdown no Dashboard ★★★★★ ✅ CONCLUÍDO
**O que foi implementado:**
- Campo `capital_inicial` no model `ParametrosTrader`
- Migração `0004_parametrostrader_capital_inicial.py`
- `ParametrosTraderAdmin` com fieldset "Capital"
- Helper `_drawdown_maximo(df)`: ordena → cumsum → cummax → max(pico - acumulado)
- `dashboard()`: carrega params, calcula drawdown_max, retorno_pct, drawdown_pct
- `dashboard.html` reorganizado: linha 1 (Resultado, Win Rate, Retorno %, Drawdown),
  linha 2 (Operações, Wins/Losses, EM, Payoff Ratio)
- Win Rate: cor baseada na EM (antecipa Passo 9)

**Bug corrigido:**
- Typo "loss_edio" → "loss_medio" no context da dashboard()

---

### PASSO 3 — Resultado em Pontos ★★★★★ ✅ CONCLUÍDO
**O que foi implementado:**
- Model `Operacao` reestruturado:
  - Removidos: resultado_intervalo_pontos, resultado_intervalo_pct, resultado_operacao_pct
  - Adicionado: resultado_operacao_pontos ← CSV 'Res. Operação (%)'
  - Mantido: resultado_operacao ← CSV 'Res. Operação'
- Migração `0005_operacao_passo3.py`
- `services.py` corrigido: mapeamento correto dos dois campos; remoção dos três
  campos obsoletos do Operacao.objects.create()
- `views.py`: resultado_operacao_pontos adicionado em campos[] de dia() e operacoes();
  resultado_pontos calculado em dashboard() e passado ao context
- `dashboard.html`: subtítulo do card Resultado Total exibe "· +632 pts"
- `dia.html`: coluna "Pts" na tabela colorida em fonte mono
- `operacoes.html`: coluna "Pts" na tabela; colspan do empty atualizado para 11

**Bugs corrigidos durante implementação:**
- importar_csv() chamada sem nome_arquivo → corrigido para importar_csv(arquivo, arquivo.name)
- Retorno de importar_csv() tratado como objeto → corrigido para dict: importacao['total_operacoes']
- resultado_operacao_pontos recebia valor errado (igual a resultado_operacao) pois
  apontava para coluna CSV errada ('Res. Intervalo Bruto' → corrigido para 'Res. Operação (%)')

---

### PASSO 4 — Página de Relatório Mensal ★★★★★ ✅ CONCLUÍDO
**O que foi implementado:**
- View `relatorio_mensal()`: agrupa operações por `Period('M')` do Pandas;
  calcula por mês: resultado, pontos, win rate, EM, payoff ratio, drawdown,
  melhor/pior dia, retorno % (se capital_inicial > 0); delta mês a mês para
  resultado, win rate, total de ops e EM
- Rota `/relatorio-mensal/` adicionada ao urls.py
- `relatorio_mensal.html`: 8 cards de KPI do mês selecionado (2 linhas de 4),
  2 gráficos Plotly (barras de resultado por mês + linha de evolução do win rate),
  tabela histórica comparativa com deltas coloridos; linha do mês selecionado
  destacada com table-active; link "—" para Admin quando capital_inicial não
  configurado; filtro por mês via GET com padrão no mês mais recente
- `django.contrib.humanize` adicionado ao INSTALLED_APPS em core/settings/base.py
- Link "Rel. Mensal" adicionado ao sidebar do base.html

**Detalhes técnicos:**
- Drawdown calculado inline por mês (escopo mensal isolado; não usa _drawdown_maximo
  global pois o acumulado é reiniciado a cada mês)
- include_plotlyjs=False em todos os to_html() — padrão do projeto
- Datas convertidas para America/Sao_Paulo antes de qualquer uso

**Bug corrigido:**
- `{% load humanize %}` no template causava TemplateSyntaxError pois
  django.contrib.humanize não estava em INSTALLED_APPS → adicionado ao base.py

---

### PASSO 5 — Resultado em Pontos na Tabela do Dia ★★★★☆
**Status:** implementado junto com Passo 3. ✅ CONCLUÍDO

---

### PASSO 6 — Anotação do Dia (AnotacaoDia) ★★★★☆
**Objetivo:** campo de observação do pregão como um todo —
contexto de mercado, estado emocional, score do dia 1-10.

**Arquivos a criar/alterar:**
- `apps/trades/models.py` → adicionar model AnotacaoDia (ver seção Models)
- `apps/trades/migrations/` → nova migração
- `apps/trades/admin.py` → registrar AnotacaoDia
- `apps/trades/views.py` → dia():
  - Buscar AnotacaoDia.objects.filter(data_sessao=data_sel).first()
  - Calcular score_dia automático baseado em: resultado (40%), win rate (20%),
    aproveitamento MEP (20%), gestão stop MEN (20%) — escala 0-10
  - Passar anotacao_dia e score_dia_calculado ao context
  - Adicionar tratamento POST para salvar/atualizar AnotacaoDia
- `templates/trades/dia.html` → adicionar seção após os KPIs:
  - Card com formulário inline (contexto de mercado, emoção, score manual, observação)
  - Score calculado automaticamente exibido ao lado do score manual
  - Botão salvar que faz POST sem sair da página (form normal com redirect de volta)

**Detalhes de implementação:**
- Score do dia calculado: normalizar cada componente para 0-10 e ponderar
- Se score manual preenchido, exibir ambos (calculado e manual)
- Anotação do dia integrada ao Relatório Mensal (Passo 4)

---

### PASSO 7 — Gráfico de Drawdown ★★★★☆
**Objetivo:** adicionar curva de drawdown abaixo da curva de capital
no Dashboard. Visual padrão em todas plataformas profissionais.

**Arquivos a alterar:**
- `apps/trades/views.py` → adicionar função _grafico_drawdown(df):
  - Calcular série de drawdown ponto a ponto (valor atual - pico histórico)
  - Retornar figura Plotly com área vermelha fill='tozeroy'
  - Altura: 160px (gráfico secundário, menor que o de capital)
- `templates/trades/dashboard.html` → exibir _grafico_drawdown abaixo da
  Curva de Capital, dentro do mesmo chart-card, separado por linha divisória

**Detalhes de implementação:**
- Eixo Y do drawdown sempre negativo (zero = sem drawdown)
- Exibir valor de drawdown máximo do período como anotação no gráfico
- Usar tickprefix="R$ " e tickformat=",.0f" consistente com os demais
- Reutilizar lógica do helper _drawdown_maximo(); não duplicar cálculo

---

### PASSO 8 — Avaliação Relativa no Revenge Trading ★★★★☆
**Objetivo:** corrigir distorção estatística: calcular % de episódios
sobre total de operações em vez de contagem absoluta.

**Arquivos a alterar:**
- `apps/trades/views.py` → _calcular_comportamental():
  - Adicionar revenge_pct = revenge_total / (total_ops - 1) * 100
  - Ajustar limiares de avaliação: baixo < 5%, moderado < 15%, alto >= 15%
- `templates/trades/comportamental.html` → card "Episódios":
  - Exibir contagem e percentual: "3 (7.5%)"
  - Ajustar lógica de coloração para usar revenge_pct nos limiares

---

### PASSO 9 — Win Rate Contextualizado pela EM ★★★★☆ — PARCIALMENTE ANTECIPADO
**Status:** card Win Rate do Dashboard já implementado no Passo 2.
Falta apenas o card Win Rate da página Dia.

**Arquivos a alterar:**
- `templates/trades/dia.html` → card Win Rate:
  - Mesma lógica usando payoff_ratio_dia como proxy (>= 1 = verde)

---

### PASSO 10 — Análise por Setup/Tag ★★★★☆
**Objetivo:** agrupar métricas por setup e tag do journal.
**Depende do Passo 1 (Journal). ✅ Passo 1 concluído.**

**Arquivos a criar/alterar:**
- `apps/trades/views.py` → nova view analise_setup():
  - JOIN entre Operacao e JournalOperacao
  - Agrupar por setup: resultado total, win rate, EM, payoff ratio,
    média de qualidade de entrada/saída, total de operações
  - Agrupar por tag: mesmas métricas
- `apps/trades/urls.py` → rota /analise-setup/
- `templates/trades/analise_setup.html` → tabelas + gráficos por setup e tag
- `templates/base.html` → link no sidebar

---

### PASSO 11 — Correlação Overtrading × Revenge ★★★☆☆
**Objetivo:** seção de correlação cruzada entre indicadores comportamentais.

**Arquivos a alterar:**
- `apps/trades/views.py` → _calcular_comportamental():
  - Correlação de Pearson entre qtd_ops_dia e n_revenge_dia
  - Retornar: corr_overtrade_revenge, revenge_pct_dias_normais, revenge_pct_dias_overtrade
- `templates/trades/comportamental.html` → nova seção com interpretação textual automática

---

### PASSO 12 — Comparativo de Períodos ★★★☆☆
**Objetivo:** comparar dois períodos lado a lado com delta de cada métrica.

**Arquivos a criar/alterar:**
- `apps/trades/views.py` → nova view comparativo()
- `apps/trades/urls.py` → rota /comparativo/
- `templates/trades/comparativo.html` → tabela Métrica | Período 1 | Período 2 | Delta
- `templates/base.html` → link no sidebar

---

### PASSO 13 — Volume por Ativo com Nº de Operações ★★★☆☆
**Arquivos a alterar:**
- `apps/trades/views.py` → _grafico_ativos(): count de operações + texttemplate + hover

---

### PASSO 14 — Score Comportamental Consolidado ★★★☆☆
**Objetivo:** nota única 0–100 combinando os 5 indicadores comportamentais.

**Arquivos a alterar:**
- `apps/trades/views.py` → _calcular_comportamental(): score 0-20 por indicador
- `templates/trades/comportamental.html` → card de score com barra de progresso

---

### PASSO 15 — Histograma de Duração das Operações ★★★☆☆
**Arquivos a alterar:**
- `apps/trades/views.py` → _grafico_histograma_duracao(df): winners vs losers
- `templates/trades/comportamental.html` → gráfico na seção de Consistência

---

### PASSO 16 — Exportação PDF ★★★☆☆
**Dependências:** pip install weasyprint (produção) ou window.print() (simples)
**Arquivos a criar/alterar:**
- `apps/trades/views.py` → nova view exportar_pdf()
- `apps/trades/urls.py` → rota /exportar-pdf/
- `templates/trades/pdf_relatorio.html` → template otimizado para impressão

---

### PASSO 17 — Score do Dia Automático ★★★☆☆
**Implementado em conjunto com Passo 6 (AnotacaoDia).**
**Fórmula:** resultado (40%) + win rate (20%) + MEP (20%) + MEN (20%) → escala 0-10

---

### PASSO 18 — Multi-usuário e Autenticação ★★☆☆☆
**Arquivos a criar/alterar:**
- `apps/trades/models.py` → FK User em todos os models; ParametrosTrader vira OneToOne
- `apps/trades/views.py` → @login_required; filtrar por request.user
- `templates/` → login/logout/registro
- `templates/base.html` → nome do usuário + logout no sidebar

---

### PASSO 19 — Importação Automática / Integração ★★☆☆☆
**Opção A:** watcher de pasta via management command + cron
**Opção B:** endpoint POST /api/importar/ para webhook

---

### PASSO 20 — Metas e Alertas ★★☆☆☆
**Arquivos a alterar:**
- `apps/trades/models.py` → meta_resultado_mensal, drawdown_maximo_permitido
- `apps/trades/views.py` → dashboard(): progresso_meta, alerta_drawdown
- `templates/trades/dashboard.html` → barra de progresso + banner de alerta

---

### PASSO 21 — Linha do Tempo Visual do Dia ★★☆☆☆
**Arquivos a alterar:**
- `apps/trades/views.py` → dia(): dados de timeline por operação
- `templates/trades/dia.html` → SVG/CSS com blocos proporcionais ao tempo

---

### PASSO 22 — Dark/Light Mode ★★☆☆☆
**Arquivos a alterar:**
- `templates/base.html` → variáveis CSS, botão toggle, localStorage

---

### PASSO 23 — App Mobile (PWA) ★☆☆☆☆
**Arquivos a criar/alterar:**
- `static/manifest.json`, `static/sw.js`
- `templates/base.html` → manifest + service worker

---

### ORDEM DE EXECUÇÃO RECOMENDADA

Fase 1 — Fundação analítica:
  ~~Passo 1~~ ✅ → ~~Passo 2~~ ✅ → ~~Passo 3~~ ✅ → Passo 7 → Passo 9

Fase 2 — Diferencial competitivo:
  ~~Passo 1~~ ✅ → Passo 6 → Passo 10 → Passo 14 → Passo 17

Fase 3 — Visão de negócio:
  ~~Passo 4~~ ✅ → Passo 12 → Passo 16

Fase 4 — Refinamentos comportamentais:
  ~~Passo 5~~ ✅ → Passo 8 → Passo 11 → Passo 13 → Passo 15

Fase 5 — Infraestrutura para comercialização:
  Passo 18 → Passo 19 → Passo 20

Fase 6 — Experiência e conveniência:
  Passo 21 → Passo 22 → Passo 23