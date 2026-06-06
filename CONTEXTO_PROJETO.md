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
│       └── relatorio_mensal.html ← A CRIAR (Passo 4)
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
- `apps/trades/models.py` → 5 models ativos (JournalOperacao implementado;
  ParametrosTrader atualizado com capital_inicial) + 1 a criar (AnotacaoDia)
- `apps/trades/migrations/0001_initial.py` → migração inicial
- `apps/trades/migrations/0002_parametrostrader.py` → migração ParametrosTrader
- `apps/trades/migrations/0003_journaloperacao.py` → migração JournalOperacao (Passo 1)
- `apps/trades/migrations/0004_parametrostrader_capital_inicial.py` → migração capital_inicial (Passo 2)
- `apps/trades/admin.py` → registra os 5 models; ParametrosTraderAdmin com fieldsets
  "Limites Operacionais" e "Capital"; redireciona listagem direto para edição,
  impede criação de segundo registro e impede exclusão;
  JournalOperacaoAdmin com filtros por emocao e setup
- `apps/trades/views.py` → 7 views ativas + helpers de cálculo e gráficos
- `apps/trades/urls.py` → namespace='trades'; rotas ativas:
  / (dashboard), /operacoes/, /importar/, /dia/, /comportamental/,
  /journal/, /journal/salvar/<op_id>/
- `apps/trades/services.py` → lógica de importação do CSV do Profitchart
- `templates/base.html` → sidebar com todos os links de navegação incluindo Journal;
  .alert-warning e .val-warn no CSS global
- `templates/trades/dashboard.html` → filter bar; 2 linhas de cards (linha 1:
  Resultado Total, Win Rate, Retorno %, Drawdown Máx.; linha 2: Operações,
  Wins/Losses, EM, Payoff Ratio); 4 gráficos Plotly
- `templates/trades/dia.html` → 4 linhas de KPIs; 3 gráficos; tabela completa
- `templates/trades/importar.html` → upload drag-and-drop + exclusão por data/ativo
- `templates/trades/operacoes.html` → listagem com filtros, paginação, 4 cards;
  coluna Journal com botão por linha; offcanvas drawer Bootstrap com formulário
  completo (setup + autocomplete, tags, emoção em chips, qualidade 1-10, anotação);
  salvo via AJAX sem reload; ícone muda de cor ao anotar
- `templates/trades/comportamental.html` → 5 seções de indicadores comportamentais
- `templates/trades/journal.html` → página dedicada com filtros (setup, emoção, tag,
  período); tabela de métricas por setup (win rate, resultado, média/op, qualidade
  entrada/saída); listagem de anotações com badges de tags e emoção
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
  (Passo 9 antecipado no Passo 2)
- Dashboard linha 1: Resultado Total · Win Rate · Retorno % · Drawdown Máx.
- Dashboard linha 2: Operações · Wins/Losses · Expect. Matemática · Payoff Ratio

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
- Reutilizar _drawdown_maximo() em qualquer view que precisar de drawdown
- NUNCA recalcular drawdown inline nas views; sempre usar o helper

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
- 39 operações importadas
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

### Página Comportamental
1. Overtrading → eixo duplo: barras resultado + linha qtd ops; limiar amarelo tracejado
2. Consistência → barras resultado por dia; linha zero destacada

## Métricas avançadas implementadas
- Expectativa Matemática → _calcular_metricas_avancadas(df); Dashboard
- Payoff Ratio → mesma função; Dashboard e Dia
- Drawdown Máximo → _drawdown_maximo(df); Dashboard (Passo 2)
- Retorno % sobre Capital → dashboard(); requer capital_inicial > 0 (Passo 2)

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
**Objetivo:** permitir que o trader anote motivo, setup, emoção e
qualidade de cada operação individualmente. É o recurso mais valorizado
por traders profissionais e o core de ferramentas como Edgewonk.

**O que foi implementado:**
- Model `JournalOperacao` (OneToOne com Operacao): setup, tags, emocao, qualidade_entrada,
  qualidade_saida, anotacao, criado_em, atualizado_em; método tags_lista()
- Migração `0003_journaloperacao.py`
- `JournalOperacaoAdmin` registrado com filtros por emocao e setup
- View `journal()` → página /journal/ com filtros por setup/emoção/tag/período;
  métricas por setup (win rate, resultado total, média/op, qualidade entrada/saída);
  listagem com badges de tags e emoção coloridos
- View `salvar_journal()` → POST /journal/salvar/<op_id>/; retorna JsonResponse;
  cria ou atualiza JournalOperacao via get_or_create
- `operacoes.html` → coluna Journal na tabela com botão por linha (bi-journal-plus /
  bi-journal-check); offcanvas drawer Bootstrap com: campo setup + autocomplete
  client-side, campo tags com hint, chips de emoção, botões de qualidade 1-10
  coloridos por faixa, textarea de anotação, botão salvar via AJAX; ícone e cor
  do botão atualizados sem reload após salvar
- `journal.html` → página dedicada completa com filtros, tabela de performance
  por setup, listagem de anotações com todos os metadados
- Link "Journal" adicionado ao sidebar do base.html
- operacoes(): enriquecida com journals_map (query única com __in),
  setups_existentes para autocomplete e r["pk"] = r["id"] para expor pk ao template

**Bugs corrigidos durante implementação:**
- r["pk"] = r["id"] no loop: dicts de .values() usam "id", template precisava de "pk"
- {% csrf_token %} dentro do offcanvas: POST retornava 403 sem o token

---

### PASSO 2 — Retorno % sobre Capital + Drawdown no Dashboard ★★★★★ ✅ CONCLUÍDO
**Objetivo:** adicionar capital inicial configurável e exibir resultado
como % do capital; adicionar drawdown máximo como card no dashboard.

**O que foi implementado:**
- Campo `capital_inicial` adicionado ao model `ParametrosTrader`
- Migração `0004_parametrostrader_capital_inicial.py`
- `ParametrosTraderAdmin` atualizado com fieldset "Capital"
- Helper `_drawdown_maximo(df)` adicionado ao views.py:
  ordena por abertura → cumsum → cummax → retorna max(pico - acumulado)
- `dashboard()` atualizada: carrega params, calcula drawdown_max, retorno_pct
  e drawdown_pct (None se capital_inicial == 0)
- `dashboard.html` reorganizado em 2 linhas de 4 cards cada:
  - Linha 1: Resultado Total · Win Rate · Retorno % · Drawdown Máx.
  - Linha 2: Operações · Wins/Losses · Expect. Matemática · Payoff Ratio
- Win Rate antecipa Passo 9: cor baseada na EM (positiva = verde), não no limiar 50%
- Retorno % e Drawdown % exibem "—" quando capital_inicial == 0

**Bug corrigido durante implementação:**
- Typo "loss_edio" → "loss_medio" no context da dashboard()

---

### PASSO 3 — Resultado em Pontos ★★★★★
**Objetivo:** exibir resultado em pontos do contrato além de R$ em
todas as telas relevantes. Traders de futuros pensam em pontos primeiro.

**Arquivos a alterar:**
- `apps/trades/views.py`:
  - dashboard(): calcular resultado_pontos = soma de resultado_intervalo_pontos
  - dia(): adicionar coluna resultado_intervalo_pontos no DataFrame e na tabela
  - operacoes(): adicionar resultado_intervalo_pontos no .values() e na listagem
- `templates/trades/dashboard.html` → subtítulo do card Resultado Total:
  "R$ X.XXX · Y.YYY pts"
- `templates/trades/dia.html` → coluna adicional na tabela: "Pts"
  entre Resultado e Duração
- `templates/trades/operacoes.html` → coluna adicional "Pts" na tabela

**Detalhes de implementação:**
- resultado_intervalo_pontos já existe no model e é importado do CSV
- Exibir com 0 casas decimais para WIN/IND (contrato inteiro) e
  2 casas para WDO/DOL (frações de ponto)
- No dashboard, somar os pontos do período filtrado e exibir no subtítulo do card

---

### PASSO 4 — Página de Relatório Mensal ★★★★★
**Objetivo:** visão consolidada por mês com todas as métricas;
comparativo mês a mês; base para exportação PDF.

**Arquivos a criar/alterar:**
- `apps/trades/views.py` → nova view relatorio_mensal():
  - Agrupar operações por ano/mês
  - Para cada mês calcular: resultado, win rate, payoff ratio, EM,
    drawdown, total ops, dias operados, melhor dia, pior dia
  - Calcular delta mês a mês (variação de cada métrica)
  - Passar lista de meses com todas as métricas ao context
- `apps/trades/urls.py` → rota /relatorio-mensal/
- `templates/trades/relatorio_mensal.html` → criar página com:
  - Cards de resumo do mês selecionado (filtro por mês/ano)
  - Tabela comparativa de todos os meses com delta colorido
  - Gráfico de barras de resultado por mês
  - Gráfico de evolução do win rate por mês
  - Botão "Exportar PDF" (integrado com Passo 16)
- `templates/base.html` → adicionar link no sidebar

**Detalhes de implementação:**
- Filtro por mês: select com opções geradas dinamicamente a partir dos dados
- Delta colorido: verde se melhorou, vermelho se piorou vs mês anterior
- Mês selecionado padrão: mês mais recente com dados

---

### PASSO 5 — Resultado em Pontos na Tabela do Dia ★★★★☆
**Objetivo:** adicionar coluna de pontos na tabela da página Dia.
Baixíssima complexidade, alto valor para traders de futuros.
(Implementado em conjunto com Passo 3)

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
**Objetivo:** remover coloração binária do Win Rate (>= 50% = verde).
Colorir baseado na Expectativa Matemática (EM positiva = verde).

**Status:** card Win Rate do Dashboard já implementado no Passo 2.
Falta apenas o card Win Rate da página Dia.

**Arquivos a alterar:**
- `templates/trades/dia.html` → card Win Rate:
  - Mesma lógica usando payoff_ratio_dia como proxy (>= 1 = verde)

---

### PASSO 10 — Análise por Setup/Tag ★★★★☆
**Objetivo:** agrupar métricas por setup e tag do journal.
Permite identificar quais estratégias funcionam de verdade.
**Depende do Passo 1 (Journal). ✅ Passo 1 concluído.**

**Arquivos a criar/alterar:**
- `apps/trades/views.py` → nova view analise_setup():
  - JOIN entre Operacao e JournalOperacao
  - Agrupar por setup: calcular resultado total, win rate, EM, payoff ratio,
    média de qualidade de entrada/saída, total de operações
  - Agrupar por tag: mesmas métricas
  - Passar listas ao context
- `apps/trades/urls.py` → rota /analise-setup/
- `templates/trades/analise_setup.html` → criar página com:
  - Tabela de performance por setup com todas as métricas
  - Tabela de performance por tag
  - Gráfico de barras de resultado por setup
  - Gráfico de barras de resultado por tag
- `templates/base.html` → adicionar link no sidebar (seção Análise)

---

### PASSO 11 — Correlação Overtrading × Revenge ★★★☆☆
**Objetivo:** seção de correlação cruzada entre indicadores comportamentais.
"Nos dias de overtrading, o revenge trading aumentou X%."

**Arquivos a alterar:**
- `apps/trades/views.py` → _calcular_comportamental():
  - Identificar dias de overtrading
  - Nesses dias, calcular taxa de revenge trading
  - Comparar com taxa de revenge nos dias normais
  - Calcular correlação de Pearson entre qtd_ops_dia e n_revenge_dia
  - Retornar: corr_overtrade_revenge, revenge_pct_dias_normais,
    revenge_pct_dias_overtrade
- `templates/trades/comportamental.html` → nova seção ao final:
  - Card com correlação e interpretação textual automática
  - Ex: "Em dias de overtrading, revenge trading foi 3x mais frequente"

---

### PASSO 12 — Comparativo de Períodos ★★★☆☆
**Objetivo:** comparar dois períodos lado a lado com delta de cada métrica.

**Arquivos a criar/alterar:**
- `apps/trades/views.py` → nova view comparativo():
  - Parâmetros GET: periodo1_inicio, periodo1_fim, periodo2_inicio, periodo2_fim
  - Calcular todas as métricas para cada período
  - Calcular delta absoluto e percentual de cada métrica
- `apps/trades/urls.py` → rota /comparativo/
- `templates/trades/comparativo.html` → criar página com:
  - Dois filtros de período lado a lado
  - Tabela de métricas com colunas: Métrica | Período 1 | Período 2 | Delta
  - Delta colorido (verde = melhora, vermelho = piora)
- `templates/base.html` → link no sidebar

---

### PASSO 13 — Volume por Ativo com Nº de Operações ★★★☆☆
**Objetivo:** exibir qtd de operações nas barras do gráfico de ativos.
Evita distorção de um ativo com 1 operação boa.

**Arquivos a alterar:**
- `apps/trades/views.py` → _grafico_ativos():
  - Agrupar também por count de operações
  - Adicionar texttemplate no go.Bar com qtd de ops
  - Adicionar hover com resultado e qtd de operações

---

### PASSO 14 — Score Comportamental Consolidado ★★★☆☆
**Objetivo:** nota única 0–100 combinando os 5 indicadores comportamentais.

**Arquivos a alterar:**
- `apps/trades/views.py` → _calcular_comportamental():
  - Calcular score de cada indicador normalizado para 0-20 pontos
  - Revenge: 20 pts se 0%, decrescendo até 0 pts se >= 15%
  - Overtrading: 20 pts se 0 dias, decrescendo
  - MEP: 20 pts se aprov_medio >= 80%, proporcional
  - MEN: 20 pts se razao_media <= 110%, decrescendo
  - Consistência: 20 pts se pct_dias_positivos >= 70%, proporcional
  - score_total = soma dos 5 (0-100)
  - Retornar score_total e breakdown por indicador
- `templates/trades/comportamental.html` → card de score no topo da página:
  - Número grande com cor: >= 70 verde, 40-69 amarelo, < 40 vermelho
  - Barra de progresso visual
  - Breakdown dos 5 componentes em mini-barras

---

### PASSO 15 — Histograma de Duração das Operações ★★★☆☆
**Objetivo:** distribuição das durações (winners vs losers) em histograma.

**Arquivos a alterar:**
- `apps/trades/views.py` → nova função _grafico_histograma_duracao(df):
  - Calcular duracao_min para cada operação (fechamento - abertura)
  - Criar histograma Plotly com duas séries sobrepostas:
    winners (verde) e losers (vermelho)
  - Eixo X: minutos; Eixo Y: frequência
- `templates/trades/comportamental.html` → adicionar gráfico na seção
  de Consistência/Disciplina

---

### PASSO 16 — Exportação PDF ★★★☆☆
**Objetivo:** relatório consolidado com métricas e gráficos para
registro e compartilhamento.

**Dependências:** pip install weasyprint ou xhtml2pdf
**Arquivos a criar/alterar:**
- `apps/trades/views.py` → nova view exportar_pdf():
  - Receber parâmetros de período e tipo (diário/mensal)
  - Renderizar template HTML específico para PDF
  - Converter para PDF via WeasyPrint
  - Retornar HttpResponse com content_type='application/pdf'
- `apps/trades/urls.py` → rota /exportar-pdf/
- `templates/trades/pdf_relatorio.html` → template otimizado para impressão:
  - CSS específico para PDF (@media print)
  - Sem sidebar, sem filtros interativos
  - Logo, período, todas as métricas, gráficos como imagem estática
  - Usando Plotly .to_image() (requer kaleido: pip install kaleido)
- Botão "Exportar PDF" nas páginas Dia e Relatório Mensal

**Detalhes de implementação:**
- Gráficos: converter figuras Plotly para PNG base64 com fig.to_image()
  e embutir no HTML antes de passar ao WeasyPrint
- Alternativa mais simples: usar CSS @media print e botão window.print()
  sem dependência externa (menor fidelidade mas zero dependência)
- Recomendado: implementar primeiro com window.print() e depois migrar
  para WeasyPrint na fase de produção

---

### PASSO 17 — Score do Dia Automático ★★★☆☆
**Objetivo:** nota calculada automaticamente para cada dia (0-10)
combinando resultado, disciplina, aproveitamento MEP e gestão de stop.
**Implementado em conjunto com Passo 6 (AnotacaoDia).**

**Fórmula sugerida:**
- Componente resultado (40%): normalizar resultado do dia entre -10 e +10
  usando desvio padrão histórico como referência
- Componente win rate (20%): win_rate_dia / 100 * 2 (0-2 pontos)
- Componente MEP (20%): aprov_medio_dia / 100 * 2 (0-2 pontos)
- Componente MEN (20%): max(0, 2 - (men_razao_dia - 100) / 100) (0-2 pontos)
- Score final = soma dos componentes, arredondado para 1 casa decimal

---

### PASSO 18 — Multi-usuário e Autenticação ★★☆☆☆
**Objetivo:** login por usuário, dados isolados, base para planos de acesso.
ParametrosTrader já preparado para esta migração.

**Arquivos a criar/alterar:**
- `core/settings/base.py` → adicionar django.contrib.auth ao INSTALLED_APPS
  (já está por padrão); configurar LOGIN_URL, LOGIN_REDIRECT_URL
- `core/urls.py` → incluir django.contrib.auth.urls
- `apps/trades/models.py`:
  - Adicionar campo `usuario = models.ForeignKey(User, on_delete=CASCADE)`
    em: Operacao, ImportacaoArquivo, SessaoOperacao, JournalOperacao, AnotacaoDia
  - ParametrosTrader: trocar singleton por OneToOneField(User)
  - Criar migration correspondente
- `apps/trades/views.py`:
  - Decorar todas as views com @login_required
  - Filtrar todos os querysets por request.user
  - ParametrosTrader.carregar() → ParametrosTrader.objects.get(usuario=request.user)
- `templates/` → criar templates de login/logout/registro
- `templates/base.html` → exibir nome do usuário logado no sidebar footer;
  link de logout

**Detalhes de implementação:**
- Migração de dados existentes: script one-shot para associar registros
  sem usuário ao superuser (dados do desenvolvedor)
- Planos de acesso: adicionar campo plano ao model User (via UserProfile)
  com choices: gratuito, profissional, enterprise
- Controle de acesso por plano: decorator customizado check_plano()

---

### PASSO 19 — Importação Automática / Integração ★★☆☆☆
**Objetivo:** reduzir fricção do uso diário; importar sem CSV manual.

**Opções a avaliar:**
- Opção A (mais simples): watcher de pasta — usuário configura uma pasta
  e o sistema monitora novos CSVs automaticamente via Django management command
  agendado com cron/Celery
- Opção B: webhook receptor — Profitchart ou corretora envia dados via API;
  criar endpoint POST /api/importar/ que recebe e processa
- Opção C: integração direta com API da corretora (requer análise por corretora)

**Arquivos a criar (Opção A):**
- `apps/trades/management/commands/importar_pasta.py` → management command
- `apps/trades/views.py` → nova view api_importar() para Opção B
- Documentar configuração do cron no README

---

### PASSO 20 — Metas e Alertas ★★☆☆☆
**Objetivo:** meta de resultado mensal com barra de progresso;
alerta de drawdown máximo configurável.

**Arquivos a alterar:**
- `apps/trades/models.py` → adicionar ao ParametrosTrader:
  - meta_resultado_mensal → DecimalField(10,2, default=0)
  - drawdown_maximo_permitido → DecimalField(10,2, default=0)
- `apps/trades/admin.py` → adicionar campos ao fieldset
- `apps/trades/views.py` → dashboard():
  - Calcular resultado do mês atual
  - Calcular progresso_meta = resultado_mes / meta * 100 (se meta > 0)
  - Verificar se drawdown_atual > drawdown_maximo_permitido → alerta_drawdown = True
- `templates/trades/dashboard.html`:
  - Barra de progresso da meta mensal abaixo dos cards principais
  - Banner de alerta (vermelho) se drawdown ultrapassou o limite configurado

---

### PASSO 21 — Linha do Tempo Visual do Dia ★★☆☆☆
**Objetivo:** timeline horizontal com cada operação como bloco colorido.
Visual diferenciado que facilita leitura do fluxo do dia.

**Arquivos a alterar:**
- `apps/trades/views.py` → dia(): preparar dados de timeline:
  - Para cada operação: hora_abertura, hora_fechamento, resultado, ativo
  - Calcular posição proporcional na janela de 09:00-18:00
- `templates/trades/dia.html` → adicionar seção de timeline:
  - SVG ou div CSS com blocos proporcionais ao tempo de duração
  - Cor: verde (win) ou vermelho (loss)
  - Tooltip com detalhes ao hover
  - Posicionada entre os KPIs e a curva de capital

---

### PASSO 22 — Dark/Light Mode ★★☆☆☆
**Objetivo:** alternância de tema escuro/claro.

**Arquivos a alterar:**
- `templates/base.html`:
  - Adicionar variáveis CSS para tema claro em @media (prefers-color-scheme: light)
  - Adicionar botão toggle no topbar
  - Salvar preferência em localStorage
  - Aplicar classe 'light' no <html> via JavaScript

---

### PASSO 23 — App Mobile (PWA) ★☆☆☆☆
**Objetivo:** tornar a aplicação instalável no celular como Progressive Web App.

**Arquivos a criar/alterar:**
- `static/manifest.json` → Web App Manifest com nome, ícones, cores
- `static/sw.js` → Service Worker básico para cache offline
- `templates/base.html` → adicionar <link rel="manifest"> e registro do SW
- Criar ícones em múltiplos tamanhos (192x192, 512x512)

---

### ORDEM DE EXECUÇÃO RECOMENDADA

Fase 1 — Fundação analítica (implementar antes de qualquer outra coisa):
  ~~Passo 1~~ ✅ → ~~Passo 2~~ ✅ → Passo 3 → Passo 7 → Passo 9

Fase 2 — Diferencial competitivo (o que vai vender o produto):
  ~~Passo 1~~ ✅ → Passo 6 → Passo 10 → Passo 14 → Passo 17

Fase 3 — Visão de negócio (relatórios e comparativos):
  Passo 4 → Passo 12 → Passo 16

Fase 4 — Refinamentos comportamentais:
  Passo 5 → Passo 8 → Passo 11 → Passo 13 → Passo 15

Fase 5 — Infraestrutura para comercialização:
  Passo 18 → Passo 19 → Passo 20

Fase 6 — Experiência e conveniência:
  Passo 21 → Passo 22 → Passo 23