from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, make_response
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

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('pagina_inicial'))

    if request.method == 'POST':
        email = request.form['email']
        senha = request.form['senha']
        
        # CORREÇÃO: Removemos o .single() e usamos .limit(1) para buscar no máximo um usuário.
        # Isso não causa erro se nenhum usuário for encontrado.
        response = supabase.table('usuarios').select('*, funcoes(nome_funcao)').eq('email', email).limit(1).execute()
        user_list = response.data
        
        # Verificamos se a lista está vazia (usuário não encontrado) OU se a senha está incorreta.
        if not user_list or not check_password_hash(user_list[0]['senha'], senha):
            flash('E-mail ou senha inválidos.', 'danger')
            return redirect(url_for('login'))

        # Se passou nas verificações, o login é um sucesso.
        user = user_list[0]
        session['user_id'] = user['id']
        session['user_name'] = user['nome']
        
        if user.get('funcoes'):
            session['user_role'] = user['funcoes']['nome_funcao'].lower()
        else:
            session['user_role'] = 'desconhecido'

        return redirect(url_for('pagina_inicial'))
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Você foi desconectado.', 'info')
    return redirect(url_for('login'))

# --- ROTAS DE GERENCIAMENTO (CADASTROS) ---
# ===== ROTAS CORRIGIDAS PARA O MÓDULO DE USUÁRIOS =====

# ===== ROTAS CORRIGIDAS E COMPLETAS PARA O MÓDULO DE USUÁRIOS =====

@app.route('/usuarios')
def pagina_usuarios():
    if 'user_id' not in session or session.get('user_role') != 'gestor':
        flash('Acesso negado.', 'danger')
        return redirect(url_for('pagina_inicial'))
    
    # Busca usuários E o nome da função relacionada
    try:
        response = supabase.table('usuarios').select('*, funcoes(nome_funcao)').order('id').execute()
        usuarios = response.data
        
        # Busca todas as funções disponíveis para o formulário de adicionar
        response_funcoes = supabase.table('funcoes').select('*').execute()
        todas_funcoes = response_funcoes.data
    except Exception as e:
        flash(f'Erro ao carregar dados de usuários: {e}', 'danger')
        usuarios = []
        todas_funcoes = []
    
    return render_template('usuarios.html', usuarios=usuarios, todas_funcoes=todas_funcoes)

@app.route('/usuarios/adicionar', methods=['POST'])
def adicionar_usuario():
    if 'user_id' not in session or session.get('user_role') != 'gestor':
        return redirect(url_for('pagina_inicial'))
    
    email = request.form['email'].strip()
    response_check = supabase.table('usuarios').select('id').eq('email', email).execute()
    if response_check.data:
        flash('Erro: O e-mail informado já está cadastrado.', 'danger')
        return redirect(url_for('pagina_usuarios'))
    
    try:
        funcao_id_selecionada = request.form.get('funcao_id')
        if not funcao_id_selecionada:
            flash('Erro: Uma função deve ser selecionada.', 'danger')
            return redirect(url_for('pagina_usuarios'))

        dados_novo_usuario = {
            'nome': padronizar_texto(request.form['nome']),
            'email': email,
            'senha': generate_password_hash(request.form['senha']),
            'funcao_id': int(funcao_id_selecionada)
        }
        supabase.table('usuarios').insert(dados_novo_usuario).execute()
        flash('Novo usuário cadastrado com sucesso!', 'success')

    except Exception as e:
        flash(f'Ocorreu um erro ao cadastrar o usuário: {e}', 'danger')

    return redirect(url_for('pagina_usuarios'))

@app.route('/usuario/editar/<int:usuario_id>')
def pagina_editar_usuario(usuario_id):
    if 'user_id' not in session or session.get('user_role') != 'gestor':
        return redirect(url_for('pagina_inicial'))

    try:
        response_usuario = supabase.table('usuarios').select('*').eq('id', usuario_id).single().execute()
        usuario = response_usuario.data
        
        response_funcoes = supabase.table('funcoes').select('*').execute()
        todas_funcoes = response_funcoes.data
        
        return render_template('editar_usuario.html', usuario=usuario, todas_funcoes=todas_funcoes)
    except Exception as e:
        flash(f'Erro ao carregar dados do usuário: {e}', 'danger')
        return redirect(url_for('pagina_usuarios'))

@app.route('/usuario/salvar_edicao', methods=['POST'])
def salvar_edicao_usuario():
    if 'user_id' not in session or session.get('user_role') != 'gestor':
        return redirect(url_for('pagina_inicial'))
        
    try:
        usuario_id = request.form['usuario_id']
        funcao_id_selecionada = request.form.get('funcao_id')
        if not funcao_id_selecionada:
            flash('Erro: Uma função deve ser selecionada.', 'danger')
            return redirect(url_for('pagina_editar_usuario', usuario_id=usuario_id))

        dados = { 
            'nome': padronizar_texto(request.form['nome']),
            'email': request.form['email'].strip(),
            'funcao_id': int(funcao_id_selecionada)
        }
        supabase.table('usuarios').update(dados).eq('id', usuario_id).execute()
        flash('Usuário atualizado com sucesso!', 'success')
    except Exception as e:
        flash(f'Ocorreu um erro ao atualizar o usuário: {e}', 'danger')

    return redirect(url_for('pagina_usuarios'))

@app.route('/usuario/excluir/<int:usuario_id>', methods=['POST'])
def excluir_usuario(usuario_id):
    if 'user_id' not in session or session.get('user_role') != 'gestor':
        return redirect(url_for('login'))
        
    if session['user_id'] == usuario_id:
        flash('Ação inválida: você não pode excluir sua própria conta.', 'danger')
        return redirect(url_for('pagina_usuarios'))
    
    try:
        # Trava de segurança: impede excluir usuário com histórico de movimentações
        movimentacoes = supabase.table('movimentacoes').select('id', count='exact').eq('usuario_id', usuario_id).execute()
        if movimentacoes.count > 0:
            flash('Este usuário não pode ser excluído, pois possui um histórico de movimentações.', 'danger')
            return redirect(url_for('pagina_usuarios'))
        
        supabase.table('usuarios').delete().eq('id', usuario_id).execute()
        flash('Usuário excluído com sucesso.', 'success')
    except Exception as e:
        flash(f'Erro ao excluir usuário: {e}', 'danger')

    return redirect(url_for('pagina_usuarios'))

# ===== ROTAS CORRIGIDAS PARA FORNECEDORES =====

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

    # CORREÇÃO: Usando 'nome_fornecedor'
    dados_novo_fornecedor = { 
        'nome_fornecedor': padronizar_texto(request.form['nome_fornecedor']),
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
    return render_template('editar_fornecedor.html', fornecedor=fornecedor)

@app.route('/fornecedor/salvar_edicao', methods=['POST'])
def salvar_edicao_fornecedor():
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('user_role') != 'gestor': return redirect(url_for('pagina_inicial'))
    fornecedor_id = request.form['fornecedor_id']
    cnpj_limpo = ''.join(filter(str.isdigit, request.form['cnpj']))

    if len(cnpj_limpo) != 14:
        flash('Erro: O CNPJ deve conter 14 dígitos.', 'danger')
        return redirect(url_for('pagina_editar_fornecedor', fornecedor_id=fornecedor_id))

    # CORREÇÃO: Usando 'nome_fornecedor'
    dados = { 
        'nome_fornecedor': padronizar_texto(request.form['nome_fornecedor']),
        'cnpj': cnpj_limpo 
    }
    supabase.table('fornecedores').update(dados).eq('id', fornecedor_id).execute()
    flash('Fornecedor atualizado com sucesso!', 'success')
    return redirect(url_for('pagina_fornecedores'))

# A sua função excluir_fornecedor já está correta e não precisa de alterações.

@app.route('/fornecedor/excluir/<int:fornecedor_id>', methods=['POST'])
def excluir_fornecedor(fornecedor_id):
    if 'user_id' not in session or session.get('user_role') != 'gestor':
        return redirect(url_for('login'))
    
    try:
        # Trava de segurança: Verifica se o fornecedor tem movimentações de entrada
        movimentacoes = supabase.table('movimentacoes').select('id', count='exact').eq('fornecedor_id', fornecedor_id).execute()
        if movimentacoes.count > 0:
            flash('Este fornecedor não pode ser excluído pois possui um histórico de entradas no estoque.', 'danger')
            return redirect(url_for('pagina_fornecedores'))

        # Se não houver movimentações, pode excluir
        supabase.table('fornecedores').delete().eq('id', fornecedor_id).execute()
        flash('Fornecedor excluído com sucesso!', 'success')

    except Exception as e:
        flash(f'Erro ao excluir fornecedor: {e}', 'danger')

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
    
    # --- LÓGICA DE PAGINAÇÃO ---
    ITENS_POR_PAGINA = 50 # Ajustado conforme sua solicitação
    try:
        page = int(request.args.get('page', 1))
    except ValueError:
        page = 1
    
    start_index = (page - 1) * ITENS_POR_PAGINA
    end_index = start_index + ITENS_POR_PAGINA - 1
    
    # --- LÓGICA DE BUSCA E ORDENAÇÃO ---
    termo_busca = request.args.get('busca', '').strip()
    sort_by = request.args.get('sort_by', 'id')
    order = request.args.get('order', 'asc')

    # 1. Constrói a query base, pedindo a contagem total de itens
    query = supabase.table('produtos').select('*, categorias(nome_categoria)', count='exact')
    if termo_busca:
        query = query.or_(f'descricao.ilike.%{termo_busca}%,codigo_sustentare.ilike.%{termo_busca}%,codigo_valor.ilike.%{termo_busca}%')

    # 2. Executa a query com ordenação e paginação (usando .range())
    response_produtos = query.order(sort_by, desc=(order == 'desc')).range(start_index, end_index).execute()
    produtos_data = response_produtos.data
    total_itens = response_produtos.count

    # 3. Calcula o total de páginas
    total_pages = (total_itens + ITENS_POR_PAGINA - 1) // ITENS_POR_PAGINA
    
    # --- LÓGICA DE CÁLCULO DE CUSTOS (EXISTENTE) ---
    for produto in produtos_data:
        quantidade_com_custo = float(produto.get('quantidade_com_custo') or 0)
        valor_total_estoque = float(produto.get('valor_total_estoque') or 0)
        
        if quantidade_com_custo > 0:
            produto['custo_medio'] = valor_total_estoque / quantidade_com_custo
        else:
            produto['custo_medio'] = 0
            
        produto['valor_total_calculado'] = produto['custo_medio'] * float(produto.get('estoque_atual') or 0)

    # Buscas para os formulários
    response_categorias = supabase.table('categorias').select('*').execute()
    categorias = response_categorias.data
    response_unidades = supabase.table('unidades_medida').select('*').execute()
    unidades_medida = response_unidades.data
    
    # Envia os dados da paginação para o template
    return render_template('estoque.html', 
                           produtos=produtos_data, 
                           categorias=categorias, 
                           unidades_medida=unidades_medida, 
                           busca=termo_busca, 
                           sort_by=sort_by, 
                           order=order,
                           page=page,
                           total_pages=total_pages)

@app.route('/estoque/exportar_csv')
def exportar_estoque_atual_csv():
    if 'user_id' not in session: return redirect(url_for('login'))

    # A lógica de busca, cálculo e ordenação continua a mesma
    termo_busca = request.args.get('busca', '').strip()
    query = supabase.table('produtos').select('*, categorias(nome_categoria)')
    if termo_busca:
        query = query.or_(f'descricao.ilike.%{termo_busca}%,codigo_sustentare.ilike.%{termo_busca}%,codigo_valor.ilike.%{termo_busca}%')
    response_produtos = query.execute()
    produtos_data = response_produtos.data

    for produto in produtos_data:
        quantidade_com_custo = float(produto.get('quantidade_com_custo') or 0)
        valor_total_estoque = float(produto.get('valor_total_estoque') or 0)
        if quantidade_com_custo > 0:
            produto['custo_medio'] = valor_total_estoque / quantidade_com_custo
        else:
            produto['custo_medio'] = 0
        produto['valor_total_calculado'] = produto['custo_medio'] * float(produto.get('estoque_atual') or 0)

    sort_by = request.args.get('sort_by', 'id')
    order = request.args.get('order', 'asc')
    is_reverse = order == 'desc'
    def sort_key(produto):
        valor = produto.get(sort_by, 0)
        if isinstance(valor, (int, float)): return valor
        return str(valor).lower()
    produtos_data.sort(key=sort_key, reverse=is_reverse)
    
    # GERAÇÃO DO ARQUIVO CSV
    si = io.StringIO()
    cw = csv.writer(si, delimiter=';')
    
    cabecalho = ['ID', 'Cód. Sustentare', 'Cód. Valor', 'Descrição', 'Categoria', 'Estoque Atual', 'Custo Médio (R$)', 'Valor Total (R$)']
    cw.writerow(cabecalho)
    
    for produto in produtos_data:
        linha = [
            produto.get('id'),
            produto.get('codigo_sustentare'),
            produto.get('codigo_valor'),
            produto.get('descricao'),
            produto.get('categorias', {}).get('nome_categoria', 'N/A'),
            "{:.2f}".format(produto.get('estoque_atual', 0)),
            "{:.2f}".format(produto.get('custo_medio', 0)),
            "{:.2f}".format(produto.get('valor_total_calculado', 0))
        ]
        cw.writerow(linha)
    
    # --- CORREÇÃO DE ENCODING APLICADA AQUI ---
    # 1. Pega a string do CSV e a codifica para bytes usando utf-8-sig
    # O '-sig' adiciona o "sinal" (BOM) que o Excel precisa para entender os acentos.
    csv_bytes = si.getvalue().encode('utf-8-sig')

    # 2. Cria a resposta Flask usando os bytes
    output = make_response(csv_bytes)

    # 3. Define os cabeçalhos para o navegador
    output.headers["Content-Disposition"] = "attachment; filename=estoque_atual.csv"
    output.headers["Content-type"] = "text/csv; charset=utf-8-sig"
    # --- FIM DA CORREÇÃO ---
    
    return output

@app.route('/inventario/<int:inventario_id>/exportar_contagem_csv')
def exportar_contagem_inventario_csv(inventario_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        itens_response = supabase.table('inventario_itens').select(
            '*, produtos(descricao, codigo_sustentare, codigo_valor)'
        ).eq('inventario_id', inventario_id).order('produto_id').execute()
        itens_inventario = itens_response.data

        si = io.StringIO()
        cw = csv.writer(si, delimiter=';')
        
        # CORREÇÃO 1: Adicionada a coluna "Quantidade Teórica" no cabeçalho
        cabecalho = ['ID Produto', 'Cód. Sustentare', 'Cód. Valor', 'Descrição do Produto', 'Quantidade Teórica', 'Quantidade Contada']
        cw.writerow(cabecalho)
        
        for item in itens_inventario:
            # CORREÇÃO 2: Adicionado o dado 'quantidade_teorica' na linha
            linha = [
                item.get('produto_id'),
                (item.get('produtos') or {}).get('codigo_sustentare', ''),
                (item.get('produtos') or {}).get('codigo_valor', ''),
                (item.get('produtos') or {}).get('descricao', ''),
                item.get('quantidade_teorica', ''), # Dado do estoque teórico
                '' # Coluna vazia para a contagem manual
            ]
            cw.writerow(linha)
            
        csv_bytes = si.getvalue().encode('utf-8-sig')
        output = make_response(csv_bytes)
        output.headers["Content-Disposition"] = f"attachment; filename=folha_contagem_inventario_{inventario_id}.csv"
        output.headers["Content-type"] = "text/csv; charset=utf-8-sig"
        return output

    except Exception as e:
        flash(f'Erro ao gerar CSV de contagem: {e}', 'danger')
        return redirect(url_for('pagina_contagem_inventario', inventario_id=inventario_id))
    
@app.route('/produtos/adicionar', methods=['POST'])
def adicionar_produto():
    if 'user_id' not in session or session.get('user_role') != 'gestor':
        return redirect(url_for('pagina_estoque'))

    try:
        # 1. Pega os dados do formulário e garante que o padrão '0' seja aplicado
        codigo_sustentare = request.form.get('codigo_sustentare', '0').strip() or '0'
        codigo_valor = request.form.get('codigo_valor', '0').strip() or '0'
        
        # --- NOVA LÓGICA DE VALIDAÇÃO DE DUPLICIDADE ---
        
        # 2. Valida Código Sustentare (só se for diferente de '0')
        if codigo_sustentare != '0':
            query_sustentare = supabase.table('produtos').select('id', count='exact').eq('codigo_sustentare', codigo_sustentare).execute()
            if query_sustentare.count > 0:
                flash(f'Erro: O Código Sustentare "{codigo_sustentare}" já está em uso.', 'danger')
                return redirect(url_for('pagina_estoque'))

        # 3. Valida Código Valor (só se for diferente de '0')
        if codigo_valor != '0':
            query_valor = supabase.table('produtos').select('id', count='exact').eq('codigo_valor', codigo_valor).execute()
            if query_valor.count > 0:
                flash(f'Erro: O Código Valor "{codigo_valor}" já está em uso.', 'danger')
                return redirect(url_for('pagina_estoque'))
        
        # --- FIM DA VALIDAÇÃO ---

        # 4. Se passou nas validações, cria o novo produto
        dados_novo_produto = {
            'descricao': padronizar_texto(request.form['descricao']),
            'categoria_id': int(request.form['categoria_id']),
            'codigo_sustentare': codigo_sustentare,
            'codigo_valor': codigo_valor,
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
    
    tipo = request.form['tipo']
    produto_id = int(request.form['produto_id'])
    quantidade_movimentada = float(request.form.get('quantidade', 0))

    if quantidade_movimentada <= 0:
        flash('Erro: A quantidade da movimentação deve ser maior que zero.', 'danger')
        return redirect(url_for('pagina_movimentacao', produto_id=produto_id, tipo=tipo))
    
    response_produto = supabase.table('produtos').select('estoque_atual, valor_total_estoque, quantidade_com_custo').eq('id', produto_id).limit(1).single().execute()
    produto_atual = response_produto.data
    
    estoque_antigo = float(produto_atual.get('estoque_atual', 0))
    valor_total_antigo = float(produto_atual.get('valor_total_estoque', 0))
    quantidade_com_custo_antiga = float(produto_atual.get('quantidade_com_custo', 0))

    dados_movimentacao = { 'produto_id': produto_id, 'tipo': tipo, 'quantidade': quantidade_movimentada, 'usuario_id': session['user_id'] }
    
    if tipo == 'entrada':
        custo_unitario_entrada = float(request.form.get('custo_unitario', 0))
        if custo_unitario_entrada < 0:
            flash('Erro: O custo unitário não pode ser um valor negativo.', 'danger')
            return redirect(url_for('pagina_movimentacao', produto_id=produto_id, tipo=tipo))

        numero_requisicao_alvo = request.form.get('numero_requisicao_alvo', '').strip().upper()
        fornecedor_id = request.form.get('fornecedor_id')

        dados_movimentacao.update({
            'preco_unitario': custo_unitario_entrada,
            'fornecedor_id': int(fornecedor_id) if fornecedor_id else None,
            'numero_requisicao_alvo': numero_requisicao_alvo,
            'tipo_documento': request.form.get('tipo_documento'),
            'numero_documento': request.form.get('numero_documento', '0')
        })
        
        novo_estoque = estoque_antigo + quantidade_movimentada
        novo_valor_total = valor_total_antigo
        nova_quantidade_com_custo = quantidade_com_custo_antiga
        if custo_unitario_entrada > 0:
            novo_valor_total += quantidade_movimentada * custo_unitario_entrada
            nova_quantidade_com_custo += quantidade_movimentada
        
        dados_produto_update = { 'estoque_atual': novo_estoque, 'valor_total_estoque': novo_valor_total, 'quantidade_com_custo': nova_quantidade_com_custo }
        flash_message = 'Entrada registrada com sucesso!'

    else: # Saída
        if estoque_antigo < quantidade_movimentada:
            flash(f'Erro: Quantidade de saída ({quantidade_movimentada}) é maior que o estoque atual ({estoque_antigo}).', 'danger')
            return redirect(url_for('pagina_movimentacao', produto_id=produto_id, tipo=tipo))
        
        equipamento_id_str = request.form.get('equipamento_id')
        equipamento_id = int(equipamento_id_str) if equipamento_id_str else None
        colaborador_id_str = request.form.get('colaborador_id')
        colaborador_id = int(colaborador_id_str) if colaborador_id_str else None
        custo_medio_atual = valor_total_antigo / quantidade_com_custo_antiga if quantidade_com_custo_antiga > 0 else 0
        
        dados_movimentacao.update({
            'preco_unitario': custo_medio_atual,
            'colaborador_id': colaborador_id,
            'equipamento_id': equipamento_id,
            'numero_requisicao_manual': request.form.get('numero_requisicao_manual')
        })

        novo_estoque = estoque_antigo - quantidade_movimentada
        novo_valor_total = valor_total_antigo - (quantidade_movimentada * custo_medio_atual)
        nova_quantidade_com_custo = quantidade_com_custo_antiga - quantidade_movimentada
        
        dados_produto_update = { 'estoque_atual': max(0, novo_estoque), 'valor_total_estoque': max(0, novo_valor_total), 'quantidade_com_custo': max(0, nova_quantidade_com_custo) }
        flash_message = 'Saída registrada com sucesso!'

    supabase.table('movimentacoes').insert(dados_movimentacao).execute()
    supabase.table('produtos').update(dados_produto_update).eq('id', produto_id).execute()
    
    # --- CORREÇÃO: LÓGICA DE BAIXA EM CASCATA RESTAURADA ---
    if tipo == 'entrada' and dados_movimentacao.get('numero_requisicao_alvo'):
        try:
            saldo_entrada = quantidade_movimentada
            usos_pendentes = supabase.table('uso_temporario').select('*').eq('numero_requisicao_alvo', dados_movimentacao['numero_requisicao_alvo']).eq('produto_id', produto_id).in_('status', ['Pendente', 'Baixado Parcialmente']).order('id').execute().data
            
            for uso in usos_pendentes:
                if saldo_entrada <= 0: break
                
                quantidade_pendente = float(uso['quantidade_usada'])
                dados_atualizacao_uso = {}

                if saldo_entrada >= quantidade_pendente:
                    dados_atualizacao_uso['status'] = 'Baixado'
                    dados_atualizacao_uso['quantidade_usada'] = 0
                    saldo_entrada -= quantidade_pendente
                    flash(f'Uso temporário ID {uso["id"]} ({quantidade_pendente} un.) baixado integralmente.', 'info')
                else:
                    nova_quantidade_pendente = quantidade_pendente - saldo_entrada
                    dados_atualizacao_uso['status'] = 'Baixado Parcialmente'
                    dados_atualizacao_uso['quantidade_usada'] = nova_quantidade_pendente
                    saldo_entrada = 0
                    flash(f'Uso temporário ID {uso["id"]} baixado parcialmente. Restam {nova_quantidade_pendente} un. pendentes.', 'info')
                
                supabase.table('uso_temporario').update(dados_atualizacao_uso).eq('id', uso['id']).execute()
        except Exception as e:
            print(f"DEBUG: Não foi possível realizar a baixa automática. Erro: {e}")

    flash(flash_message, 'success')
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
    if 'user_id' not in session or session.get('user_role') != 'gestor':
        return redirect(url_for('login'))

    try:
        produto_id = int(request.form['produto_id'])
        # Garante que, se o campo vier vazio, ele seja '0'
        codigo_sustentare = request.form.get('codigo_sustentare', '0').strip() or '0'
        codigo_valor = request.form.get('codigo_valor', '0').strip() or '0'
        
        # --- NOVA LÓGICA DE VALIDAÇÃO DE DUPLICIDADE ---
        
        # 1. Valida Código Sustentare (só se for diferente de '0')
        if codigo_sustentare != '0':
            # Procura por outro produto (!= do que estamos editando) com o mesmo código
            query_sustentare = supabase.table('produtos').select('id').eq('codigo_sustentare', codigo_sustentare).neq('id', produto_id).execute()
            if query_sustentare.data:
                flash(f'Erro: O Código Sustentare "{codigo_sustentare}" já está em uso por outro produto.', 'danger')
                return redirect(url_for('pagina_editar_produto', produto_id=produto_id))

        # 2. Valida Código Valor (só se for diferente de '0')
        if codigo_valor != '0':
            # Procura por outro produto (!= do que estamos editando) com o mesmo código
            query_valor = supabase.table('produtos').select('id').eq('codigo_valor', codigo_valor).neq('id', produto_id).execute()
            if query_valor.data:
                flash(f'Erro: O Código Valor "{codigo_valor}" já está em uso por outro produto.', 'danger')
                return redirect(url_for('pagina_editar_produto', produto_id=produto_id))

        # --- FIM DA VALIDAÇÃO ---

        # Se passou nas validações, atualiza o produto
        dados_atualizados = {
            'descricao': padronizar_texto(request.form['descricao']),
            'categoria_id': int(request.form['categoria_id']),
            'codigo_sustentare': codigo_sustentare,
            'codigo_valor': codigo_valor,
            'unidade_medida_id': int(request.form['unidade_medida_id'])
        }
        supabase.table('produtos').update(dados_atualizados).eq('id', produto_id).execute()
        flash('Produto atualizado com sucesso!', 'success')
    
    except Exception as e:
        flash(f'Erro ao atualizar produto: {e}', 'danger')

    return redirect(url_for('pagina_estoque'))

@app.route('/produto/salvar_edicao', methods=['POST'])
def salvar_edicao_produto():
    if 'user_id' not in session: return redirect(url_for('login'))
    produto_id = request.form['produto_id']
    dados_para_atualizar = { 'codigo_sustentare': request.form['codigo_sustentare'], 'descricao': request.form['descricao'], 'unidade_medida': request.form['unidade_medida'], 'estoque_minimo': request.form['estoque_minimo'], 'categoria_id': request.form['categoria_id'] }
    supabase.table('produtos').update(dados_para_atualizar).eq('id', produto_id).execute()
    flash('Produto atualizado com sucesso!', 'success')
    return redirect(url_for('pagina_estoque'))

@app.route('/produtos/excluir/<int:produto_id>', methods=['POST'])
def excluir_produto(produto_id):
    if 'user_id' not in session or session.get('user_role') != 'gestor':
        return redirect(url_for('login'))
    
    try:
        # --- NOVA TRAVA DE SEGURANÇA ---
        # 1. Antes de apagar, verifica se existe alguma movimentação para este produto.
        # Usamos 'count' para ser uma consulta rápida e eficiente.
        movimentacoes_count = supabase.table('movimentacoes').select('id', count='exact').eq('produto_id', produto_id).execute()

        # 2. Se o contador for maior que zero, o produto tem histórico. Bloqueamos a exclusão.
        if movimentacoes_count.count > 0:
            flash('Este produto não pode ser excluído pois possui um histórico de movimentações.', 'danger')
            return redirect(url_for('pagina_estoque'))

        # --- FIM DA TRAVA DE SEGURANÇA ---

        # 3. Se o produto passou na verificação (não tem histórico), ele pode ser excluído.
        # Limpamos primeiro registros em outras tabelas que possam estar vinculados.
        supabase.table('inventario_itens').delete().eq('produto_id', produto_id).execute()
        supabase.table('uso_temporario').delete().eq('produto_id', produto_id).execute()
        
        # E finalmente, excluímos o produto da tabela principal.
        supabase.table('produtos').delete().eq('id', produto_id).execute()
        flash('Produto excluído com sucesso!', 'success')

    except Exception as e:
        flash(f'Erro ao excluir produto: {e}', 'danger')

    return redirect(url_for('pagina_estoque'))

# ===== COLE ESTAS DUAS FUNÇÕES NO SEU main.py, SUBSTITUINDO AS VERSÕES ANTIGAS =====

@app.route('/relatorios/historico')
def pagina_relatorio_historico():
    if 'user_id' not in session or session.get('user_role') != 'gestor':
        return redirect(url_for('login'))
    
    todos_produtos = supabase.table('produtos').select('id, descricao').order('descricao').execute().data
    todos_fornecedores = supabase.table('fornecedores').select('id, nome_fornecedor').order('nome_fornecedor').execute().data
    todos_usuarios = supabase.table('usuarios').select('id, nome').order('nome').execute().data
    todos_equipamentos = supabase.table('equipamentos').select('id, codigo_identificador, descricao').order('codigo_identificador').execute().data
    
    # Coleta os filtros da URL, agora com os campos separados
    filtros = {
        'data_inicio': request.args.get('data_inicio'),
        'data_fim': request.args.get('data_fim'),
        'tipo': request.args.get('tipo'),
        'produtos_ids': request.args.getlist('produtos_ids', type=int),
        'fornecedores_ids': request.args.getlist('fornecedores_ids', type=int),
        'usuarios_ids': request.args.getlist('usuarios_ids', type=int),
        'equipamentos_ids': request.args.getlist('equipamentos_ids', type=int),
        'nf_doc': request.args.get('nf_doc', '').strip(), # Filtro separado para NF/Doc de entrada
        'req_manual': request.args.get('req_manual', '').strip() # Filtro separado para Req. Manual de saída
    }

    query = supabase.table('movimentacoes').select(
        '*, produtos(descricao, codigo_sustentare, codigo_valor), fornecedores(nome_fornecedor), usuarios(nome), colaboradores(nome), equipamentos(descricao, codigo_identificador)'
    ).order('created_at', desc=True)

    # Aplica os filtros na consulta
    if filtros['data_inicio']: query = query.gte('created_at', filtros['data_inicio'])
    if filtros['data_fim']: query = query.lte('created_at', filtros['data_fim'] + 'T23:59:59')
    if filtros['tipo']: query = query.eq('tipo', filtros['tipo'])
    if filtros['produtos_ids']: query = query.in_('produto_id', filtros['produtos_ids'])
    if filtros['fornecedores_ids']: query = query.in_('fornecedor_id', filtros['fornecedores_ids'])
    if filtros['usuarios_ids']: query = query.in_('usuario_id', filtros['usuarios_ids'])
    if filtros['equipamentos_ids']: query = query.in_('equipamento_id', filtros['equipamentos_ids'])
    # CORREÇÃO: Usando .eq() para busca exata em vez de .ilike()
    if filtros['nf_doc']: query = query.eq('numero_documento', filtros['nf_doc'])
    if filtros['req_manual']: query = query.eq('numero_requisicao_manual', filtros['req_manual'])

    response = query.execute()
    movimentacoes = response.data
    
    return render_template('historico_lancamentos.html', 
                           movimentacoes=movimentacoes, filtros=filtros, todos_produtos=todos_produtos,
                           todos_fornecedores=todos_fornecedores, todos_usuarios=todos_usuarios,
                           todos_equipamentos=todos_equipamentos)

@app.route('/relatorios/historico/exportar_csv')
def exportar_historico_csv():
    if 'user_id' not in session or session.get('user_role') != 'gestor':
        return redirect(url_for('login'))

    # REPETE A MESMA LÓGICA DE FILTROS APRIMORADA
    filtros = {
        'data_inicio': request.args.get('data_inicio'), 'data_fim': request.args.get('data_fim'),
        'tipo': request.args.get('tipo'), 'produtos_ids': request.args.getlist('produtos_ids', type=int),
        'fornecedores_ids': request.args.getlist('fornecedores_ids', type=int), 'usuarios_ids': request.args.getlist('usuarios_ids', type=int),
        'equipamentos_ids': request.args.getlist('equipamentos_ids', type=int), 'nf_doc': request.args.get('nf_doc', '').strip(),
        'req_manual': request.args.get('req_manual', '').strip()
    }
    query = supabase.table('movimentacoes').select('*, produtos(descricao, codigo_sustentare, codigo_valor), fornecedores(nome_fornecedor), usuarios(nome), colaboradores(nome), equipamentos(codigo_identificador, descricao)').order('created_at', desc=True)
    if filtros['data_inicio']: query = query.gte('created_at', filtros['data_inicio'])
    if filtros['data_fim']: query = query.lte('created_at', filtros['data_fim'] + 'T23:59:59')
    if filtros['tipo']: query = query.eq('tipo', filtros['tipo'])
    if filtros['produtos_ids']: query = query.in_('produto_id', filtros['produtos_ids'])
    if filtros['fornecedores_ids']: query = query.in_('fornecedor_id', filtros['fornecedores_ids'])
    if filtros['usuarios_ids']: query = query.in_('usuario_id', filtros['usuarios_ids'])
    if filtros['equipamentos_ids']: query = query.in_('equipamento_id', filtros['equipamentos_ids'])
    if filtros['nf_doc']: query = query.eq('numero_documento', filtros['nf_doc'])
    if filtros['req_manual']: query = query.eq('numero_requisicao_manual', filtros['req_manual'])
    movimentacoes = query.execute().data
    
    si = io.StringIO()
    cw = csv.writer(si, delimiter=';')
    cabecalho = ['Data', 'Tipo', 'ID Produto', 'Cód. Sustentare', 'Cód. Valor', 'Descrição Produto', 'Qtd', 'Custo Unit.', 'Valor Total', 'Fornecedor/Requisitante', 'Equipamento', 'NF/Doc (Entrada)', 'Req. Manual (Saída)', 'Usuário']
    cw.writerow(cabecalho)
    for mov in movimentacoes:
        valor_total = (float(mov.get('preco_unitario', 0) or 0) * float(mov.get('quantidade', 0) or 0))
        linha = [
            mov.get('created_at'), mov.get('tipo'), mov.get('produto_id'),
            (mov.get('produtos') or {}).get('codigo_sustentare', 'N/A'), (mov.get('produtos') or {}).get('codigo_valor', 'N/A'),
            (mov.get('produtos') or {}).get('descricao', 'N/A'), mov.get('quantidade'), "{:.2f}".format(mov.get('preco_unitario', 0) or 0), "{:.2f}".format(valor_total),
            (mov.get('fornecedores') or {}).get('nome_fornecedor', '') if mov.get('tipo') == 'entrada' else (mov.get('colaboradores') or {}).get('nome', ''),
            (mov.get('equipamentos') or {}).get('codigo_identificador', ''), mov.get('numero_documento'),
            mov.get('numero_requisicao_manual'), (mov.get('usuarios') or {}).get('nome', 'N/A')
        ]
        cw.writerow(linha)
        
    csv_bytes = si.getvalue().encode('utf-8-sig')
    output = make_response(csv_bytes)
    output.headers["Content-Disposition"] = "attachment; filename=historico_lancamentos.csv"
    output.headers["Content-type"] = "text/csv; charset=utf-8-sig"
    return output

# ===== FUNÇÃO MOTOR PARA CÁLCULO DE POSIÇÃO DE ESTOQUE
def calcular_posicao_estoque_data(data_inicio, data_fim, categorias_ids=None, produtos_ids=None):
    print("\n--- INICIANDO 'calcular_posicao_estoque_data' ---")
    print(f"Filtros recebidos: data_inicio={data_inicio}, data_fim={data_fim}, produtos_ids={produtos_ids}")
    
    try:
        query = supabase.table('produtos').select('*, categorias!left(nome_categoria)')
        if categorias_ids: query = query.in_('categoria_id', categorias_ids)
        if produtos_ids: query = query.in_('id', produtos_ids)
        produtos = query.execute().data
        
        if not produtos: 
            print("--- FINALIZANDO: Nenhum produto encontrado com os filtros.")
            return []
        
        print(f"--- DEBUG: {len(produtos)} produtos encontrados.")
        ids_dos_produtos_filtrados = [p['id'] for p in produtos]
        movimentacoes = supabase.table('movimentacoes').select('*').in_('produto_id', ids_dos_produtos_filtrados).lte('created_at', data_fim + 'T23:59:59').order('created_at').execute().data
        print(f"--- DEBUG: {len(movimentacoes)} movimentações totais encontradas para estes produtos.")

        resultado_final = []
        for produto in produtos:
            print(f"\n--- Processando Produto ID: {produto['id']} - {produto['descricao']} ---")
            
            dados_relatorio = {
                'id': produto['id'], 'descricao': produto['descricao'],
                'codigo_sustentare': produto.get('codigo_sustentare'), 'codigo_valor': produto.get('codigo_valor'),
                'categorias': produto.get('categorias'),
                'inicial_qtd': 0.0, 'inicial_valor': 0.0,
                'entradas_qtd': 0.0, 'entradas_valor': 0.0,
                'saidas_qtd': 0.0, 'saidas_valor': 0.0,
            }
            qtd_custo_inicial = 0.0

            print("--- Calculando Saldo Inicial (movimentações ANTES de data_inicio)...")
            for mov in movimentacoes:
                data_mov_str = mov.get('created_at', '')[:10]
                if mov.get('produto_id') == produto['id'] and data_mov_str and data_mov_str < data_inicio:
                    quantidade = float(mov.get('quantidade', 0) or 0)
                    preco_unit = float(mov.get('preco_unitario', 0) or 0)
                    
                    if mov.get('tipo') == 'entrada':
                        dados_relatorio['inicial_qtd'] += quantidade
                        if preco_unit > 0:
                            dados_relatorio['inicial_valor'] += quantidade * preco_unit
                            qtd_custo_inicial += quantidade
                        print(f"  -> [INICIAL] Data: {data_mov_str}, Tipo: Entrada, Qtd: {quantidade}. Saldo Qtd: {dados_relatorio['inicial_qtd']}, Saldo Valor: {dados_relatorio['inicial_valor']:.2f}")
                    else: # Saída
                        custo_medio_ate_entao = dados_relatorio['inicial_valor'] / qtd_custo_inicial if qtd_custo_inicial > 0 else 0
                        dados_relatorio['inicial_qtd'] -= quantidade
                        dados_relatorio['inicial_valor'] -= quantidade * custo_medio_ate_entao
                        qtd_custo_inicial -= quantidade
                        print(f"  -> [INICIAL] Data: {data_mov_str}, Tipo: Saída, Qtd: {quantidade} ao CMP de {custo_medio_ate_entao:.2f}. Saldo Qtd: {dados_relatorio['inicial_qtd']}, Saldo Valor: {dados_relatorio['inicial_valor']:.2f}")

            dados_relatorio['inicial_cmp'] = dados_relatorio['inicial_valor'] / dados_relatorio['inicial_qtd'] if dados_relatorio['inicial_qtd'] > 0 else 0
            print(f"--- Saldo Inicial Finalizado: Qtd={dados_relatorio['inicial_qtd']}, Valor={dados_relatorio['inicial_valor']:.2f}, CMP={dados_relatorio['inicial_cmp']:.2f}")

            valor_corrente = dados_relatorio['inicial_valor']
            qtd_custo_corrente = qtd_custo_inicial
            print(f"--- Calculando Movimentações do Período (iniciando com Valor Corrente: {valor_corrente:.2f}, Qtd Custo: {qtd_custo_corrente})...")
            for mov in movimentacoes:
                data_mov_str = mov.get('created_at', '')[:10]
                if mov.get('produto_id') == produto['id'] and data_mov_str and data_inicio <= data_mov_str <= data_fim:
                    quantidade = float(mov.get('quantidade', 0) or 0)
                    preco_unit = float(mov.get('preco_unitario', 0) or 0)
                    if mov.get('tipo') == 'entrada':
                        dados_relatorio['entradas_qtd'] += quantidade
                        dados_relatorio['entradas_valor'] += quantidade * preco_unit
                        if preco_unit > 0:
                            valor_corrente += quantidade * preco_unit
                            qtd_custo_corrente += quantidade
                        print(f"  -> [PERÍODO] Data: {data_mov_str}, Tipo: Entrada, Qtd: {quantidade}. Valor Corrente: {valor_corrente:.2f}")
                    else: # Saída
                        custo_medio_no_momento_da_saida = valor_corrente / qtd_custo_corrente if qtd_custo_corrente > 0 else 0
                        dados_relatorio['saidas_qtd'] += quantidade
                        dados_relatorio['saidas_valor'] += quantidade * custo_medio_no_momento_da_saida
                        valor_corrente -= quantidade * custo_medio_no_momento_da_saida
                        qtd_custo_corrente -= quantidade
                        print(f"  -> [PERÍODO] Data: {data_mov_str}, Tipo: Saída, Qtd: {quantidade} ao CMP de {custo_medio_no_momento_da_saida:.2f}. Valor Corrente: {valor_corrente:.2f}")
            
            dados_relatorio['entradas_cmp'] = dados_relatorio['entradas_valor'] / dados_relatorio['entradas_qtd'] if dados_relatorio['entradas_qtd'] > 0 else 0
            dados_relatorio['saidas_cmp'] = dados_relatorio['saidas_valor'] / dados_relatorio['saidas_qtd'] if dados_relatorio['saidas_qtd'] > 0 else 0
            
            dados_relatorio['final_qtd'] = dados_relatorio['inicial_qtd'] + dados_relatorio['entradas_qtd'] - dados_relatorio['saidas_qtd']
            dados_relatorio['final_valor'] = dados_relatorio['inicial_valor'] + dados_relatorio['entradas_valor'] - dados_relatorio['saidas_valor']
            dados_relatorio['final_cmp'] = dados_relatorio['final_valor'] / dados_relatorio['final_qtd'] if dados_relatorio['final_qtd'] > 0 else 0
            
            resultado_final.append(dados_relatorio)
        
        print(f"--- FINALIZANDO: {len(resultado_final)} produtos processados.")
        return resultado_final
    except Exception as e:
        print(f"\n!!!!!! ERRO CRÍTICO DENTRO DA FUNÇÃO: {e} !!!!!!\n")
        return []

@app.route('/relatorios/posicao_estoque')
def pagina_posicao_estoque():
    if 'user_id' not in session or session.get('user_role') != 'gestor':
        return redirect(url_for('login'))

    todos_produtos = supabase.table('produtos').select('id, descricao, codigo_sustentare, codigo_valor').order('descricao').execute().data
    todas_categorias = supabase.table('categorias').select('id, nome_categoria').order('nome_categoria').execute().data

    filtros = {
        'data_inicio': request.args.get('data_inicio', datetime.now().replace(day=1).strftime('%Y-%m-%d')),
        'data_fim': request.args.get('data_fim', datetime.now().strftime('%Y-%m-%d')),
        'categorias_ids': request.args.getlist('categorias_ids', type=int),
        'produtos_ids': request.args.getlist('produtos_ids', type=int),
        'sort_by': request.args.get('sort_by', 'descricao'),
        'order': request.args.get('order', 'asc')
    }
    
    dados_posicao = calcular_posicao_estoque_data(filtros['data_inicio'], filtros['data_fim'], filtros['categorias_ids'], filtros['produtos_ids'])
    
    is_reverse = filtros['order'] == 'desc'
    def sort_key(item):
        valor = item.get(filtros['sort_by'], 0)
        if isinstance(valor, (int, float)): return valor
        return str(valor).lower()
    dados_posicao.sort(key=sort_key, reverse=is_reverse)

    return render_template('posicao_estoque.html', 
                           dados_posicao=dados_posicao, 
                           filtros=filtros,
                           todas_categorias=todas_categorias,
                           todos_produtos=todos_produtos)

@app.route('/inventario/iniciar')
def pagina_iniciar_inventario():
    if 'user_id' not in session or session.get('user_role') != 'gestor':
        flash('Acesso negado: você não tem permissão para esta área.', 'danger')
        return redirect(url_for('pagina_inicial'))
    
    try:
        # Busca todos os produtos para exibir na lista de seleção do inventário
        response_produtos = supabase.table('produtos').select('id, descricao, codigo_sustentare').order('descricao').execute()
        todos_produtos = response_produtos.data
    except Exception as e:
        flash(f'Erro ao carregar a lista de produtos: {e}', 'danger')
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
        dados_inventario = {
            'usuario_iniciou_id': session['user_id']
            # O status padrão 'Em Andamento' já é definido pelo Supabase
        }
        
        response_insert = supabase.table('inventarios').insert(dados_inventario).execute()
        inventario_criado = response_insert.data[0]
        inventario_id = inventario_criado['id']

        # --- CORREÇÃO FINAL APLICADA AQUI ---
        # Usando o nome da coluna correto ('quantidade_teorica')
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
        # Melhoria de UX: Redireciona para a lista de inventários em andamento
        return redirect(url_for('pagina_inventarios_em_andamento'))

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

@app.route('/inventario/contagem/<int:inventario_id>')
def pagina_contagem_inventario(inventario_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    response_inventario = supabase.table('inventarios').select('*').eq('id', inventario_id).single().execute()
    inventario = response_inventario.data

    # CORREÇÃO: Aprimorando o select para buscar os códigos dos produtos
    response_itens = supabase.table('inventario_itens').select(
        '*, produtos(descricao, codigo_sustentare, codigo_valor)'
    ).eq('inventario_id', inventario_id).execute()
    itens_inventario = response_itens.data

    # A lógica de filtro que você já tinha é mantida
    filtro = request.args.get('filtro', 'todos')
    filtered_itens = itens_inventario
    if filtro == 'contados':
        filtered_itens = [item for item in itens_inventario if item['quantidade_contada'] is not None]
    elif filtro == 'nao_contados':
        filtered_itens = [item for item in itens_inventario if item['quantidade_contada'] is None]

    return render_template('contagem_inventario.html', inventario=inventario, itens_inventario=filtered_itens, filtro=filtro)

@app.route('/inventario/salvar_contagem', methods=['POST'])
def salvar_contagem_inventario():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    inventario_id = request.form.get('inventario_id')
    
    try:
        # 1. Busca todos os itens que pertencem a este inventário
        response_itens = supabase.table('inventario_itens').select('id, produto_id').eq('inventario_id', inventario_id).execute()
        itens_do_inventario = response_itens.data

        # 2. Faz um loop por cada item e o ATUALIZA individualmente, se necessário
        for item in itens_do_inventario:
            quantidade_contada_str = request.form.get(f"quantidade_{item['id']}")
            
            # Se um valor foi digitado para este item, atualiza apenas ele
            if quantidade_contada_str and quantidade_contada_str.strip():
                dados_para_atualizar = {
                    'quantidade_contada': float(quantidade_contada_str),
                    'usuario_contou_id': session['user_id']
                }
                # Executa o UPDATE para este item específico, usando seu ID
                supabase.table('inventario_itens').update(dados_para_atualizar).eq('id', item['id']).execute()
        
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

@app.route('/inventario/finalizar/<int:inventario_id>', methods=['POST'])
def finalizar_inventario(inventario_id):
    if 'user_id' not in session or session.get('user_role') != 'gestor':
        return redirect(url_for('login'))

    observacoes = request.form.get('observacoes')
    
    try:
        # 1. Busca todos os itens do inventário para processar as divergências
        itens_inventario = supabase.table('inventario_itens').select('*, produtos(*)').eq('inventario_id', inventario_id).execute().data

        movimentacoes_ajuste = []
        produtos_para_atualizar = []

        for item in itens_inventario:
            qtd_contada_str = item.get('quantidade_contada')
            if qtd_contada_str is None: continue # Ignora itens não contados

            qtd_contada = float(qtd_contada_str)
            qtd_teorica = float(item['quantidade_teorica'])
            diferenca = qtd_contada - qtd_teorica

            if diferenca != 0:
                produto = item['produtos']
                tipo_mov = 'entrada' if diferenca > 0 else 'saida'
                
                custo_medio = float(produto['valor_total_estoque']) / float(produto['quantidade_com_custo']) if float(produto['quantidade_com_custo']) > 0 else 0
                
                # Prepara a movimentação de ajuste com as colunas corretas
                movimentacoes_ajuste.append({
                    'produto_id': produto['id'],
                    'tipo': tipo_mov,
                    'quantidade': abs(diferenca),
                    'usuario_id': session['user_id'],
                    'preco_unitario': custo_medio,
                    'numero_requisicao_manual': f"AJUSTE INVENTÁRIO #{inventario_id}"
                })
                
                # Prepara a atualização do produto
                novo_estoque = float(produto['estoque_atual']) + diferenca
                novo_valor_total = float(produto['valor_total_estoque']) + (diferenca * custo_medio)
                
                produtos_para_atualizar.append({
                    'id': produto['id'],
                    'dados': {
                        'estoque_atual': novo_estoque,
                        'valor_total_estoque': novo_valor_total
                    }
                })

        # Insere todas as movimentações de ajuste de uma vez (mais eficiente)
        if movimentacoes_ajuste:
            supabase.table('movimentacoes').insert(movimentacoes_ajuste).execute()

        # Atualiza todos os produtos de uma vez (mais eficiente)
        for prod_update in produtos_para_atualizar:
            supabase.table('produtos').update(prod_update['dados']).eq('id', prod_update['id']).execute()

        # Finaliza o "cabeçalho" do inventário
        supabase.table('inventarios').update({
            'status': 'Finalizado',
            'data_fim': datetime.now(timezone.utc).isoformat(),
            'usuario_finalizou_id': session['user_id'],
            'observacoes': observacoes
        }).eq('id', inventario_id).execute()

        flash(f'Inventário #{inventario_id} finalizado e estoque ajustado com sucesso!', 'success')
        # Redirecionamento correto para o histórico
        return redirect(url_for('pagina_historico_inventarios'))

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

# ===== Funções Corrigidas para Detalhe de Inventário =====

@app.route('/inventario/detalhes/<int:inventario_id>')
def pagina_detalhe_inventario(inventario_id):
    if 'user_id' not in session or session.get('user_role') != 'gestor':
        flash('Acesso negado.', 'danger')
        return redirect(url_for('pagina_inicial'))

    try:
        response_inv = supabase.table('inventarios').select(
            '*, usuario_iniciou:usuarios!inventarios_usuario_iniciou_id_fkey(nome), usuario_finalizou:usuarios!inventarios_usuario_finalizou_id_fkey(nome)'
        ).eq('id', inventario_id).single().execute()
        inventario = response_inv.data
        
        # CORREÇÃO: Busca os códigos corretos dos produtos
        response_itens = supabase.table('inventario_itens').select('*, produtos(descricao, codigo_sustentare, codigo_valor)').eq('inventario_id', inventario_id).order('id').execute()
        itens_inventario = response_itens.data

    except Exception as e:
        flash(f'Erro ao carregar detalhes do inventário: {e}', 'danger')
        return redirect(url_for('pagina_historico_inventarios'))

    return render_template('detalhe_inventario.html', inventario=inventario, itens_inventario=itens_inventario)

# ROTA CORRIGIDA para um endereço único
@app.route('/relatorios/posicao_estoque/exportar_csv')
def exportar_posicao_estoque_csv():
    if 'user_id' not in session or session.get('user_role') != 'gestor':
        return redirect(url_for('login'))
    
    # Pega os filtros da URL para que o CSV corresponda à tela
    filtros = {
        'data_inicio': request.args.get('data_inicio', datetime.now().replace(day=1).strftime('%Y-%m-%d')),
        'data_fim': request.args.get('data_fim', datetime.now().strftime('%Y-%m-%d')),
        'categorias_ids': request.args.getlist('categorias_ids', type=int),
        'produtos_ids': request.args.getlist('produtos_ids', type=int)
    }
    
    # Usa a mesma função "motor" para garantir consistência
    dados_posicao = calcular_posicao_estoque_data(filtros['data_inicio'], filtros['data_fim'], filtros['categorias_ids'], filtros['produtos_ids'])
    
    si = io.StringIO()
    cw = csv.writer(si, delimiter=';')
    
    # Cria o cabeçalho complexo
    cabecalho1 = ['Produto', '', '', 'Estoque Inicial', '', '', 'Entradas', '', '', 'Saidas', '', '', 'Estoque Final', '', '']
    cabecalho2 = ['ID', 'Cód. Sustentare', 'Descrição', 'Qtd', 'CMP', 'Valor', 'Qtd', 'CMP', 'Valor', 'Qtd', 'CMP', 'Valor', 'Qtd', 'CMP', 'Valor']
    cw.writerow(cabecalho1)
    cw.writerow(cabecalho2)
    
    # Escreve os dados
    for item in dados_posicao:
        linha = [
            item.get('id'), item.get('codigo_sustentare'), item.get('descricao'),
            "{:.2f}".format(item.get('inicial_qtd', 0)), "{:.2f}".format(item.get('inicial_cmp', 0)), "{:.2f}".format(item.get('inicial_valor', 0)),
            "{:.2f}".format(item.get('entradas_qtd', 0)), "{:.2f}".format(item.get('entradas_cmp', 0)), "{:.2f}".format(item.get('entradas_valor', 0)),
            "{:.2f}".format(item.get('saidas_qtd', 0)), "{:.2f}".format(item.get('saidas_cmp', 0)), "{:.2f}".format(item.get('saidas_valor', 0)),
            "{:.2f}".format(item.get('final_qtd', 0)), "{:.2f}".format(item.get('final_cmp', 0)), "{:.2f}".format(item.get('final_valor', 0)),
        ]
        cw.writerow(linha)
        
    csv_bytes = si.getvalue().encode('utf-8-sig')
    output = make_response(csv_bytes)
    output.headers["Content-Disposition"] = "attachment; filename=valoracao_de_estoque.csv"
    output.headers["Content-type"] = "text/csv; charset=utf-8-sig"
    return output

@app.route('/inventario/detalhes/exportar_csv')
def exportar_detalhe_inventario_csv():
    if 'user_id' not in session or session.get('user_role') != 'gestor':
        return redirect(url_for('pagina_inicial'))

    inventario_id = request.args.get('inventario_id')
    if not inventario_id:
        flash('ID do inventário não fornecido.', 'danger')
        return redirect(url_for('pagina_historico_inventarios'))

    try:
        # CORREÇÃO: Busca os códigos corretos dos produtos
        response_itens = supabase.table('inventario_itens').select('*, produtos(descricao, codigo_sustentare, codigo_valor)').eq('inventario_id', inventario_id).order('id').execute()
        itens_inventario = response_itens.data

        si = io.StringIO()
        writer = csv.writer(si, delimiter=';')
        
        # CORREÇÃO: Cabeçalho do CSV atualizado
        writer.writerow(['ID Produto', 'Cód. Sustentare', 'Cód. Valor', 'Descrição', 'Qtd. Teórica', 'Qtd. Contada', 'Diferença'])
        
        for item in itens_inventario:
            produto = item.get('produtos', {})
            qtd_contada = item.get('quantidade_contada')
            qtd_teorica = item.get('quantidade_teorica')
            diferenca = ''
            if qtd_contada is not None and qtd_teorica is not None:
                diferenca = float(qtd_contada) - float(qtd_teorica)

            # CORREÇÃO: Linhas do CSV com os dados corretos
            writer.writerow([
                produto.get('id', 'N/A'),
                produto.get('codigo_sustentare', 'N/A'),
                produto.get('codigo_valor', 'N/A'),
                produto.get('descricao', 'N/A'),
                qtd_teorica,
                qtd_contada if qtd_contada is not None else 'NÃO CONTADO',
                diferenca
            ])
        
        csv_bytes = si.getvalue().encode('utf-8-sig')
        output = make_response(csv_bytes)
        output.headers["Content-Disposition"] = f"attachment;filename=inventario_{inventario_id}_detalhes.csv"
        output.headers["Content-type"] = "text/csv; charset=utf-8-sig"
        return output

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