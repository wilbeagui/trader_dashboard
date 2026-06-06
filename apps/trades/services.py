import io
import pandas as pd
from decimal import Decimal, InvalidOperation
from datetime import datetime 
import pytz
from django.db import transaction
from .models import ImportacaoArquivo, SessaoOperacao, Operacao


def converter_decimal(valor_str):
    """Converte string brasileira para Decimal. Ex: '177.950,00' → 177950.00"""
    if not valor_str or str(valor_str).strip() in ['-', ' - ', '']:
        return Decimal('0')
    try:
        valor_limpo = str(valor_str).strip()
        valor_limpo = valor_limpo.replace('.', '').replace(',', '.')
        return Decimal(valor_limpo)
    except InvalidOperation:
        return Decimal('0')


def converter_datetime(valor_str):
    """Converte string de data/hora para datetime com fuso horário de SP."""
    try:
        fuso_sp = pytz.timezone('America/Sao_Paulo')
        dt = datetime.strptime(str(valor_str).strip(), '%d/%m/%Y %H:%M:%S')
        return fuso_sp.localize(dt)
    except ValueError:
        return None


def converter_bool_medio(valor_str):
    """Converte campo Médio para booleano. 'Sim' → True, 'Não' → False"""
    return str(valor_str).strip().lower() == 'sim'


def converter_tet(valor_str):
    """Trata o campo TET (Tempo Entre Trades). ' - ' → None"""
    valor = str(valor_str).strip()
    if valor in ['-', ' - ', '']:
        return None
    return valor


def importar_csv(arquivo, nome_arquivo):
    """
    Função principal de importação.
    Recebe o arquivo CSV e o nome do arquivo.
    Retorna um dicionário com o resultado da importação.
    """
    try:


        # Lê o conteúdo bruto e decodifica com latin-1
        conteudo = arquivo.read().decode('latin-1')

        # Passa o conteúdo como texto para o Pandas
        df = pd.read_csv(
            io.StringIO(conteudo),
            sep=';',
            skiprows=4,
            header=0,
            dtype=str
        )

        # Remove linhas completamente vazias
        df = df.dropna(how='all')

        # Remove espaços extras nos nomes das colunas
        df.columns = df.columns.str.strip()

        # Verifica se o arquivo tem as colunas esperadas
        colunas_esperadas = ['Ativo', 'Abertura', 'Fechamento']
        for coluna in colunas_esperadas:
            if coluna not in df.columns:
                return {
                    'sucesso': False,
                    'erro': f'Coluna "{coluna}" não encontrada. Verifique se o arquivo é do Profitchart.'
                }

        # Inicia a importação dentro de uma transação
        # Se qualquer coisa falhar, nada é salvo no banco
        with transaction.atomic():

            # Cria o registro de importação
            importacao = ImportacaoArquivo.objects.create(
                arquivo_nome=nome_arquivo,
                total_operacoes=0
            )

            # Identifica os dias presentes no arquivo
            datas_no_arquivo = set()
            for _, row in df.iterrows():
                dt = converter_datetime(row['Abertura'])
                if dt:
                    datas_no_arquivo.add(dt.date())

            # Apaga sessões existentes para os dias encontrados (comportamento: Substituir)
            sessoes_apagadas = SessaoOperacao.objects.filter(
                data_sessao__in=datas_no_arquivo
            )
            dias_substituidos = sessoes_apagadas.count()
            sessoes_apagadas.delete()

            # Processa cada linha do CSV
            total_operacoes = 0
            sessoes_dict = {}  # cache para não buscar no banco a cada linha

            for _, row in df.iterrows():
                abertura = converter_datetime(row['Abertura'])
                fechamento = converter_datetime(row['Fechamento'])

                if not abertura or not fechamento:
                    continue  # pula linhas com datas inválidas

                data_sessao = abertura.date()

                # Cria ou recupera a sessão do dia (usando cache)
                if data_sessao not in sessoes_dict:
                    sessao = SessaoOperacao.objects.create(
                        importacao=importacao,
                        data_sessao=data_sessao,
                        resultado_total=Decimal('0'),
                        total_operacoes=0,
                        total_wins=0,
                        total_losses=0
                    )
                    sessoes_dict[data_sessao] = sessao
                else:
                    sessao = sessoes_dict[data_sessao]

                # Cria a operação
                resultado_op = converter_decimal(row['Res. Operação'])

                Operacao.objects.create(
                    sessao=sessao,
                    importacao=importacao,
                    ativo=str(row['Ativo']).strip(),
                    lado=str(row['Lado']).strip(),
                    houve_preco_medio=converter_bool_medio(row['Médio']),
                    abertura=abertura,
                    fechamento=fechamento,
                    tempo_operacao=str(row['Tempo Operação']).strip(),
                    tempo_entre_trades=converter_tet(row['TET']),
                    qtd_compra=int(row['Qtd Compra']) if str(
                        row['Qtd Compra']).strip().isdigit() else 0,
                    qtd_venda=int(row['Qtd Venda']) if str(
                        row['Qtd Venda']).strip().isdigit() else 0,
                    preco_compra=converter_decimal(row['Preço Compra']),
                    preco_venda=converter_decimal(row['Preço Venda']),
                    preco_mercado=converter_decimal(row['Preço de Mercado']),
                    preco_medio=converter_decimal(
                        row['Médio']) if converter_bool_medio(row['Médio']) else None,
                    mep=converter_decimal(row['MEP']),
                    men=converter_decimal(row['MEN']),
                    resultado_operacao_pontos=converter_decimal(
                        row['Res. Operação (%)']),
                    resultado_operacao=resultado_op,
                    ganho_maximo=converter_decimal(row['Ganho Max.']),
                    perda_maxima=converter_decimal(row['Perda Max.']),
                    total_acumulado=converter_decimal(row['Total'])
                )

                # Atualiza totais da sessão
                sessao.total_operacoes += 1
                sessao.resultado_total += resultado_op
                if resultado_op > 0:
                    sessao.total_wins += 1
                else:
                    sessao.total_losses += 1
                sessao.save()

                total_operacoes += 1

            # Atualiza total de operações na importação
            importacao.total_operacoes = total_operacoes
            importacao.save()

        return {
            'sucesso': True,
            'total_operacoes': total_operacoes,
            'total_sessoes': len(sessoes_dict),
            'dias_substituidos': dias_substituidos,
            'importacao_id': importacao.id
        }

    except Exception as e:
        return {
            'sucesso': False,
            'erro': f'Erro inesperado: {str(e)}'
        }
