from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
from supabase import create_client, Client
import csv
import io
import unicodedata # ADICIONE ESTA LINHA
# Adicione esta linha junto aos outros imports no topo do arquivo
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

# Função para formatar a data no padrão brasileiro para os templates
def format_datetime_filter(value):
    if value is None:
        return ""
    try:
        # Converte a string de data ISO do Supabase para um objeto datetime
        dt_object = datetime.fromisoformat(value)
        # Formata o objeto datetime para o nosso padrão
        return dt_object.strftime('%d/%m/%Y %H:%M')
    except (ValueError, TypeError):
        # Se o valor não for uma data válida, retorna o original sem quebrar a página
        return value

# --- Bloco de Conexão com Supabase ---
SUPABASE_URL = "https://bblwsqlelbrhotnnxxxt.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJibHdzcWxlbGJyaG90bm54eHh0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTMzODQ2ODUsImV4cCI6MjA2ODk2MDY4NX0.dwW0UQdiGD16TDbP-hAYK3CAg1UbboxUKw-fhH3_shA"

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("Conexão com Supabase bem-sucedida!")
except Exception as e:
    print(f"Erro ao conectar com o Supabase: {e}")
    exit()

# --- Inicialização do App Flask ---
app = Flask(__name__)
app.jinja_env.filters['format_datetime'] = format_datetime_filter
app.secret_key = 'PAPADINHAEROIAMASTER'
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['TEMPLATES_AUTO_RELOAD'] = True

# --- FUNÇÕES AJUDANTES ---
def formata_cnpj(cnpj_limpo):
    if len(cnpj_limpo) == 14:
        return f"{cnpj_limpo[:2]}.{cnpj_limpo[2:5]}.{cnpj_limpo[5:8]}/{cnpj_limpo[8:12]}-{cnpj_limpo[12:]}"
    return cnpj_limpo

def convert_utc_to_local(utc_string):
    if not utc_string:
        return ""
    try:
        utc_dt = datetime.fromisoformat(utc_string.replace('Z', '+00:00')).replace(tzinfo=timezone.utc)
        local_tz = ZoneInfo("America/Sao_Paulo")
        local_dt = utc_dt.astimezone(local_tz)
        return local_dt.strftime('%d/%m/%Y %H:%M:%S')
    except (ValueError, TypeError):
        return utc_string

def padronizar_texto(texto):
    """Converte para maiúsculas, remove acentos e espaços extras."""
    if not texto:
        return texto
    # Normaliza para decompor acentos e caracteres
    texto_normalizado = unicodedata.normalize('NFKD', texto)
    # Remove os acentos (caracteres de combinação) e converte para maiúsculas e remove espaços
    return "".join([c for c in texto_normalizado if not unicodedata.combining(c)]).upper().strip()

# --- Processador de Contexto para Funções Globais ---
@app.context_processor
def utility_processor():
    return dict(convert_utc_to_local=convert_utc_to_local)

# --- ROTAS DE AUTENTICAÇÃO ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('pagina_inicial'))

    if request.method == 'POST':
        email = request.form['email']
        senha = request.form['senha']
        
        # CORREÇÃO 1: A consulta agora busca o nome da função na tabela relacionada 'funcoes'
        response = supabase.table('usuarios').select('*, funcoes(nome_funcao)').eq('email', email).single().execute()
        user = response.data
        
        if user and check_password_hash(user['senha'], senha):
            session['user_id'] = user['id']
            session['user_name'] = user['nome']
            
            # CORREÇÃO 2: Acessamos o nome da função da nova forma e o salvamos na sessão
            # Verificamos se a relação 'funcoes' não é nula antes de acessá-la
            if user.get('funcoes'):
                # Adicionamos .lower() para manter o padrão 'gestor' em minúsculo que o resto do sistema espera
                session['user_role'] = user['funcoes']['nome_funcao'].lower()
            else:
                session['user_role'] = 'desconhecido' # Um valor padrão para evitar erros

            return redirect(url_for('pagina_inicial'))
        else:
            flash('E-mail ou senha inválidos.', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Você foi desconectado.', 'info')
    return redirect(url_for('login'))

# --- ROTAS DE GERENCIAMENTO (CADASTROS) ---
@app.route('/usuarios')
def pagina_usuarios():
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor':
        flash('Acesso negado: você não tem permissão para gerenciar usuários.', 'danger')
        return redirect(url_for('pagina_inicial'))
    response = supabase.table('usuarios').select('*').order('id').execute()
    usuarios = response.data
    return render_template('usuarios.html', usuarios=usuarios)

@app.route('/usuarios/adicionar', methods=['POST'])
def adicionar_usuario():
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor': return redirect(url_for('pagina_inicial'))
    email = request.form['email']
    response_check = supabase.table('usuarios').select('id').eq('email', email).execute()
    if response_check.data:
        flash('Erro: O e-mail informado já está cadastrado.', 'danger')
        return redirect(url_for('pagina_usuarios'))
    
    dados_novo_usuario = {
    'nome': padronizar_texto(request.form['nome']),
    'email': request.form['email'].strip(),
    'senha': generate_password_hash(request.form['senha']), # <-- CORRIGIDO E SEGURO
    'role': request.form['role']
}
    supabase.table('usuarios').insert(dados_novo_usuario).execute()
    flash('Novo usuário cadastrado com sucesso!', 'success')
    return redirect(url_for('pagina_usuarios'))

@app.route('/usuario/editar/<int:usuario_id>')
def pagina_editar_usuario(usuario_id):
    # if 'user_id' not in session: return redirect(url_for('login'))
    # if session.get('user_role') != 'gestor': return redirect(url_for('pagina_inicial'))
    response = supabase.table('usuarios').select('*').eq('id', usuario_id).single().execute()
    usuario = response.data
    return render_template('editar_usuario.html', usuario=usuario)

@app.route('/usuario/salvar_edicao', methods=['POST'])
def salvar_edicao_usuario():
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor': return redirect(url_for('pagina_inicial'))
    usuario_id = request.form['usuario_id']
    dados = { 
        'nome': padronizar_texto(request.form['nome']), # PADRONIZADO
        'email': request.form['email'].strip(),
        'role': request.form['role'] 
    }
    supabase.table('usuarios').update(dados).eq('id', usuario_id).execute()
    flash('Usuário atualizado com sucesso!', 'success')
    return redirect(url_for('pagina_usuarios'))

@app.route('/usuario/excluir/<int:usuario_id>')
def excluir_usuario(usuario_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor': return redirect(url_for('pagina_inicial'))
    if session['user_id'] == usuario_id:
        flash('Ação inválida: você não pode excluir sua própria conta.', 'danger')
        return redirect(url_for('pagina_usuarios'))
    supabase.table('usuarios').delete().eq('id', usuario_id).execute()
    flash('Usuário excluído com sucesso.', 'success')
    return redirect(url_for('pagina_usuarios'))

@app.route('/fornecedores')
def pagina_fornecedores():
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') not in ['gestor', 'almoxarife']:
        flash('Acesso negado.', 'danger')
        return redirect(url_for('pagina_inicial'))
    response = supabase.table('fornecedores').select('*').order('id').execute()
    fornecedores = response.data
    for fornecedor in fornecedores:
        if fornecedor.get('cnpj'): fornecedor['cnpj'] = formata_cnpj(fornecedor['cnpj'])
    return render_template('fornecedores.html', fornecedores=fornecedores)

@app.route('/fornecedores/adicionar', methods=['POST'])
def adicionar_fornecedor():
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') not in ['gestor', 'almoxarife']: return redirect(url_for('pagina_inicial'))
    
    cnpj_limpo = ''.join(filter(str.isdigit, request.form['cnpj']))
    if len(cnpj_limpo) != 14:
        flash('Erro: O CNPJ deve conter 14 dígitos.', 'danger')
        return redirect(url_for('pagina_fornecedores'))

    response_check = supabase.table('fornecedores').select('id').eq('cnpj', cnpj_limpo).execute()
    if response_check.data:
        flash('Erro: O CNPJ informado já está cadastrado.', 'danger')
        return redirect(url_for('pagina_fornecedores'))

    dados_novo_fornecedor = { 
        'razao_social': padronizar_texto(request.form['razao_social']),
        'cnpj': cnpj_limpo 
    }
    supabase.table('fornecedores').insert(dados_novo_fornecedor).execute()
    flash('Novo fornecedor cadastrado com sucesso!', 'success')
    return redirect(url_for('pagina_fornecedores'))

@app.route('/fornecedor/editar/<int:fornecedor_id>')
def pagina_editar_fornecedor(fornecedor_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor': return redirect(url_for('pagina_inicial'))
    response = supabase.table('fornecedores').select('*').eq('id', fornecedor_id).single().execute()
    fornecedor = response.data
    if fornecedor and fornecedor.get('cnpj'): fornecedor['cnpj'] = formata_cnpj(fornecedor['cnpj'])
    return render_template('editar_fornecedor.html', fornecedor=fornecedor)

@app.route('/fornecedor/salvar_edicao', methods=['POST'])
def salvar_edicao_fornecedor():
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor': return redirect(url_for('pagina_inicial'))
    fornecedor_id = request.form['fornecedor_id']
    cnpj_limpo = ''.join(filter(str.isdigit, request.form['cnpj']))

    # VALIDAÇÃO DE TAMANHO DO CNPJ
    if len(cnpj_limpo) != 14:
        flash('Erro: O CNPJ deve conter 14 dígitos.', 'danger')
        return redirect(url_for('pagina_editar_fornecedor', fornecedor_id=fornecedor_id))

    dados = { 
        'razao_social': padronizar_texto(request.form['razao_social']), # PADRONIZADO
        'cnpj': cnpj_limpo 
    }
    supabase.table('fornecedores').update(dados).eq('id', fornecedor_id).execute()
    flash('Fornecedor atualizado com sucesso!', 'success')
    return redirect(url_for('pagina_fornecedores'))

@app.route('/fornecedor/excluir/<int:fornecedor_id>')
def excluir_fornecedor(fornecedor_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor': return redirect(url_for('pagina_inicial'))
    supabase.table('fornecedores').delete().eq('id', fornecedor_id).execute()
    flash('Fornecedor excluído com sucesso!', 'success')
    return redirect(url_for('pagina_fornecedores'))

@app.route('/categorias')
def pagina_categorias():
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor':
        flash('Acesso negado.', 'danger')
        return redirect(url_for('pagina_inicial'))
    response = supabase.table('categorias').select('*').order('id').execute()
    categorias = response.data
    return render_template('categorias.html', categorias=categorias)

@app.route('/categorias/adicionar', methods=['POST'])
def adicionar_categoria():
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor': return redirect(url_for('pagina_inicial'))
    
    nome_categoria = padronizar_texto(request.form['nome_categoria']) # PADRONIZADO

    response_check = supabase.table('categorias').select('id').eq('nome_categoria', nome_categoria).execute()
    if response_check.data:
        flash('Erro: Esta categoria já está cadastrada.', 'danger')
        return redirect(url_for('pagina_categorias'))
    dados_nova_categoria = { 'nome_categoria': nome_categoria }
    supabase.table('categorias').insert(dados_nova_categoria).execute()
    flash('Nova categoria cadastrada com sucesso!', 'success')
    return redirect(url_for('pagina_categorias'))

@app.route('/categoria/editar/<int:categoria_id>')
def pagina_editar_categoria(categoria_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor': return redirect(url_for('pagina_inicial'))
    response = supabase.table('categorias').select('*').eq('id', categoria_id).single().execute()
    categoria = response.data
    return render_template('editar_categoria.html', categoria=categoria)

@app.route('/categoria/salvar_edicao', methods=['POST'])
def salvar_edicao_categoria():
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor': return redirect(url_for('pagina_inicial'))
    categoria_id = request.form['categoria_id']
    dados = { 
        'nome_categoria': padronizar_texto(request.form['nome_categoria']) # PADRONIZADO
    }
    supabase.table('categorias').update(dados).eq('id', categoria_id).execute()
    flash('Categoria atualizada com sucesso!', 'success')
    return redirect(url_for('pagina_categorias'))

@app.route('/categoria/excluir/<int:categoria_id>')
def excluir_categoria(categoria_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor': return redirect(url_for('pagina_inicial'))
    supabase.table('categorias').delete().eq('id', categoria_id).execute()
    flash('Categoria excluída com sucesso!', 'success')
    return redirect(url_for('pagina_categorias'))

@app.route('/unidades')
def pagina_unidades_medida():
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor':
        flash('Acesso negado.', 'danger')
        return redirect(url_for('pagina_inicial'))
    
    response = supabase.table('unidades_medida').select('*').order('nome_unidade').execute()
    unidades = response.data
    return render_template('unidades_medida.html', unidades=unidades)

@app.route('/unidades/adicionar', methods=['POST'])
def adicionar_unidade_medida():
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor': return redirect(url_for('pagina_inicial'))

    nome_unidade = padronizar_texto(request.form['nome_unidade'])
    sigla = padronizar_texto(request.form['sigla'])

    # --- NOVA VALIDAÇÃO DE TAMANHO ---
    if len(sigla) > 2:
        flash('Erro: A sigla deve ter no máximo 2 caracteres.', 'danger')
        return redirect(url_for('pagina_unidades_medida'))
    # --- FIM DA VALIDAÇÃO ---

    response_check = supabase.table('unidades_medida').select('id', count='exact').or_(f'nome_unidade.eq.{nome_unidade},sigla.eq.{sigla}').execute()
    
    if response_check.count > 0:
        flash('Erro: O nome da unidade ou a sigla já existem no sistema.', 'danger')
        return redirect(url_for('pagina_unidades_medida'))
    
    dados = {'nome_unidade': nome_unidade, 'sigla': sigla}
    try:
        supabase.table('unidades_medida').insert(dados).execute()
        flash('Unidade de medida cadastrada com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao cadastrar unidade: {e}', 'danger')
    
    return redirect(url_for('pagina_unidades_medida'))

# --- ROTAS DA APLICAÇÃO PRINCIPAL ---
@app.route('/')
def pagina_inicial():
    if 'user_id' not in session: return redirect(url_for('login'))

    today = datetime.now(ZoneInfo("America/Sao_Paulo"))
    data_inicio_default = (today - timedelta(days=30)).strftime('%Y-%m-%d')
    data_fim_default = today.strftime('%Y-%m-%d')
    
    filtros = {
        'data_inicio': request.args.get('data_inicio', data_inicio_default),
        'data_fim': request.args.get('data_fim', data_fim_default),
        'categorias': request.args.getlist('categorias')
    }

    kpis = { "valor_total_estoque": 0, "itens_estoque_baixo": 0, "top_alto_giro": [], "top_baixo_giro": [], 'alto_giro_count': 0, 'baixo_giro_count': 0, "ultimas_entradas": [], "ultimas_saidas": [] }

    try:
        query_produtos = supabase.table('produtos').select('id, descricao, valor_total_estoque, categoria_id, estoque_atual, estoque_minimo')
        if filtros['categorias']:
            cat_ids = [int(c) for c in filtros['categorias']]
            query_produtos = query_produtos.in_('categoria_id', cat_ids)
        produtos_filtrados = query_produtos.execute().data
        ids_produtos = [p['id'] for p in produtos_filtrados]

        kpis['valor_total_estoque'] = sum(p['valor_total_estoque'] for p in produtos_filtrados)
        kpis['itens_estoque_baixo'] = len([p for p in produtos_filtrados if p['estoque_minimo'] > 0 and p['estoque_atual'] <= p['estoque_minimo']])

        if ids_produtos:
            movimentacoes_periodo = supabase.table('movimentacoes').select('produto_id, tipo, quantidade').in_('produto_id', ids_produtos).gte('data', f"{filtros['data_inicio']} 00:00:00").lte('data', f"{filtros['data_fim']} 23:59:59").execute().data
            
            giro_map = {p['id']: {'entradas': 0, 'saidas': 0, 'descricao': p['descricao']} for p in produtos_filtrados}
            for mov in movimentacoes_periodo:
                p_id = mov['produto_id']
                if p_id in giro_map:
                    if mov['tipo'] == 'entrada': giro_map[p_id]['entradas'] += mov['quantidade']
                    else: giro_map[p_id]['saidas'] += mov['quantidade']
            
            lista_giro = []
            for p_id, dados in giro_map.items():
                if dados['entradas'] > 0:
                    dados['giro'] = dados['saidas'] / dados['entradas']
                    lista_giro.append(dados)
            
            lista_giro.sort(key=lambda x: x['giro'], reverse=True)
            kpis['top_alto_giro'] = lista_giro[:5]
            kpis['top_baixo_giro'] = sorted([p for p in lista_giro if p['giro'] < 1 and p['saidas'] > 0], key=lambda x: x['giro'])[:5]
            kpis['alto_giro_count'] = len([p for p in lista_giro if p['giro'] >= 1])
            kpis['baixo_giro_count'] = len(kpis['top_baixo_giro'])

        query_entradas = supabase.table('movimentacoes').select('*, produtos!inner(descricao, categoria_id)').eq('tipo', 'entrada').gte('data', f"{filtros['data_inicio']} 00:00:00").lte('data', f"{filtros['data_fim']} 23:59:59")
        if filtros['categorias']: query_entradas = query_entradas.in_('produtos.categoria_id', cat_ids)
        ultimas_entradas = query_entradas.order('data', desc=True).limit(5).execute().data
        for mov in ultimas_entradas: mov['data_local'] = convert_utc_to_local(mov['data'])
        kpis['ultimas_entradas'] = ultimas_entradas

        query_saidas = supabase.table('movimentacoes').select('*, produtos!inner(descricao, categoria_id)').eq('tipo', 'saida').gte('data', f"{filtros['data_inicio']} 00:00:00").lte('data', f"{filtros['data_fim']} 23:59:59")
        if filtros['categorias']: query_saidas = query_saidas.in_('produtos.categoria_id', cat_ids)
        ultimas_saidas = query_saidas.order('data', desc=True).limit(5).execute().data
        for mov in ultimas_saidas: mov['data_local'] = convert_utc_to_local(mov['data'])
        kpis['ultimas_saidas'] = ultimas_saidas

    except Exception as e:
        flash(f'Erro ao calcular KPIs: {e}', 'danger')

    todas_categorias = supabase.table('categorias').select('id, nome_categoria').order('nome_categoria').execute().data
    
    return render_template('index.html', kpis=kpis, filtros=filtros, todas_categorias=todas_categorias)


@app.route('/estoque')
def pagina_estoque():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    # Busca de dados principais
    response_produtos = supabase.table('produtos').select('*, categorias(nome_categoria)').order('id').execute()
    produtos_data = response_produtos.data
    
    # Loop para calcular custo médio e valor total para cada produto
    for produto in produtos_data:
        quantidade_com_custo = float(produto.get('quantidade_com_custo') or 0)
        valor_total_estoque = float(produto.get('valor_total_estoque') or 0)
        
        if quantidade_com_custo > 0:
            produto['custo_medio'] = valor_total_estoque / quantidade_com_custo
        else:
            produto['custo_medio'] = 0
            
        produto['valor_total_calculado'] = produto['custo_medio'] * float(produto.get('estoque_atual') or 0)

    # Buscas para os formulários da página
    response_categorias = supabase.table('categorias').select('*').execute()
    categorias = response_categorias.data
    response_unidades = supabase.table('unidades_medida').select('*').execute()
    unidades_medida = response_unidades.data
    
    return render_template('estoque.html', produtos=produtos_data, categorias=categorias, unidades_medida=unidades_medida)

@app.route('/adicionar', methods=['POST'])
@app.route('/produtos/adicionar', methods=['POST'])
def adicionar_produto():
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor': return redirect(url_for('pagina_estoque'))

    try:
        dados_novo_produto = {
            'descricao': padronizar_texto(request.form['descricao']),
            'categoria_id': int(request.form['categoria_id']),
            'codigo_sustentare': request.form.get('codigo_sustentare', '0'),
            'codigo_valor': request.form.get('codigo_valor', '0'),
            'unidade_medida_id': int(request.form['unidade_medida_id']),
            'estoque_atual': 0,
            'estoque_minimo': 0,
            'valor_total_estoque': 0,
            'quantidade_com_custo': 0
        }
        supabase.table('produtos').insert(dados_novo_produto).execute()
        flash('Produto cadastrado com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao cadastrar produto: {e}', 'danger')

    return redirect(url_for('pagina_estoque'))

@app.route('/movimentacao/<int:produto_id>/<tipo>')
def pagina_movimentacao(produto_id, tipo):
    if 'user_id' not in session: return redirect(url_for('login'))

    # Busca o produto específico para exibir o nome na tela
    response_produto = supabase.table('produtos').select('*').eq('id', produto_id).single().execute()
    produto = response_produto.data
    
    # Busca as listas necessárias para os dropdowns dos formulários
    fornecedores = supabase.table('fornecedores').select('*').execute().data
    colaboradores = supabase.table('colaboradores').select('*').execute().data
    equipamentos = supabase.table('equipamentos').select('*').execute().data

    return render_template('movimentacao.html', produto=produto, tipo=tipo, fornecedores=fornecedores, colaboradores=colaboradores, equipamentos=equipamentos)

@app.route('/registrar_movimentacao', methods=['POST'])
def registrar_movimentacao():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    # --- 1. Captura de Dados Comuns do Formulário ---
    tipo = request.form['tipo']
    produto_id = int(request.form['produto_id'])
    quantidade_movimentada = float(request.form.get('quantidade', 0))

    if quantidade_movimentada <= 0:
        flash('Erro: A quantidade da movimentação deve ser maior que zero.', 'danger')
        return redirect(url_for('pagina_movimentacao', produto_id=produto_id, tipo=tipo))
    
    # --- 2. Busca os dados atuais do produto ---
    try:
        response_produto = supabase.table('produtos').select('estoque_atual, valor_total_estoque, quantidade_com_custo').eq('id', produto_id).limit(1).single().execute()
        produto_atual = response_produto.data
        if not produto_atual:
            flash(f'Erro: Produto com ID {produto_id} não encontrado.', 'danger')
            return redirect(url_for('pagina_estoque'))
    except Exception as e:
        flash(f'Erro ao buscar dados do produto: {e}', 'danger')
        return redirect(url_for('pagina_estoque'))

    estoque_antigo = float(produto_atual.get('estoque_atual', 0))
    valor_total_antigo = float(produto_atual.get('valor_total_estoque', 0))
    quantidade_com_custo_antiga = float(produto_atual.get('quantidade_com_custo', 0))

    dados_movimentacao = { 'produto_id': produto_id, 'tipo': tipo, 'quantidade': quantidade_movimentada, 'usuario_id': session['user_id'] }
    dados_produto_update = {}

    # --- 3. Lógica para ENTRADA ---
    if tipo == 'entrada':
        # Captura os dados específicos da entrada
        custo_unitario_entrada = float(request.form.get('custo_unitario', 0))
        numero_requisicao_alvo = request.form.get('numero_requisicao_alvo', '').strip().upper()

        if custo_unitario_entrada < 0:
            flash('Erro: O custo unitário não pode ser um valor negativo.', 'danger')
            return redirect(url_for('pagina_movimentacao', produto_id=produto_id, tipo=tipo))

        # Prepara os dados da movimentação de entrada com os novos campos
        dados_movimentacao['preco_unitario'] = custo_unitario_entrada
        dados_movimentacao['fornecedor_id'] = int(request.form['fornecedor_id'])
        dados_movimentacao['numero_requisicao_alvo'] = numero_requisicao_alvo
        dados_movimentacao['tipo_documento'] = request.form.get('tipo_documento')
        dados_movimentacao['numero_documento'] = request.form.get('numero_documento', '0')
        
        # Calcula os novos totais do produto
        novo_estoque = estoque_antigo + quantidade_movimentada
        novo_valor_total = valor_total_antigo
        nova_quantidade_com_custo = quantidade_com_custo_antiga
        if custo_unitario_entrada > 0:
            novo_valor_total += quantidade_movimentada * custo_unitario_entrada
            nova_quantidade_com_custo += quantidade_movimentada
        dados_produto_update = { 'estoque_atual': novo_estoque, 'valor_total_estoque': novo_valor_total, 'quantidade_com_custo': nova_quantidade_com_custo }
        
        # Salva a movimentação e atualiza o produto
        supabase.table('movimentacoes').insert(dados_movimentacao).execute()
        supabase.table('produtos').update(dados_produto_update).eq('id', produto_id).execute()

       # === INÍCIO DA LÓGICA DE BAIXA AUTOMÁTICA (VERSÃO ROBUSTA) ===
    # === INÍCIO DA LÓGICA DE BAIXA EM CASCATA (VERSÃO AVANÇADA) ===
    if numero_requisicao_alvo:
        try:
            # 1. Busca TODOS os usos pendentes para este alvo/produto, em ordem do mais antigo para o mais novo
            usos_pendentes_response = supabase.table('uso_temporario').select('*').eq('numero_requisicao_alvo', numero_requisicao_alvo).eq('produto_id', produto_id).in_('status', ['Pendente', 'Baixado Parcialmente']).order('id').execute()
            usos_pendentes = usos_pendentes_response.data
            
            saldo_entrada = quantidade_movimentada # Nosso "crédito" para abater as pendências
            
            # 2. Faz um loop por cada pendência encontrada
            for uso in usos_pendentes:
                if saldo_entrada <= 0:
                    break # Se o crédito acabou, paramos o loop

                quantidade_pendente = float(uso['quantidade_usada'])
                dados_atualizacao_uso = {}

                if saldo_entrada >= quantidade_pendente:
                    # O crédito é suficiente para quitar esta pendência inteira
                    dados_atualizacao_uso['status'] = 'Baixado'
                    dados_atualizacao_uso['quantidade_usada'] = 0
                    saldo_entrada -= quantidade_pendente # Subtrai o que foi usado do nosso crédito
                    flash(f'Uso temporário ID {uso["id"]} ({quantidade_pendente} un.) baixado integralmente.', 'info')
                else:
                    # O crédito só quita parte desta pendência
                    nova_quantidade_pendente = quantidade_pendente - saldo_entrada
                    dados_atualizacao_uso['status'] = 'Baixado Parcialmente'
                    dados_atualizacao_uso['quantidade_usada'] = nova_quantidade_pendente
                    saldo_entrada = 0 # O crédito foi todo utilizado
                    flash(f'Uso temporário ID {uso["id"]} baixado parcialmente. Restam {nova_quantidade_pendente} un. pendentes.', 'info')
                
                # Atualiza o registro no banco de dados
                supabase.table('uso_temporario').update(dados_atualizacao_uso).eq('id', uso['id']).execute()

        except Exception as e:
            print(f"DEBUG: Não foi possível realizar a baixa automática para o ALVO {numero_requisicao_alvo}. Erro: {e}")
    # === FIM DA LÓGICA DE BAIXA EM CASCATA ===
        
        flash('Entrada registrada com sucesso!', 'success')

    # --- 4. Lógica para SAÍDA ---
    else: # Saída
        if estoque_antigo < quantidade_movimentada:
            flash(f'Erro: Quantidade de saída ({quantidade_movimentada}) é maior que o estoque atual ({estoque_antigo}).', 'danger')
            return redirect(url_for('pagina_movimentacao', produto_id=produto_id, tipo=tipo))

        # Prepara os dados da movimentação de saída com os novos campos
        custo_medio_atual = valor_total_antigo / quantidade_com_custo_antiga if quantidade_com_custo_antiga > 0 else 0
        dados_movimentacao['custo_unitario'] = custo_medio_atual # Salva o custo médio no momento da saída
        dados_movimentacao['colaborador_id'] = request.form.get('colaborador_id')
        dados_movimentacao['equipamento_id'] = request.form.get('equipamento_id')
        dados_movimentacao['numero_requisicao_manual'] = request.form.get('numero_requisicao_manual')

        # Calcula os novos totais do produto
        novo_estoque = estoque_antigo - quantidade_movimentada
        novo_valor_total = valor_total_antigo - (quantidade_movimentada * custo_medio_atual)
        nova_quantidade_com_custo = quantidade_com_custo_antiga # Na saída, a quantidade base do custo médio não muda
        
        dados_produto_update = { 'estoque_atual': max(0, novo_estoque), 'valor_total_estoque': max(0, novo_valor_total), 'quantidade_com_custo': nova_quantidade_com_custo }

        # Salva a movimentação e atualiza o produto
        supabase.table('movimentacoes').insert(dados_movimentacao).execute()
        supabase.table('produtos').update(dados_produto_update).eq('id', produto_id).execute()

        flash('Saída registrada com sucesso!', 'success')
    
    return redirect(url_for('pagina_estoque'))

@app.route('/produtos/editar/<int:produto_id>')
def pagina_editar_produto(produto_id):
    # --- MARCADOR DE DEPURAÇÃO 1 ---
    print("\n--- EXECUTANDO A NOVA VERSÃO DA FUNÇÃO 'pagina_editar_produto' (COM PRINTS) ---")

    if 'user_id' not in session: return redirect(url_for('login'))

    try:
        # --- MARCADOR DE DEPURAÇÃO 2 ---
        print(f"--- PASSO 2: Buscando produto com ID: {produto_id}")
        response_produto = supabase.table('produtos').select('*').eq('id', produto_id).single().execute()
        produto = response_produto.data
        
        if not produto:
            flash('Produto não encontrado.', 'danger')
            return redirect(url_for('pagina_estoque'))

        # --- MARCADOR DE DEPURAÇÃO 3 ---
        print("--- PASSO 3: Buscando a lista de categorias...")
        response_categorias = supabase.table('categorias').select('*').execute()
        categorias = response_categorias.data
        
        # --- MARCADOR DE DEPURAÇÃO 4 ---
        print("--- PASSO 4: Buscando a lista de unidades_medida (o nome correto)...")
        response_unidades = supabase.table('unidades_medida').select('*').execute()
        unidades_medida = response_unidades.data
        
        # --- MARCADOR DE DEPURAÇÃO 5 ---
        print("--- PASSO 5: Todos os dados foram buscados com sucesso. Renderizando o template...")
        return render_template('editar_produto.html', produto=produto, categorias=categorias, unidades_medida=unidades_medida)
    
    except Exception as e:
        # --- MARCADOR DE DEPURAÇÃO 6 ---
        print(f"\n!!! ERRO CAPTURADO DENTRO DA FUNÇÃO NOVA: {e} !!!\n")
        flash(f'Erro ao carregar dados do produto: {e}', 'danger')
        return redirect(url_for('pagina_estoque'))
    
@app.route('/produtos/editar', methods=['POST'])
def editar_produto():
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor': return redirect(url_for('pagina_estoque'))

    # Lógica de receber dados do formulário e salvar
    try:
        produto_id = request.form['produto_id']
        dados_atualizados = {
            'descricao': padronizar_texto(request.form['descricao']),
            'categoria_id': int(request.form['categoria_id']),
            'codigo_sustentare': request.form.get('codigo_sustentare', '0'),
            'codigo_valor': request.form.get('codigo_valor', '0'),
            'unidade_medida_id': int(request.form['unidade_medida_id'])
        }
        supabase.table('produtos').update(dados_atualizados).eq('id', produto_id).execute()
        flash('Produto atualizado com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao atualizar produto: {e}', 'danger')

    return redirect(url_for('pagina_estoque'))
    
    try:
        # Para evitar erros de chave estrangeira, excluímos primeiro os registros dependentes
        supabase.table('movimentacoes').delete().eq('produto_id', produto_id).execute()
        supabase.table('inventario_itens').delete().eq('produto_id', produto_id).execute()
        supabase.table('uso_temporario').delete().eq('produto_id', produto_id).execute()
        
        # Agora podemos excluir o produto principal
        supabase.table('produtos').delete().eq('id', produto_id).execute()
        flash('Produto e todo o seu histórico foram excluídos com sucesso!', 'warning')
    except Exception as e:
        flash(f'Erro ao excluir produto: {e}', 'danger')

    return redirect(url_for('pagina_estoque'))

@app.route('/produto/salvar_edicao', methods=['POST'])
def salvar_edicao_produto():
    if 'user_id' not in session: return redirect(url_for('login'))
    produto_id = request.form['produto_id']
    dados_para_atualizar = { 'codigo_sustentare': request.form['codigo_sustentare'], 'descricao': request.form['descricao'], 'unidade_medida': request.form['unidade_medida'], 'estoque_minimo': request.form['estoque_minimo'], 'categoria_id': request.form['categoria_id'] }
    supabase.table('produtos').update(dados_para_atualizar).eq('id', produto_id).execute()
    flash('Produto atualizado com sucesso!', 'success')
    return redirect(url_for('pagina_estoque'))

@app.route('/produto/excluir/<int:produto_id>')
def excluir_produto(produto_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    try:
        supabase.table('produtos').delete().eq('id', produto_id).execute()
        flash('Produto excluído com sucesso!', 'danger')
    except Exception as e:
        flash(f'Erro ao excluir produto: {e}', 'danger')
    return redirect(url_for('pagina_estoque'))

# --- ROTAS DE RELATÓRIOS ---
@app.route('/relatorios/historico')
def pagina_relatorio_historico():
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor':
        flash('Acesso negado.', 'danger')
        return redirect(url_for('pagina_inicial'))
    filtros = { 'data_inicio': request.args.get('data_inicio', ''), 'data_fim': request.args.get('data_fim', ''), 'tipo': request.args.get('tipo', 'todos'), 'usuario_id': request.args.get('usuario_id', 'todos'), 'produtos': request.args.getlist('produtos'), 'fornecedores': request.args.getlist('fornecedores') }
    query = supabase.table('movimentacoes').select('*, produtos(descricao), usuarios(nome), fornecedores(razao_social)').order('data', desc=True)
    if filtros['data_inicio']: query = query.gte('data', f"{filtros['data_inicio']} 00:00:00")
    if filtros['data_fim']: query = query.lte('data', f"{filtros['data_fim']} 23:59:59")
    if filtros['tipo'] != 'todos': query = query.eq('tipo', filtros['tipo'])
    if filtros['usuario_id'] != 'todos': query = query.eq('usuario_id', filtros['usuario_id'])
    if filtros['produtos']: query = query.in_('produto_id', filtros['produtos'])
    if filtros['fornecedores']: query = query.in_('fornecedor_id', filtros['fornecedores'])
    response = query.execute()
    movimentacoes = response.data
    for mov in movimentacoes:
        mov['data_local'] = convert_utc_to_local(mov['data'])
    todos_produtos = supabase.table('produtos').select('id, descricao').execute().data
    todos_usuarios = supabase.table('usuarios').select('id, nome').execute().data
    todos_fornecedores = supabase.table('fornecedores').select('id, razao_social').execute().data
    return render_template('historico_lancamentos.html', movimentacoes=movimentacoes, filtros=filtros, todos_produtos=todos_produtos, todos_usuarios=todos_usuarios, todos_fornecedores=todos_fornecedores)

@app.route('/relatorios/historico/exportar')
def exportar_historico_csv():
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor': return redirect(url_for('pagina_inicial'))
    filtros = { 'data_inicio': request.args.get('data_inicio', ''), 'data_fim': request.args.get('data_fim', ''), 'tipo': request.args.get('tipo', 'todos'), 'usuario_id': request.args.get('usuario_id', 'todos'), 'produtos': request.args.getlist('produtos'), 'fornecedores': request.args.getlist('fornecedores') }
    query = supabase.table('movimentacoes').select('*, produtos(descricao), usuarios(nome), fornecedores(razao_social)').order('data', desc=True)
    if filtros['data_inicio']: query = query.gte('data', f"{filtros['data_inicio']} 00:00:00")
    if filtros['data_fim']: query = query.lte('data', f"{filtros['data_fim']} 23:59:59")
    if filtros['tipo'] != 'todos': query = query.eq('tipo', filtros['tipo'])
    if filtros['usuario_id'] != 'todos': query = query.eq('usuario_id', filtros['usuario_id'])
    if filtros['produtos']: query = query.in_('produto_id', filtros['produtos'])
    if filtros['fornecedores']: query = query.in_('fornecedor_id', filtros['fornecedores'])
    movimentacoes = query.execute().data
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['Data', 'Produto', 'Tipo', 'Quantidade', 'Custo Unitario', 'Valor Total', 'Usuario', 'Fornecedor/Requisitante', 'Cod. Requisicao'])
    for mov in movimentacoes:
        data_local = convert_utc_to_local(mov.get('data'))
        valor_total = (mov.get('quantidade', 0) * mov.get('custo_unitario', 0)) if mov.get('custo_unitario') else 0
        produto_desc = mov.get('produtos', {}).get('descricao', 'N/A') if mov.get('produtos') is not None else 'N/A'
        usuario_nome = mov.get('usuarios', {}).get('nome', 'N/A') if mov.get('usuarios') is not None else 'N/A'
        fornecedor_dict = mov.get('fornecedores')
        if fornecedor_dict:
            fornecedor_req = fornecedor_dict.get('razao_social', 'N/A')
        else:
            fornecedor_req = mov.get('requisitante_nome', '')
        writer.writerow([ data_local, produto_desc, mov.get('tipo', ''), mov.get('quantidade', ''), str(mov.get('custo_unitario', '')).replace('.',','), str(valor_total).replace('.',','), usuario_nome, fornecedor_req, mov.get('codigo_requisicao_compra', '') ])
    output.seek(0)
    return Response(output.getvalue().encode('utf-8-sig'), mimetype="text/csv", headers={"Content-Disposition":f"attachment;filename=historico_lancamentos_{datetime.now().strftime('%Y%m%d')}.csv"})

@app.route('/relatorios/posicao_estoque')
def pagina_posicao_estoque():
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') not in ['gestor', 'almoxarife']:
        flash('Acesso negado.', 'danger')
        return redirect(url_for('pagina_inicial'))
    filtros = { 'data_inicio': request.args.get('data_inicio'), 'data_fim': request.args.get('data_fim'), 'ordenar_por': request.args.get('ordenar_por', 'descricao'), 'produtos': request.args.getlist('produtos'), 'categorias': request.args.getlist('categorias') }
    dados_relatorio = []
    totais = {}
    if filtros['data_inicio'] and filtros['data_fim']:
        query_produtos = supabase.table('produtos').select('id, descricao, codigo_sustentare, categoria_id')
        if filtros['produtos']:
            query_produtos = query_produtos.in_('id', [int(p) for p in filtros['produtos']])
        if filtros['categorias']:
            query_produtos = query_produtos.in_('categoria_id', [int(c) for c in filtros['categorias']])
        produtos_a_analisar = query_produtos.execute().data
        ids_produtos = [p['id'] for p in produtos_a_analisar]
        if ids_produtos:
            todas_movimentacoes = supabase.table('movimentacoes').select('produto_id, tipo, quantidade, custo_unitario, data').in_('produto_id', ids_produtos).lte('data', f"{filtros['data_fim']} 23:59:59").execute().data
            produtos_map = {p['id']: p for p in produtos_a_analisar}
            relatorio_map = { p_id: {'id': p_id, 'descricao': produtos_map[p_id]['descricao'], 'codigo_sustentare': produtos_map[p_id]['codigo_sustentare'], 'qtd_inicial': 0, 'valor_inicial': 0, 'qtd_entradas': 0, 'valor_entradas': 0, 'qtd_saidas': 0, 'valor_saidas': 0, 'qtd_final': 0, 'valor_final': 0} for p_id in ids_produtos }
            data_inicio_dt = datetime.fromisoformat(f"{filtros['data_inicio']}T00:00:00+00:00").replace(tzinfo=timezone.utc)
            for mov in todas_movimentacoes:
                p_id = mov['produto_id']
                if p_id in relatorio_map:
                    item = relatorio_map[p_id]
                    mov_data = datetime.fromisoformat(mov['data'].replace('Z', '+00:00')).replace(tzinfo=timezone.utc)
                    if mov_data < data_inicio_dt:
                        if mov['tipo'] == 'entrada':
                            item['qtd_inicial'] += mov['quantidade']
                            if mov.get('custo_unitario', 0) > 0: item['valor_inicial'] += mov['quantidade'] * mov['custo_unitario']
                        else:
                            item['qtd_inicial'] -= mov['quantidade']
                    else:
                        if mov['tipo'] == 'entrada':
                            item['qtd_entradas'] += mov['quantidade']
                            if mov.get('custo_unitario', 0) > 0: item['valor_entradas'] += mov['quantidade'] * mov['custo_unitario']
                        else:
                            item['qtd_saidas'] += mov['quantidade']
            for p_id in ids_produtos:
                item = relatorio_map[p_id]
                item['qtd_final'] = item['qtd_inicial'] + item['qtd_entradas'] - item['qtd_saidas']
                custo_medio_inicial = item['valor_inicial'] / item['qtd_inicial'] if item['qtd_inicial'] > 0 else 0
                item['valor_saidas'] = item['qtd_saidas'] * custo_medio_inicial
                item['valor_final'] = item['valor_inicial'] + item['valor_entradas'] - item['valor_saidas']
                dados_relatorio.append(item)
            if filtros['ordenar_por'] == 'codigo_sustentare':
                dados_relatorio.sort(key=lambda x: x['codigo_sustentare'])
            elif filtros['ordenar_por'] == 'estoque_final':
                dados_relatorio.sort(key=lambda x: x['qtd_final'], reverse=True)
            else:
                dados_relatorio.sort(key=lambda x: x['descricao'])
            totais = { 'qtd_inicial': sum(item['qtd_inicial'] for item in dados_relatorio), 'valor_inicial': sum(item['valor_inicial'] for item in dados_relatorio), 'qtd_entradas': sum(item['qtd_entradas'] for item in dados_relatorio), 'valor_entradas': sum(item['valor_entradas'] for item in dados_relatorio), 'qtd_saidas': sum(item['qtd_saidas'] for item in dados_relatorio), 'valor_saidas': sum(item.get('valor_saidas', 0) for item in dados_relatorio), 'qtd_final': sum(item['qtd_final'] for item in dados_relatorio), 'valor_final': sum(item['valor_final'] for item in dados_relatorio) }
    todos_produtos = supabase.table('produtos').select('id, descricao').order('descricao').execute().data
    todas_categorias = supabase.table('categorias').select('id, nome_categoria').order('nome_categoria').execute().data
    return render_template('posicao_estoque.html', filtros=filtros, dados_relatorio=dados_relatorio, totais=totais, todos_produtos=todos_produtos, todas_categorias=todas_categorias)

@app.route('/relatorios/posicao_estoque/exportar')
def exportar_posicao_estoque_csv():
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') not in ['gestor', 'almoxarife']: return redirect(url_for('pagina_inicial'))
    filtros = { 'data_inicio': request.args.get('data_inicio'), 'data_fim': request.args.get('data_fim'), 'ordenar_por': request.args.get('ordenar_por', 'descricao'), 'produtos': request.args.getlist('produtos'), 'categorias': request.args.getlist('categorias') }
    dados_relatorio = []
    if not (filtros['data_inicio'] and filtros['data_fim']):
        flash('Datas são obrigatórias para exportar.', 'danger')
        return redirect(url_for('pagina_posicao_estoque'))
    query_produtos = supabase.table('produtos').select('id, descricao, codigo_sustentare, categoria_id')
    if filtros['produtos']:
        query_produtos = query_produtos.in_('id', [int(p) for p in filtros['produtos']])
    if filtros['categorias']:
        query_produtos = query_produtos.in_('categoria_id', [int(c) for c in filtros['categorias']])
    produtos_a_analisar = query_produtos.execute().data
    ids_produtos = [p['id'] for p in produtos_a_analisar]
    if ids_produtos:
        todas_movimentacoes = supabase.table('movimentacoes').select('produto_id, tipo, quantidade, custo_unitario, data').in_('produto_id', ids_produtos).lte('data', f"{filtros['data_fim']} 23:59:59").execute().data
        produtos_map = {p['id']: p for p in produtos_a_analisar}
        relatorio_map = { p_id: {'id': p_id, 'descricao': produtos_map[p_id]['descricao'], 'codigo_sustentare': produtos_map[p_id]['codigo_sustentare'], 'qtd_inicial': 0, 'valor_inicial': 0, 'qtd_entradas': 0, 'valor_entradas': 0, 'qtd_saidas': 0, 'valor_saidas': 0, 'qtd_final': 0, 'valor_final': 0} for p_id in ids_produtos }
        data_inicio_dt = datetime.fromisoformat(f"{filtros['data_inicio']}T00:00:00+00:00").replace(tzinfo=timezone.utc)
        for mov in todas_movimentacoes:
            p_id = mov['produto_id']
            if p_id in relatorio_map:
                item = relatorio_map[p_id]
                mov_data = datetime.fromisoformat(mov['data'].replace('Z', '+00:00')).replace(tzinfo=timezone.utc)
                if mov_data < data_inicio_dt:
                    if mov['tipo'] == 'entrada':
                        item['qtd_inicial'] += mov['quantidade']
                        if mov.get('custo_unitario', 0) > 0: item['valor_inicial'] += mov['quantidade'] * mov['custo_unitario']
                    else:
                        item['qtd_inicial'] -= mov['quantidade']
                else:
                    if mov['tipo'] == 'entrada':
                        item['qtd_entradas'] += mov['quantidade']
                        if mov.get('custo_unitario', 0) > 0: item['valor_entradas'] += mov['quantidade'] * mov['custo_unitario']
                    else:
                        item['qtd_saidas'] += mov['quantidade']
        for p_id in ids_produtos:
            item = relatorio_map[p_id]
            item['qtd_final'] = item['qtd_inicial'] + item['qtd_entradas'] - item['qtd_saidas']
            custo_medio_inicial = item['valor_inicial'] / item['qtd_inicial'] if item['qtd_inicial'] > 0 else 0
            item['valor_saidas'] = item['qtd_saidas'] * custo_medio_inicial
            item['valor_final'] = item['valor_inicial'] + item['valor_entradas'] - item['valor_saidas']
            dados_relatorio.append(item)
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['Produto', 'Qtd Inicial', 'Valor Inicial', 'Qtd Entradas', 'Valor Entradas', 'Qtd Saidas', 'Valor Saidas', 'Qtd Final', 'Valor Final'])
    for item in dados_relatorio:
        writer.writerow([ item['descricao'], item['qtd_inicial'], str(item['valor_inicial']).replace('.',','), item['qtd_entradas'], str(item['valor_entradas']).replace('.',','), item['qtd_saidas'], str(item['valor_saidas']).replace('.',','), item['qtd_final'], str(item['valor_final']).replace('.',',') ])
    output.seek(0)
    return Response(output.getvalue().encode('utf-8-sig'), mimetype="text/csv", headers={"Content-Disposition":f"attachment;filename=posicao_estoque_{datetime.now().strftime('%Y%m%d')}.csv"})

@app.route('/inventario/iniciar', methods=['GET'])
def pagina_iniciar_inventario():
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor':
        flash('Acesso negado: apenas gestores podem iniciar inventários.', 'danger')
        return redirect(url_for('pagina_contagem_inventario', inventario_id=inventario_id))
    
    # Busca todos os produtos para a tela de seleção
    try:
        response = supabase.table('produtos').select('id, codigo_sustentare, descricao').order('descricao').execute()
        todos_produtos = response.data
    except Exception as e:
        flash(f"Erro ao carregar produtos: {e}", "danger")
        todos_produtos = []
    
    return render_template('iniciar_inventario.html', todos_produtos=todos_produtos)

@app.route('/inventario/iniciar', methods=['POST'])
def iniciar_inventario():
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor': return redirect(url_for('pagina_inicial'))

    produtos_selecionados_ids = request.form.getlist('produtos_selecionados')

    if not produtos_selecionados_ids:
        flash('Nenhum produto foi selecionado. Por favor, escolha os itens para a contagem.', 'warning')
        return redirect(url_for('pagina_iniciar_inventario'))

    response_produtos = supabase.table('produtos').select('id, estoque_atual').in_('id', produtos_selecionados_ids).execute()
    produtos_para_inventariar = response_produtos.data

    try:
        # 1. Cria o "cabeçalho" do inventário
        dados_inventario = {'usuario_iniciou_id': session['user_id']}
        
        # --- LINHA CORRIGIDA ---
        # O método .insert() já retorna os dados inseridos. Não precisamos do .select()
        response_insert = supabase.table('inventarios').insert(dados_inventario).execute()
        inventario_criado = response_insert.data[0]
        inventario_id = inventario_criado['id']
        # --- FIM DA CORREÇÃO ---

        # 2. Cria os itens do inventário com o estoque "congelado"
        itens_para_inserir = []
        for produto in produtos_para_inventariar:
            itens_para_inserir.append({
                'inventario_id': inventario_id,
                'produto_id': produto['id'],
                'quantidade_teorica': produto['estoque_atual']
            })
        
        if itens_para_inserir:
            supabase.table('inventario_itens').insert(itens_para_inserir).execute()

        flash(f'Inventário #{inventario_id} iniciado com sucesso com {len(itens_para_inserir)} itens.', 'success')
        # Por enquanto, redireciona para a lista de inventários (que ainda vamos criar)
        return redirect(url_for('pagina_inicial')) # Placeholder temporário

    except Exception as e:
        flash(f'Ocorreu um erro ao iniciar o inventário: {e}', 'danger')
        return redirect(url_for('pagina_iniciar_inventario'))

@app.route('/inventarios/em_andamento')
def pagina_inventarios_em_andamento():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    try:
        # --- CONSULTA CORRIGIDA E SEM AMBIGUIDADE ---
        # Pedimos explicitamente para usar a relação do 'usuario_iniciou_id'
        # e damos um apelido para a tabela de usuários para o template entender
        response = supabase.table('inventarios').select(
            '*, usuario_iniciou:usuarios!inventarios_usuario_iniciou_id_fkey(nome)'
        ).eq('status', 'Em Andamento').order('data_inicio', desc=True).execute()
        inventarios = response.data
    except Exception as e:
        flash(f'Erro ao buscar inventários: {e}', 'danger')
        inventarios = []

    return render_template('inventarios_em_andamento.html', inventarios=inventarios)

@app.route('/inventario/<int:inventario_id>/contagem')
def pagina_contagem_inventario(inventario_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    
    try:
        # Busca o cabeçalho do inventário
        response_inv = supabase.table('inventarios').select('*, usuario_iniciou:usuarios!inventarios_usuario_iniciou_id_fkey(nome)').eq('id', inventario_id).single().execute()
        inventario = response_inv.data
        
        # Busca os itens a serem contados, com os nomes dos produtos
        response_itens = supabase.table('inventario_itens').select('*, produtos(*)').eq('inventario_id', inventario_id).order('id').execute()
        itens_inventario = response_itens.data

    except Exception as e:
        flash(f'Erro ao carregar dados do inventário: {e}', 'danger')
        return redirect(url_for('pagina_inventarios_em_andamento'))

    return render_template('contagem_inventario.html', inventario=inventario, itens_inventario=itens_inventario)

@app.route('/inventario/salvar_contagem', methods=['POST'])
def salvar_contagem_inventario():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    inventario_id = request.form.get('inventario_id')
    updates = []

    for key, value in request.form.items():
        if key.startswith('qtd_contada_'):
            if value and value.strip():
                produto_id = key.split('_')[-1]
                qtd_teorica_str = request.form.get(f'qtd_teorica_{produto_id}')
                
                updates.append({
                    'inventario_id': int(inventario_id),
                    'produto_id': int(produto_id),
                    # --- CORREÇÃO APLICADA ---
                    # Convertemos para float primeiro, depois para int
                    'quantidade_teorica': int(float(qtd_teorica_str)),
                    'quantidade_contada': int(float(value)),
                    # --- FIM DA CORREÇÃO ---
                    'usuario_contou_id': session['user_id']
                })
    
    try:
        if updates:
            supabase.table('inventario_itens').upsert(updates, on_conflict='inventario_id, produto_id').execute()
        flash('Progresso do inventário salvo com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao salvar progresso: {e}', 'danger')

    return redirect(url_for('pagina_contagem_inventario', inventario_id=inventario_id))

@app.route('/inventario/<int:inventario_id>/revisar')
def pagina_revisar_inventario(inventario_id):
    if session.get('user_role') != 'gestor':
        flash('Acesso negado.', 'danger')
        return redirect(url_for('pagina_inicial'))

    try:
        response_inv = supabase.table('inventarios').select('*, usuario_iniciou:usuarios!inventarios_usuario_iniciou_id_fkey(nome)').eq('id', inventario_id).single().execute()
        inventario = response_inv.data
        
        # 1. Busca TODOS os itens do inventário, sem tentar filtrar por divergência no banco
        query_itens = supabase.table('inventario_itens').select('*, produtos(*)').eq('inventario_id', inventario_id)
        
        itens_inventario_brutos = query_itens.order('id').execute().data
        
        # 2. Agora, filtramos a lista em Python
        filtro = request.args.get('filtro', 'todos')
        itens_inventario = []

        if filtro == 'divergencia':
            for item in itens_inventario_brutos:
                # Verifica se o item foi contado e se a contagem é diferente da teórica
                if item.get('quantidade_contada') is not None and item['quantidade_contada'] != item['quantidade_teorica']:
                    itens_inventario.append(item)
        elif filtro == 'nao_contados':
            for item in itens_inventario_brutos:
                if item.get('quantidade_contada') is None:
                    itens_inventario.append(item)
        else: # filtro == 'todos'
            itens_inventario = itens_inventario_brutos

    except Exception as e:
        flash(f'Erro ao carregar dados para revisão: {e}', 'danger')
        return redirect(url_for('pagina_inventarios_em_andamento'))

    return render_template('revisar_inventario.html', inventario=inventario, itens_inventario=itens_inventario, filtro=filtro)

@app.route('/inventario/finalizar', methods=['POST'])
def finalizar_inventario():
    if session.get('user_role') != 'gestor':
        return redirect(url_for('pagina_inicial'))

    inventario_id = request.form.get('inventario_id')
    observacoes = request.form.get('observacoes')
    
    try:
        # 1. Busca todos os itens do inventário para processar as divergências
        itens_inventario = supabase.table('inventario_itens').select('*, produtos(*)').eq('inventario_id', inventario_id).execute().data

        movimentacoes_ajuste = []
        produtos_para_atualizar = []

        for item in itens_inventario:
            qtd_contada = item.get('quantidade_contada')
            if qtd_contada is None: continue # Ignora itens não contados

            qtd_teorica = item['quantidade_teorica']
            diferenca = qtd_contada - qtd_teorica

            if diferenca != 0:
                produto = item['produtos']
                tipo_mov = 'Entrada por Ajuste de Inventário' if diferenca > 0 else 'Saída por Ajuste de Inventário'
                
                # Prepara a movimentação de ajuste
                movimentacoes_ajuste.append({
                    'produto_id': produto['id'],
                    'tipo': tipo_mov,
                    'quantidade': abs(diferenca),
                    'usuario_id': session['user_id'],
                    'requisitante_nome': f"Ajuste Inventário #{inventario_id}"
                })
                
                # Prepara a atualização do produto
                custo_medio = produto['valor_total_estoque'] / produto['quantidade_com_custo'] if produto['quantidade_com_custo'] > 0 else 0
                
                novo_estoque = produto['estoque_atual'] + diferenca
                novo_valor_total = produto['valor_total_estoque'] + (diferenca * custo_medio)

                supabase.table('produtos').update({
                    'estoque_atual': novo_estoque,
                    'valor_total_estoque': novo_valor_total
                }).eq('id', produto['id']).execute()

        # Insere todas as movimentações de ajuste de uma vez
        if movimentacoes_ajuste:
            supabase.table('movimentacoes').insert(movimentacoes_ajuste).execute()

        # 3. Finaliza o "cabeçalho" do inventário
        supabase.table('inventarios').update({
            'status': 'Finalizado',
            'data_fim': datetime.now(timezone.utc).isoformat(),
            'usuario_finalizou_id': session['user_id'],
            'observacoes': observacoes
        }).eq('id', inventario_id).execute()

        flash(f'Inventário #{inventario_id} finalizado e estoque ajustado com sucesso!', 'success')
        return redirect(url_for('pagina_inicial')) # Placeholder para o Histórico de Inventários

    except Exception as e:
        flash(f'Erro ao finalizar o inventário: {e}', 'danger')
        return redirect(url_for('pagina_revisar_inventario', inventario_id=inventario_id))

@app.route('/inventarios/historico')
def pagina_historico_inventarios():
    if session.get('user_role') != 'gestor':
        flash('Acesso negado.', 'danger')
        return redirect(url_for('pagina_inicial'))
    
    try:
        response = supabase.table('inventarios').select(
            '*, usuario_finalizou:usuarios!inventarios_usuario_finalizou_id_fkey(nome)'
        ).neq('status', 'Em Andamento').order('data_fim', desc=True).execute()
        inventarios = response.data
    except Exception as e:
        flash(f'Erro ao buscar histórico de inventários: {e}', 'danger')
        inventarios = []

    return render_template('historico_inventarios.html', inventarios=inventarios)

@app.route('/inventario/<int:inventario_id>/detalhes')
def pagina_detalhe_inventario(inventario_id):
    if session.get('user_role') != 'gestor':
        flash('Acesso negado.', 'danger')
        return redirect(url_for('pagina_inicial'))

    try:
        # Busca o cabeçalho do inventário e os nomes de ambos os usuários (início e fim)
        response_inv = supabase.table('inventarios').select(
            '*, usuario_iniciou:usuarios!inventarios_usuario_iniciou_id_fkey(nome), usuario_finalizou:usuarios!inventarios_usuario_finalizou_id_fkey(nome)'
        ).eq('id', inventario_id).single().execute()
        inventario = response_inv.data
        
        # Busca os itens do inventário
        response_itens = supabase.table('inventario_itens').select('*, produtos(*)').eq('inventario_id', inventario_id).order('id').execute()
        itens_inventario = response_itens.data

    except Exception as e:
        flash(f'Erro ao carregar detalhes do inventário: {e}', 'danger')
        return redirect(url_for('pagina_historico_inventarios'))

    return render_template('detalhe_inventario.html', inventario=inventario, itens_inventario=itens_inventario)

@app.route('/inventario/exportar_csv')
def exportar_relatorio_inventario_csv():
    if session.get('user_role') != 'gestor':
        return redirect(url_for('pagina_inicial'))

    inventario_id = request.args.get('inventario_id')
    if not inventario_id:
        flash('ID do inventário não fornecido.', 'danger')
        return redirect(url_for('pagina_inventarios_em_andamento'))

    try:
        # Busca os itens do inventário para o relatório
        response_itens = supabase.table('inventario_itens').select('*, produtos(*)').eq('inventario_id', inventario_id).order('id').execute()
        itens_inventario = response_itens.data

        # Geração do CSV em memória
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        
        # Escreve o cabeçalho
        writer.writerow(['ID Produto', 'Cód. Interno', 'Descrição', 'Qtd. Teórica', 'Qtd. Contada', 'Diferença'])
        
        # Escreve os dados
        for item in itens_inventario:
            produto = item.get('produtos', {})
            qtd_contada = item.get('quantidade_contada')
            qtd_teorica = item.get('quantidade_teorica')
            diferenca = ''

            if qtd_contada is not None and qtd_teorica is not None:
                diferenca = qtd_contada - qtd_teorica

            writer.writerow([
                produto.get('id', 'N/A'),
                produto.get('codigo_sustentare', 'N/A'),
                produto.get('descricao', 'N/A'),
                qtd_teorica,
                qtd_contada if qtd_contada is not None else 'NÃO CONTADO',
                diferenca
            ])
        
        output.seek(0)
        
        return Response(
            output.getvalue().encode('utf-8-sig'),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment;filename=relatorio_inventario_{inventario_id}.csv"}
        )

    except Exception as e:
        flash(f'Erro ao gerar o relatório CSV: {e}', 'danger')
        return redirect(url_for('pagina_revisar_inventario', inventario_id=inventario_id))

@app.route('/inventario/detalhes/exportar_csv')
def exportar_detalhe_inventario_csv():
    if session.get('user_role') != 'gestor':
        return redirect(url_for('pagina_inicial'))

    inventario_id = request.args.get('inventario_id')
    if not inventario_id:
        flash('ID do inventário não fornecido.', 'danger')
        return redirect(url_for('pagina_historico_inventarios'))

    try:
        # Busca os itens do inventário para o relatório
        response_itens = supabase.table('inventario_itens').select('*, produtos(*)').eq('inventario_id', inventario_id).order('id').execute()
        itens_inventario = response_itens.data

        # Geração do CSV em memória
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        
        # Escreve o cabeçalho
        writer.writerow(['ID Produto', 'Cód. Interno', 'Descrição', 'Qtd. Teórica', 'Qtd. Contada', 'Diferença'])
        
        # Escreve os dados
        for item in itens_inventario:
            produto = item.get('produtos', {})
            qtd_contada = item.get('quantidade_contada')
            qtd_teorica = item.get('quantidade_teorica')
            diferenca = ''

            if qtd_contada is not None and qtd_teorica is not None:
                diferenca = qtd_contada - qtd_teorica

            writer.writerow([
                produto.get('id', 'N/A'),
                produto.get('codigo_sustentare', 'N/A'),
                produto.get('descricao', 'N/A'),
                qtd_teorica,
                qtd_contada if qtd_contada is not None else 'NÃO CONTADO',
                diferenca
            ])
        
        output.seek(0)
        
        return Response(
            output.getvalue().encode('utf-8-sig'),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment;filename=inventario_{inventario_id}_detalhes.csv"}
        )

    except Exception as e:
        flash(f'Erro ao gerar o relatório CSV: {e}', 'danger')
        return redirect(url_for('pagina_detalhe_inventario', inventario_id=inventario_id))

# ===== ROTAS PARA GERENCIAMENTO DE EQUIPAMENTOS =====

@app.route('/equipamentos')
def pagina_equipamentos():
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor':
        flash('Acesso negado: você não tem permissão para esta área.', 'danger')
        return redirect(url_for('pagina_inicial'))
        
    response = supabase.table('equipamentos').select('*').order('id').execute()
    equipamentos = response.data
    return render_template('equipamentos.html', equipamentos=equipamentos)

@app.route('/equipamentos/adicionar', methods=['POST'])
def adicionar_equipamento():
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor': return redirect(url_for('pagina_inicial'))

    dados_novo_equipamento = {
        'codigo_identificador': request.form['codigo_identificador'].strip().upper(),
        'descricao': padronizar_texto(request.form['descricao'])
    }
    try:
        supabase.table('equipamentos').insert(dados_novo_equipamento).execute()
        flash('Equipamento adicionado com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao adicionar equipamento: {e}', 'danger')
    return redirect(url_for('pagina_equipamentos'))

@app.route('/equipamentos/excluir/<int:equipamento_id>', methods=['POST'])
def excluir_equipamento(equipamento_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor': return redirect(url_for('pagina_inicial'))

    try:
        supabase.table('equipamentos').delete().eq('id', equipamento_id).execute()
        flash('Equipamento excluído com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao excluir equipamento: {e}', 'danger')
    return redirect(url_for('pagina_equipamentos'))

@app.route('/equipamentos/editar/<int:equipamento_id>')
def pagina_editar_equipamento(equipamento_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor': return redirect(url_for('pagina_inicial'))

    response = supabase.table('equipamentos').select('*').eq('id', equipamento_id).single().execute()
    equipamento = response.data
    return render_template('editar_equipamento.html', equipamento=equipamento)

@app.route('/equipamentos/editar', methods=['POST'])
def editar_equipamento():
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor': return redirect(url_for('pagina_inicial'))

    equipamento_id = request.form['equipamento_id']
    dados_atualizados = {
        'codigo_identificador': request.form['codigo_identificador'].strip().upper(),
        'descricao': padronizar_texto(request.form['descricao'])
    }
    try:
        supabase.table('equipamentos').update(dados_atualizados).eq('id', equipamento_id).execute()
        flash('Equipamento atualizado com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao atualizar equipamento: {e}', 'danger')
    return redirect(url_for('pagina_equipamentos'))

# ===== ROTAS PARA GERENCIAMENTO DE COLABORADORES =====

@app.route('/colaboradores')
def pagina_colaboradores():
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor':
        flash('Acesso negado: você não tem permissão para esta área.', 'danger')
        return redirect(url_for('pagina_inicial'))
        
    response = supabase.table('colaboradores').select('*').order('id').execute()
    colaboradores = response.data
    return render_template('colaboradores.html', colaboradores=colaboradores)

@app.route('/colaboradores/adicionar', methods=['POST'])
def adicionar_colaborador():
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor': return redirect(url_for('pagina_inicial'))

    dados_novo_colaborador = {
        'nome': padronizar_texto(request.form['nome']),
        'cargo': padronizar_texto(request.form['cargo']),
        'setor': padronizar_texto(request.form['setor'])
    }
    try:
        supabase.table('colaboradores').insert(dados_novo_colaborador).execute()
        flash('Colaborador adicionado com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao adicionar colaborador: {e}', 'danger')
    return redirect(url_for('pagina_colaboradores'))

@app.route('/colaboradores/excluir/<int:colaborador_id>', methods=['POST'])
def excluir_colaborador(colaborador_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor': return redirect(url_for('pagina_inicial'))

    try:
        supabase.table('colaboradores').delete().eq('id', colaborador_id).execute()
        flash('Colaborador excluído com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao excluir colaborador: {e}', 'danger')
    return redirect(url_for('pagina_colaboradores'))

@app.route('/colaboradores/editar/<int:colaborador_id>')
def pagina_editar_colaborador(colaborador_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor': return redirect(url_for('pagina_inicial'))

    response = supabase.table('colaboradores').select('*').eq('id', colaborador_id).single().execute()
    colaborador = response.data
    return render_template('editar_colaborador.html', colaborador=colaborador)

@app.route('/colaboradores/editar', methods=['POST'])
def editar_colaborador():
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor': return redirect(url_for('pagina_inicial'))

    colaborador_id = request.form['colaborador_id']
    dados_atualizados = {
        'nome': padronizar_texto(request.form['nome']),
        'cargo': padronizar_texto(request.form['cargo']),
        'setor': padronizar_texto(request.form['setor'])
    }
    try:
        supabase.table('colaboradores').update(dados_atualizados).eq('id', colaborador_id).execute()
        flash('Colaborador atualizado com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao atualizar colaborador: {e}', 'danger')
    return redirect(url_for('pagina_colaboradores'))

# ===== ROTAS PARA USO TEMPORARIO (SEM NF) =====

@app.route('/uso_temporario')
def pagina_uso_temporario():
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor':
        flash('Acesso negado: você não tem permissão para esta área.', 'danger')
        return redirect(url_for('pagina_inicial'))

    # Busca todos os produtos para popular o dropdown do formulário
    try:
        produtos_response = supabase.table('produtos').select('id, descricao').order('descricao').execute()
        produtos = produtos_response.data
    except Exception as e:
        produtos = []
        flash(f'Erro ao carregar produtos: {e}', 'danger')

    # Busca todos os usos temporários com o nome do produto relacionado
    try:
        usos_response = supabase.table('uso_temporario').select('*, produtos(descricao)').order('id', desc=True).execute()
        usos_temporarios = usos_response.data
    except Exception as e:
        usos_temporarios = []
        flash(f'Erro ao carregar usos temporários: {e}', 'danger')

    return render_template('uso_temporario.html', produtos=produtos, usos_temporarios=usos_temporarios)

@app.route('/uso_temporario/adicionar', methods=['POST'])
def adicionar_uso_temporario():
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor': return redirect(url_for('pagina_inicial'))

    try:
        dados_novo_uso = {
            'produto_id': request.form['produto_id'],
            'quantidade_usada': request.form['quantidade_usada'],
            'numero_requisicao_alvo': request.form['numero_requisicao_alvo'].strip().upper()
            # data_uso e status já têm valores padrão definidos no banco
        }
        supabase.table('uso_temporario').insert(dados_novo_uso).execute()
        flash('Uso temporário registrado com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao registrar uso temporário: {e}', 'danger')

    return redirect(url_for('pagina_uso_temporario'))

# --- Bloco de Execução ---
if __name__ == '__main__':
    app.run(debug=True, port=5001)