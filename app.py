import os
import json
import fitz
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, jsonify, Response
from sqlalchemy import func
import pandas as pd
from datetime import datetime, date
from models import db, Cliente, Empreendimento, Usuario, Material, PerfilUsuario, StatusCliente, TemperaturaLead, EstadoCivil, Agendamento, Atividade, TipoAtividade, ExemploIA
from functools import wraps
from werkzeug.utils import secure_filename
from markupsafe import escape, Markup
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///halley_crm.db')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'uma-outra-chave-muito-segura')
basedir = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(basedir, 'static/uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

try:
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
except Exception as e:
    print(f"AVISO: Chave de API do Google não encontrada ou inválida. Erro: {e}")
    pass

db.init_app(app)

@app.template_filter('nl2br')
def nl2br_filter(s):
    return Markup(escape(s).replace('\n', '<br>\n'))

with app.app_context():
    db.create_all()

# --- DECORATORS E FUNÇÕES AUXILIARES ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario_id' not in session:
            flash('Por favor, faça login para acessar esta página.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def verificar_permissao_cliente(id_cliente):
    cliente = db.get_or_404(Cliente, id_cliente)
    if session.get('usuario_perfil') != 'Admin' and cliente.proprietario_id != session.get('usuario_id'):
        flash('Você não tem permissão para acessar este cliente.', 'danger')
        return None
    return cliente

def salvar_exemplo_ia(texto_original, form_data):
    if not texto_original: return
    dados_corrigidos = {
        "nome": form_data.get('nome', ''), "status": form_data.get('status', ''),
        "endereco": form_data.get('endereco', ''), "descricao": form_data.get('descricao', ''),
        "previsao_entrega": form_data.get('previsao_entrega', ''), "valor_a_partir_de": form_data.get('valor_a_partir_de', ''),
        "tamanho_apartamentos_planta": form_data.get('tamanho_apartamentos_planta', ''),
        "vagas_garagem": form_data.get('vagas_garagem', ''), "quantidade_torres": form_data.get('quantidade_torres', ''),
        "subsolos": form_data.get('subsolos', ''), "andares": form_data.get('andares', ''),
        "campanha_promocional": form_data.get('campanha_promocional', '')
    }
    novo_exemplo = ExemploIA(
        texto_documento=texto_original,
        json_resultado_corrigido=json.dumps(dados_corrigidos, ensure_ascii=False, indent=2)
    )
    db.session.add(novo_exemplo)
    db.session.commit()
    flash('Obrigado! A IA usará este exemplo para aprender e melhorar no futuro.', 'info')

# --- ROTAS DE AUTENTICAÇÃO ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        usuario = db.session.execute(db.select(Usuario).filter_by(email=email)).scalar_one_or_none()
        if usuario and usuario.ativo and usuario.verificar_senha(senha):
            session['usuario_id'] = usuario.id
            session['usuario_nome'] = usuario.nome
            session['usuario_perfil'] = usuario.perfil.value
            return redirect(url_for('dashboard'))
        else:
            flash('Email, senha ou permissão inválidos.', 'danger')
    return render_template('login.html')

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        email = request.form.get('email')
        if not email:
            flash('O campo de email é obrigatório.', 'danger')
            return render_template('registro.html')
        usuario_existente = db.session.execute(db.select(Usuario).filter_by(email=email)).scalar_one_or_none()
        if usuario_existente:
            flash('Este email já está cadastrado.', 'danger')
            return redirect(url_for('login'))
        novo_usuario = Usuario(nome=request.form.get('nome'), email=email, ativo=True)
        total_usuarios = db.session.execute(db.select(func.count(Usuario.id))).scalar_one()
        if total_usuarios == 0:
            novo_usuario.perfil = PerfilUsuario.ADMIN
        else:
            novo_usuario.perfil = PerfilUsuario.CORRETOR
        novo_usuario.definir_senha(request.form['senha'])
        db.session.add(novo_usuario)
        db.session.commit()
        flash('Registro realizado com sucesso! Faça seu login.', 'success')
        return redirect(url_for('login'))
    return render_template('registro.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Você saiu da sua conta.', 'info')
    return redirect(url_for('login'))

# --- ROTAS PRINCIPAIS E DE USUÁRIOS ---
@app.route('/')
@login_required
def dashboard():
    if session['usuario_perfil'] == 'Admin':
        total_clientes = db.session.execute(db.select(func.count(Cliente.id)).filter_by(descartado=False)).scalar_one()
    else:
        total_clientes = db.session.execute(db.select(func.count(Cliente.id)).filter_by(proprietario_id=session['usuario_id'], descartado=False)).scalar_one()
    total_empreendimentos = db.session.execute(db.select(func.count(Empreendimento.id))).scalar_one()
    query_clientes_recentes = db.select(Cliente).filter_by(descartado=False).order_by(Cliente.id.desc())
    if session['usuario_perfil'] != 'Admin':
        query_clientes_recentes = query_clientes_recentes.filter_by(proprietario_id=session['usuario_id'])
    ultimos_clientes = db.session.execute(query_clientes_recentes.limit(5)).scalars().all()
    ultimos_empreendimentos = db.session.execute(db.select(Empreendimento).order_by(Empreendimento.id.desc()).limit(5)).scalars().all()
    return render_template('dashboard.html', total_clientes=total_clientes, total_empreendimentos=total_empreendimentos, ultimos_clientes=ultimos_clientes, ultimos_empreendimentos=ultimos_empreendimentos)

@app.route('/usuarios')
@login_required
def lista_usuarios():
    if session.get('usuario_perfil') != 'Admin':
        flash('Você não tem permissão para acessar esta página.', 'danger')
        return redirect(url_for('dashboard'))
    usuarios = db.session.execute(db.select(Usuario).order_by(Usuario.nome)).scalars().all()
    return render_template('usuarios.html', usuarios=usuarios)

# --- ROTAS DE CLIENTES ---
@app.route('/clientes')
@login_required
def lista_clientes():
    termo_busca = request.args.get('termo_busca', '')
    status_busca = request.args.get('status_busca', '')
    query = db.select(Cliente).filter_by(descartado=False)
    if session['usuario_perfil'] != 'Admin':
        query = query.filter(Cliente.proprietario_id == session['usuario_id'])
    if termo_busca:
        query = query.filter(Cliente.nome_completo.ilike(f'%{termo_busca}%'))
    if status_busca:
        query = query.filter(Cliente.status == StatusCliente[status_busca])
    lista_de_clientes = db.session.execute(query.order_by(Cliente.nome_completo)).scalars().all()
    return render_template('index.html', clientes=lista_de_clientes, termo_busca=termo_busca, status_busca=status_busca, status_options=StatusCliente)

@app.route('/cliente/<int:id>')
@login_required
def detalhes_cliente(id):
    cliente = verificar_permissao_cliente(id)
    if not cliente: return redirect(url_for('lista_clientes'))
    ids_interesse = [emp.id for emp in cliente.empreendimentos_interesse]
    empreendimentos_disponiveis = db.session.execute(db.select(Empreendimento).filter(Empreendimento.id.not_in(ids_interesse))).scalars().all()
    return render_template('detalhes_cliente.html', cliente=cliente, empreendimentos_disponiveis=empreendimentos_disponiveis, tipos_atividade=TipoAtividade, Atividade=Atividade)

@app.route('/cliente/adicionar', methods=['GET', 'POST'])
@login_required
def adicionar_cliente():
    if request.method == 'POST':
        if not request.form.get('ddd_pessoal') or not request.form.get('telefone_pessoal'):
            flash('O DDD e o Telefone Pessoal são obrigatórios.', 'danger')
            return render_template('cliente_form.html', form_data=request.form, estado_civil_options=EstadoCivil, status_options=StatusCliente, temperatura_options=TemperaturaLead)
        cpf = request.form.get('cpf') if request.form.get('cpf') else None
        email = request.form.get('email') if request.form.get('email') else None
        email_comercial = request.form.get('email_comercial') if request.form.get('email_comercial') else None
        if cpf and db.session.execute(db.select(Cliente).filter_by(cpf=cpf)).scalar_one_or_none():
            flash(f'Erro: O CPF {cpf} já está cadastrado.', 'danger')
            return render_template('cliente_form.html', form_data=request.form, estado_civil_options=EstadoCivil, status_options=StatusCliente, temperatura_options=TemperaturaLead)
        if email and db.session.execute(db.select(Cliente).filter_by(email=email)).scalar_one_or_none():
            flash(f'Erro: O Email Pessoal {email} já está cadastrado.', 'danger')
            return render_template('cliente_form.html', form_data=request.form, estado_civil_options=EstadoCivil, status_options=StatusCliente, temperatura_options=TemperaturaLead)
        if email_comercial and db.session.execute(db.select(Cliente).filter_by(email_comercial=email_comercial)).scalar_one_or_none():
            flash(f'Erro: O Email Comercial {email_comercial} já está cadastrado.', 'danger')
            return render_template('cliente_form.html', form_data=request.form, estado_civil_options=EstadoCivil, status_options=StatusCliente, temperatura_options=TemperaturaLead)
        data_nasc_obj = datetime.strptime(request.form.get('data_nascimento'), '%Y-%m-%d').date() if request.form.get('data_nascimento') else None
        novo_cliente = Cliente(
            proprietario_id=session['usuario_id'],
            nome_completo=request.form.get('nome_completo'), data_nascimento=data_nasc_obj, cpf=cpf, rg=request.form.get('rg'), 
            profissao=request.form.get('profissao'), email=email, email_comercial=email_comercial,
            ddd_pessoal=request.form.get('ddd_pessoal'), telefone_pessoal=request.form.get('telefone_pessoal'),
            ddd_pessoal_2=request.form.get('ddd_pessoal_2'), telefone_pessoal_2=request.form.get('telefone_pessoal_2'),
            ddd_residencial=request.form.get('ddd_residencial'), telefone_residencial=request.form.get('telefone_residencial'),
            ddd_comercial=request.form.get('ddd_comercial'), telefone_comercial=request.form.get('telefone_comercial'),
            cep_residencial=request.form.get('cep_residencial'), logradouro_residencial=request.form.get('logradouro_residencial'),
            numero_residencial=request.form.get('numero_residencial'), complemento_residencial=request.form.get('complemento_residencial'),
            bairro_residencial=request.form.get('bairro_residencial'), cidade_residencial=request.form.get('cidade_residencial'),
            estado_residencial=request.form.get('estado_residencial'),
            empresa_cliente=request.form.get('empresa_cliente'),
            endereco_comercial_cliente=request.form.get('endereco_comercial_cliente'),
            estado_civil=EstadoCivil[request.form['estado_civil']] if request.form.get('estado_civil') else None,
            nome_conjuge=request.form.get('nome_conjuge'), 
            cpf_conjuge=request.form.get('cpf_conjuge') if request.form.get('cpf_conjuge') else None,
            profissao_conjuge=request.form.get('profissao_conjuge'),
            email_conjuge=request.form.get('email_conjuge'), 
            email_conjuge_comercial=request.form.get('email_conjuge_comercial'),
            ddd_conjuge=request.form.get('ddd_conjuge'),
            telefone_conjuge=request.form.get('telefone_conjuge'), 
            empresa_conjuge=request.form.get('empresa_conjuge'),
            endereco_comercial_conjuge=request.form.get('endereco_comercial_conjuge'),
            origem_lead=request.form.get('origem_lead'), temperatura=TemperaturaLead[request.form['temperatura']] if request.form.get('temperatura') else None,
            status=StatusCliente[request.form['status']] if request.form.get('status') else None, valor_imovel_buscado=request.form.get('valor_imovel_buscado'),
            faixa_renda=request.form.get('faixa_renda'), observacoes=request.form.get('observacoes')
        )
        db.session.add(novo_cliente)
        db.session.commit()
        flash('Cliente adicionado com sucesso!', 'success')
        return redirect(url_for('lista_clientes'))
    return render_template('cliente_form.html', estado_civil_options=EstadoCivil, status_options=StatusCliente, temperatura_options=TemperaturaLead)

@app.route('/cliente/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_cliente(id):
    cliente = verificar_permissao_cliente(id)
    if not cliente: return redirect(url_for('lista_clientes'))
    if request.method == 'POST':
        if not request.form.get('ddd_pessoal') or not request.form.get('telefone_pessoal'):
            flash('O DDD e o Telefone Pessoal são obrigatórios.', 'danger')
            return render_template('cliente_form.html', cliente=cliente, estado_civil_options=EstadoCivil, status_options=StatusCliente, temperatura_options=TemperaturaLead)
        cliente.nome_completo = request.form.get('nome_completo')
        cliente.data_nascimento = datetime.strptime(request.form.get('data_nascimento'), '%Y-%m-%d').date() if request.form.get('data_nascimento') else None
        cliente.cpf = request.form.get('cpf') if request.form.get('cpf') else None
        cliente.rg = request.form.get('rg') if request.form.get('rg') else None
        cliente.profissao = request.form.get('profissao')
        cliente.email = request.form.get('email') if request.form.get('email') else None
        cliente.email_comercial = request.form.get('email_comercial') if request.form.get('email_comercial') else None
        cliente.ddd_pessoal = request.form.get('ddd_pessoal')
        cliente.telefone_pessoal = request.form.get('telefone_pessoal')
        cliente.ddd_pessoal_2 = request.form.get('ddd_pessoal_2')
        cliente.telefone_pessoal_2 = request.form.get('telefone_pessoal_2')
        cliente.ddd_residencial = request.form.get('ddd_residencial')
        cliente.telefone_residencial = request.form.get('telefone_residencial')
        cliente.ddd_comercial = request.form.get('ddd_comercial')
        cliente.telefone_comercial = request.form.get('telefone_comercial')
        cliente.cep_residencial = request.form.get('cep_residencial')
        cliente.logradouro_residencial = request.form.get('logradouro_residencial')
        cliente.numero_residencial = request.form.get('numero_residencial')
        cliente.complemento_residencial = request.form.get('complemento_residencial')
        cliente.bairro_residencial = request.form.get('bairro_residencial')
        cliente.cidade_residencial = request.form.get('cidade_residencial')
        cliente.estado_residencial = request.form.get('estado_residencial')
        cliente.empresa_cliente = request.form.get('empresa_cliente')
        cliente.endereco_comercial_cliente = request.form.get('endereco_comercial_cliente')
        estado_civil_form = request.form.get('estado_civil')
        cliente.estado_civil = EstadoCivil[estado_civil_form] if estado_civil_form else None
        cliente.nome_conjuge = request.form.get('nome_conjuge')
        cliente.cpf_conjuge = request.form.get('cpf_conjuge') if request.form.get('cpf_conjuge') else None
        cliente.profissao_conjuge = request.form.get('profissao_conjuge')
        cliente.email_conjuge = request.form.get('email_conjuge')
        cliente.email_conjuge_comercial = request.form.get('email_conjuge_comercial')
        cliente.ddd_conjuge = request.form.get('ddd_conjuge')
        cliente.telefone_conjuge = request.form.get('telefone_conjuge')
        cliente.empresa_conjuge = request.form.get('empresa_conjuge')
        cliente.endereco_comercial_conjuge = request.form.get('endereco_comercial_conjuge')
        cliente.origem_lead = request.form.get('origem_lead')
        temperatura_form = request.form.get('temperatura')
        cliente.temperatura = TemperaturaLead[temperatura_form] if temperatura_form else None
        status_form = request.form.get('status')
        cliente.status = StatusCliente[status_form] if status_form else None
        cliente.valor_imovel_buscado = request.form.get('valor_imovel_buscado')
        cliente.faixa_renda = request.form.get('faixa_renda')
        cliente.observacoes = request.form.get('observacoes')
        db.session.commit()
        flash('Cliente atualizado com sucesso!', 'success')
        return redirect(url_for('detalhes_cliente', id=cliente.id))
    return render_template('cliente_form.html', cliente=cliente, estado_civil_options=EstadoCivil, status_options=StatusCliente, temperatura_options=TemperaturaLead)

# --- ROTAS DE DESCARTE DE CLIENTE ---
@app.route('/cliente/<int:id>/descartar', methods=['POST'])
@login_required
def descartar_cliente(id):
    cliente = verificar_permissao_cliente(id)
    if not cliente: return redirect(url_for('lista_clientes'))
    cliente.descartado = True
    db.session.commit()
    flash(f'Cliente "{cliente.nome_completo}" movido para a lixeira.', 'info')
    return redirect(url_for('lista_clientes'))

@app.route('/clientes/descartados')
@login_required
def lista_clientes_descartados():
    if session.get('usuario_perfil') != 'Admin':
        flash('Você não tem permissão para acessar esta página.', 'danger')
        return redirect(url_for('dashboard'))
    clientes_descartados = db.session.execute(db.select(Cliente).filter_by(descartado=True).order_by(Cliente.nome_completo)).scalars().all()
    return render_template('descartados.html', clientes=clientes_descartados)

@app.route('/cliente/<int:id>/restaurar', methods=['GET', 'POST'])
@login_required
def restaurar_cliente(id):
    if session.get('usuario_perfil') != 'Admin':
        return redirect(url_for('dashboard'))
    cliente = db.get_or_404(Cliente, id)
    if request.method == 'POST':
        novo_proprietario_id = request.form.get('novo_proprietario_id')
        if novo_proprietario_id:
            cliente.descartado = False
            cliente.proprietario_id = novo_proprietario_id
            db.session.commit()
            flash(f'Cliente "{cliente.nome_completo}" restaurado e atribuído com sucesso!', 'success')
        else:
            flash('Você precisa selecionar um usuário para reatribuir o cliente.', 'danger')
        return redirect(url_for('lista_clientes_descartados'))
    usuarios_disponiveis = db.session.execute(db.select(Usuario).filter_by(ativo=True).order_by(Usuario.nome)).scalars().all()
    return render_template('restaurar_cliente.html', cliente=cliente, usuarios_disponiveis=usuarios_disponiveis)

@app.route('/cliente/<int:id>/deletar_permanente', methods=['POST'])
@login_required
def deletar_cliente_permanente(id):
    if session.get('usuario_perfil') != 'Admin':
        return redirect(url_for('dashboard'))
    cliente = db.get_or_404(Cliente, id)
    db.session.delete(cliente)
    db.session.commit()
    flash(f'Cliente "{cliente.nome_completo}" deletado permanentemente.', 'danger')
    return redirect(url_for('lista_clientes_descartados'))

# --- ROTAS DE ATIVIDADES ---
@app.route('/cliente/<int:cliente_id>/adicionar_atividade', methods=['POST'])
@login_required
def adicionar_atividade(cliente_id):
    cliente = verificar_permissao_cliente(cliente_id)
    if not cliente: return redirect(url_for('lista_clientes'))
    tipo_str = request.form.get('tipo')
    resumo = request.form.get('resumo')
    if tipo_str and resumo:
        nova_atividade = Atividade(tipo=TipoAtividade[tipo_str], resumo=resumo, cliente_id=cliente_id, usuario_id=session['usuario_id'])
        db.session.add(nova_atividade)
        db.session.commit()
        flash('Atividade registrada com sucesso!', 'success')
    else:
        flash('Erro ao registrar atividade. Verifique os campos.', 'danger')
    return redirect(url_for('detalhes_cliente', id=cliente_id))

@app.route('/atividade/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_atividade(id):
    atividade = db.get_or_404(Atividade, id)
    if atividade.usuario_id != session['usuario_id'] and session.get('usuario_perfil') != 'Admin':
        flash('Você não tem permissão para editar esta atividade.', 'danger')
        return redirect(url_for('detalhes_cliente', id=atividade.cliente_id))
    if request.method == 'POST':
        atividade.tipo = TipoAtividade[request.form['tipo']]
        atividade.resumo = request.form['resumo']
        db.session.commit()
        flash('Atividade atualizada com sucesso!', 'success')
        return redirect(url_for('detalhes_cliente', id=atividade.cliente_id))
    return render_template('atividade_form.html', atividade=atividade, tipos_atividade=TipoAtividade)

@app.route('/atividade/<int:id>/deletar', methods=['POST'])
@login_required
def deletar_atividade(id):
    atividade = db.get_or_404(Atividade, id)
    cliente_id = atividade.cliente_id
    if atividade.usuario_id != session['usuario_id'] and session.get('usuario_perfil') != 'Admin':
        flash('Você não tem permissão para deletar esta atividade.', 'danger')
        return redirect(url_for('detalhes_cliente', id=cliente_id))
    db.session.delete(atividade)
    db.session.commit()
    flash('Atividade deletada com sucesso.', 'info')
    return redirect(url_for('detalhes_cliente', id=cliente_id))


# --- ROTAS DE INTERESSES E IA ---
@app.route('/cliente/<int:cliente_id>/adicionar_interesse', methods=['POST'])
@login_required
def adicionar_interesse(cliente_id):
    cliente = verificar_permissao_cliente(cliente_id)
    if not cliente: return redirect(url_for('lista_clientes'))
    empreendimento_id = request.form.get('empreendimento_id')
    if empreendimento_id:
        empreendimento = db.get_or_404(Empreendimento, empreendimento_id)
        if empreendimento not in cliente.empreendimentos_interesse:
            cliente.empreendimentos_interesse.append(empreendimento)
            db.session.commit()
            flash(f'Interesse em "{empreendimento.nome}" adicionado com sucesso!', 'success')
    return redirect(url_for('detalhes_cliente', id=cliente_id))

@app.route('/cliente/<int:cliente_id>/remover_interesse/<int:empreendimento_id>', methods=['POST'])
@login_required
def remover_interesse(cliente_id, empreendimento_id):
    cliente = verificar_permissao_cliente(cliente_id)
    if not cliente: return redirect(url_for('lista_clientes'))
    empreendimento = db.get_or_404(Empreendimento, empreendimento_id)
    if empreendimento in cliente.empreendimentos_interesse:
        cliente.empreendimentos_interesse.remove(empreendimento)
        db.session.commit()
        flash(f'Interesse em "{empreendimento.nome}" removido.', 'info')
    return redirect(url_for('detalhes_cliente', id=cliente_id))

@app.route('/cliente/<int:cliente_id>/sugerir_ia', methods=['POST'])
@login_required
def sugerir_empreendimento_ia(cliente_id):
    cliente = verificar_permissao_cliente(cliente_id)
    if not cliente: return redirect(url_for('lista_clientes'))
    ids_interesse = [emp.id for emp in cliente.empreendimentos_interesse]
    empreendimentos_disponiveis = db.session.execute(db.select(Empreendimento).filter(Empreendimento.id.not_in(ids_interesse))).scalars().all()
    prompt = f"Analisando o Perfil do Cliente: - Nome: {cliente.nome_completo}, Status: {cliente.status.value}, Profissão: {cliente.profissao}, Renda: {cliente.faixa_renda}, Valor Buscado: {cliente.valor_imovel_buscado}, Estado Civil: {cliente.estado_civil.value if cliente.estado_civil else ''}, Observações: {cliente.observacoes} --- Com base neste perfil, sugira os 3 empreendimentos mais adequados da lista abaixo, justificando brevemente. Empreendimentos Disponíveis: "
    if not empreendimentos_disponiveis: prompt += "Nenhum."
    else:
        for emp in empreendimentos_disponiveis:
            prompt += f"- {emp.nome}: {emp.descricao}\n"
    sugestao_gerada = "Não foi possível gerar uma sugestão."
    try:
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        response = model.generate_content(prompt)
        sugestao_gerada = response.text
    except Exception as e:
        flash(f"Não foi possível contatar a IA. Erro: {e}", "danger")
    flash(Markup(sugestao_gerada.replace('\n', '<br>')), 'info')
    return redirect(url_for('detalhes_cliente', id=cliente_id))

# --- ROTAS DE EMPREENDIMENTOS ---
@app.route('/empreendimentos')
@login_required
def pagina_empreendimentos():
    lista_de_empreendimentos = db.session.execute(db.select(Empreendimento).order_by(Empreendimento.nome)).scalars().all()
    return render_template('empreendimentos_lista.html', empreendimentos=lista_de_empreendimentos)

@app.route('/empreendimento/<int:id>')
@login_required
def detalhes_empreendimento(id):
    empreendimento = db.get_or_404(Empreendimento, id)
    return render_template('detalhes_empreendimento.html', empreendimento=empreendimento)

@app.route('/empreendimento/adicionar', methods=['GET', 'POST'])
@login_required
def adicionar_empreendimento():
    if request.method == 'POST':
        # 1. Cria o objeto do empreendimento com os dados de texto
        publico = 'publico' in request.form
        prazo_entrega_obj = datetime.strptime(request.form.get('prazo_entrega'), '%Y-%m-%d').date() if request.form.get('prazo_entrega') else None
        
        novo_empreendimento = Empreendimento(
            nome=request.form['nome'],
            status=request.form.get('status'),
            endereco=request.form.get('endereco'),
            descricao=request.form.get('descricao'),
            publico=publico,
            prazo_entrega=prazo_entrega_obj,
            previsao_entrega=request.form.get('previsao_entrega'),
            valor_medio_unidades=request.form.get('valor_medio_unidades'),
            valor_a_partir_de=request.form.get('valor_a_partir_de'),
            tamanho_apartamentos_planta=request.form.get('tamanho_apartamentos_planta'),
            vagas_garagem=request.form.get('vagas_garagem'),
            tamanho_terreno=request.form.get('tamanho_terreno'),
            quantidade_torres=int(request.form.get('quantidade_torres')) if request.form.get('quantidade_torres') else None,
            subsolos=int(request.form.get('subsolos')) if request.form.get('subsolos') else None,
            andares=int(request.form.get('andares')) if request.form.get('andares') else None,
            campanha_promocional=request.form.get('campanha_promocional')
        )
        db.session.add(novo_empreendimento)
        
        # 2. Salva o empreendimento primeiro para obter um ID
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f"Erro ao salvar os dados do empreendimento: {e}", "danger")
            return redirect(url_for('pagina_empreendimentos'))

        # 3. Processa os arquivos que vieram da análise da IA (do campo oculto)
        arquivos_pre_enviados_str = request.form.get('arquivos_ja_enviados')
        if arquivos_pre_enviados_str:
            for item in arquivos_pre_enviados_str.split(','):
                if '|' in item:
                    nome_original, nome_seguro = item.split('|')
                    novo_material = Material(nome_original=nome_original, nome_arquivo_servidor=nome_seguro, empreendimento_id=novo_empreendimento.id)
                    db.session.add(novo_material)
        
        # 4. Processa arquivos novos enviados no formulário principal
        files = request.files.getlist('arquivos')
        for file in files:
            if file and file.filename != '':
                nome_original = file.filename
                nome_seguro = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(nome_original)}"
                caminho_salvar = os.path.join(app.config['UPLOAD_FOLDER'], nome_seguro)
                file.save(caminho_salvar)
                novo_material = Material(nome_original=nome_original, nome_arquivo_servidor=nome_seguro, empreendimento_id=novo_empreendimento.id)
                db.session.add(novo_material)

        # 5. Salva todos os novos registros de materiais no banco
        db.session.commit()
        
        # 6. Salva o exemplo para a IA aprender, se for o caso
        if 'form_originado_ia' in request.form:
            salvar_exemplo_ia(request.form.get('texto_original_ia'), request.form)

        flash('Empreendimento e materiais adicionados com sucesso!', 'success')
        return redirect(url_for('pagina_empreendimentos'))
        
    # Se o método for GET, apenas renderiza o formulário vazio
    return render_template('empreendimento_form.html', dados_extraidos={})

@app.route('/empreendimento/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_empreendimento(id):
    empreendimento = db.get_or_404(Empreendimento, id)
    if request.method == 'POST':
        empreendimento.publico = 'publico' in request.form
        empreendimento.nome = request.form['nome']
        empreendimento.status = request.form.get('status')
        empreendimento.endereco = request.form.get('endereco')
        empreendimento.descricao = request.form.get('descricao')
        empreendimento.prazo_entrega = datetime.strptime(request.form.get('prazo_entrega'), '%Y-%m-%d').date() if request.form.get('prazo_entrega') else None
        empreendimento.previsao_entrega = request.form.get('previsao_entrega')
        empreendimento.valor_medio_unidades = request.form.get('valor_medio_unidades')
        empreendimento.valor_a_partir_de = request.form.get('valor_a_partir_de')
        empreendimento.tamanho_apartamentos_planta = request.form.get('tamanho_apartamentos_planta')
        empreendimento.vagas_garagem = request.form.get('vagas_garagem')
        empreendimento.tamanho_terreno = request.form.get('tamanho_terreno')
        empreendimento.quantidade_torres = int(request.form.get('quantidade_torres')) if request.form.get('quantidade_torres') else None
        empreendimento.subsolos = int(request.form.get('subsolos')) if request.form.get('subsolos') else None
        empreendimento.andares = int(request.form.get('andares')) if request.form.get('andares') else None
        empreendimento.campanha_promocional = request.form.get('campanha_promocional')
        files = request.files.getlist('arquivos')
        for file in files:
            if file and file.filename != '':
                nome_original = file.filename
                nome_seguro = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(nome_original)}"
                caminho_salvar = os.path.join(app.config['UPLOAD_FOLDER'], nome_seguro)
                file.save(caminho_salvar)
                novo_material = Material(nome_original=nome_original, nome_arquivo_servidor=nome_seguro, empreendimento_id=empreendimento.id)
                db.session.add(novo_material)
        db.session.commit()
        flash('Empreendimento atualizado com sucesso!', 'success')
        return redirect(url_for('detalhes_empreendimento', id=empreendimento.id))
    return render_template('empreendimento_form.html', empreendimento=empreendimento, dados_extraidos={})

@app.route('/empreendimento/<int:id>/deletar', methods=['POST'])
@login_required
def deletar_empreendimento(id):
    if session.get('usuario_perfil') != 'Admin':
        flash('Apenas administradores podem deletar empreendimentos.', 'danger')
        return redirect(url_for('pagina_empreendimentos'))
    
    empreendimento = db.get_or_404(Empreendimento, id)
    
    # Deleta os arquivos físicos associados
    for material in empreendimento.materiais:
        try:
            caminho_arquivo = os.path.join(app.config['UPLOAD_FOLDER'], material.nome_arquivo_servidor)
            if os.path.exists(caminho_arquivo):
                os.remove(caminho_arquivo)
        except OSError as e:
            print(f"Erro ao deletar arquivo físico do material {material.id}: {e}")
            flash(f"Erro ao deletar arquivo {material.nome_original}", "danger")

    db.session.delete(empreendimento)
    db.session.commit()
    flash(f'Empreendimento "{empreendimento.nome}" e todos os seus materiais foram deletados permanentemente.', 'success')
    return redirect(url_for('pagina_empreendimentos'))


@app.route('/uploads/<path:filename>')
@login_required
def download_material(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

@app.route('/material/<int:id>/deletar', methods=['POST'])
@login_required
def deletar_material(id):
    material = db.get_or_404(Material, id)
    empreendimento_id = material.empreendimento_id
    if session.get('usuario_perfil') == 'Admin':
        try:
            caminho_arquivo = os.path.join(app.config['UPLOAD_FOLDER'], material.nome_arquivo_servidor)
            if os.path.exists(caminho_arquivo):
                os.remove(caminho_arquivo)
            db.session.delete(material)
            db.session.commit()
            flash('Material deletado com sucesso.', 'info')
        except OSError as e:
            flash(f"Erro ao deletar o arquivo físico: {e}", "danger")
    else:
        flash("Você não tem permissão para deletar materiais.", "danger")
    return redirect(url_for('detalhes_empreendimento', id=empreendimento_id))

@app.route('/material/<int:id>/renomear', methods=['GET', 'POST'])
@login_required
def renomear_material(id):
    material = db.get_or_404(Material, id)
    if request.method == 'POST':
        novo_nome = request.form.get('nome_original')
        if novo_nome:
            material.nome_original = novo_nome
            db.session.commit()
            flash('Nome do material atualizado com sucesso!', 'success')
            return redirect(url_for('detalhes_empreendimento', id=material.empreendimento_id))
    return render_template('material_form.html', material=material)

# --- ROTAS DE AGENDA ---
@app.route('/agenda')
@login_required
def agenda():
    return render_template('agenda.html')

@app.route('/api/agendamentos')
@login_required
def api_agendamentos():
    query = db.select(Agendamento)
    if session['usuario_perfil'] != 'Admin':
        query = query.filter_by(usuario_id=session['usuario_id'])
    meus_agendamentos = db.session.execute(query).scalars().all()
    eventos = []
    for agendamento in meus_agendamentos:
        eventos.append({'title': agendamento.titulo, 'start': agendamento.data_inicio.isoformat(), 'end': agendamento.data_fim.isoformat() if agendamento.data_fim else None, 'url': url_for('detalhes_agendamento', id=agendamento.id), 'color': '#007BFF', 'textColor': 'white'})
    return jsonify(eventos)

@app.route('/agendamento/adicionar', methods=['GET', 'POST'])
@login_required
def adicionar_agendamento():
    if request.method == 'POST':
        data_inicio_str = request.form.get('data_inicio')
        data_fim_str = request.form.get('data_fim')
        data_inicio_obj = datetime.fromisoformat(data_inicio_str) if data_inicio_str else None
        data_fim_obj = datetime.fromisoformat(data_fim_str) if data_fim_str else None
        cliente_id = request.form.get('cliente_id') if request.form.get('cliente_id') else None
        empreendimento_id = request.form.get('empreendimento_id') if request.form.get('empreendimento_id') else None
        novo_evento = Agendamento(
            titulo=request.form['titulo'], data_inicio=data_inicio_obj, data_fim=data_fim_obj,
            descricao=request.form.get('descricao'), usuario_id=session['usuario_id'],
            cliente_id=cliente_id, empreendimento_id=empreendimento_id
        )
        db.session.add(novo_evento)
        db.session.commit()
        flash('Evento adicionado à agenda com sucesso!', 'success')
        return redirect(url_for('agenda'))
    if session['usuario_perfil'] == 'Admin':
        clientes_do_usuario = db.session.execute(db.select(Cliente).order_by(Cliente.nome_completo)).scalars().all()
    else:
        clientes_do_usuario = db.session.execute(db.select(Cliente).filter_by(proprietario_id=session['usuario_id']).order_by(Cliente.nome_completo)).scalars().all()
    todos_empreendimentos = db.session.execute(db.select(Empreendimento).order_by(Empreendimento.nome)).scalars().all()
    return render_template('agendamento_form.html', clientes=clientes_do_usuario, empreendimentos=todos_empreendimentos)

@app.route('/agendamento/<int:id>')
@login_required
def detalhes_agendamento(id):
    agendamento = db.get_or_404(Agendamento, id)
    if session['usuario_perfil'] != 'Admin' and agendamento.usuario_id != session['usuario_id']:
        flash('Você não tem permissão para ver este evento.', 'danger')
        return redirect(url_for('agenda'))
    return render_template('detalhes_agendamento.html', agendamento=agendamento)

@app.route('/agendamento/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_agendamento(id):
    agendamento = db.get_or_404(Agendamento, id)
    if session['usuario_perfil'] != 'Admin' and agendamento.usuario_id != session['usuario_id']:
        flash('Você não tem permissão para editar este evento.', 'danger')
        return redirect(url_for('agenda'))
    if request.method == 'POST':
        agendamento.titulo = request.form['titulo']
        data_inicio_str = request.form.get('data_inicio')
        data_fim_str = request.form.get('data_fim')
        agendamento.data_inicio = datetime.fromisoformat(data_inicio_str) if data_inicio_str else agendamento.data_inicio
        agendamento.data_fim = datetime.fromisoformat(data_fim_str) if data_fim_str else None
        agendamento.cliente_id = request.form.get('cliente_id') if request.form.get('cliente_id') else None
        agendamento.empreendimento_id = request.form.get('empreendimento_id') if request.form.get('empreendimento_id') else None
        agendamento.descricao = request.form.get('descricao')
        db.session.commit()
        flash('Evento atualizado com sucesso!', 'success')
        return redirect(url_for('detalhes_agendamento', id=id))
    if session['usuario_perfil'] == 'Admin':
        clientes_do_usuario = db.session.execute(db.select(Cliente).order_by(Cliente.nome_completo)).scalars().all()
    else:
        clientes_do_usuario = db.session.execute(db.select(Cliente).filter_by(proprietario_id=session['usuario_id']).order_by(Cliente.nome_completo)).scalars().all()
    todos_empreendimentos = db.session.execute(db.select(Empreendimento).order_by(Empreendimento.nome)).scalars().all()
    return render_template('agendamento_form.html', agendamento=agendamento, clientes=clientes_do_usuario, empreendimentos=todos_empreendimentos)

@app.route('/agendamento/<int:id>/deletar', methods=['POST'])
@login_required
def deletar_agendamento(id):
    agendamento = db.get_or_404(Agendamento, id)
    if session['usuario_perfil'] != 'Admin' and agendamento.usuario_id != session['usuario_id']:
        flash('Você não tem permissão para deletar este evento.', 'danger')
        return redirect(url_for('agenda'))
    db.session.delete(agendamento)
    db.session.commit()
    flash('Evento deletado com sucesso.', 'info')
    return redirect(url_for('agenda'))

# --- ROTAS DE RELATÓRIOS E IMPORTAÇÃO ---
@app.route('/relatorios')
@login_required
def pagina_relatorios():
    return render_template('relatorios.html')

@app.route('/relatorios/exportar_clientes_csv')
@login_required
def exportar_clientes_csv():
    if session['usuario_perfil'] == 'Admin':
        query = db.select(Cliente).order_by(Cliente.nome_completo)
    else:
        query = db.select(Cliente).filter_by(proprietario_id=session['usuario_id']).order_by(Cliente.nome_completo)
    clientes = db.session.execute(query).scalars().all()
    if not clientes:
        flash('Não há clientes para exportar.', 'info')
        return redirect(url_for('pagina_relatorios'))
    dados_para_planilha = []
    for cliente in clientes:
        dados_para_planilha.append({
            'Nome Completo': cliente.nome_completo, 'Email Pessoal': cliente.email, 'Email Comercial': cliente.email_comercial,
            'DDD Pessoal': cliente.ddd_pessoal, 'Telefone Pessoal': cliente.telefone_pessoal,
            'DDD Pessoal 2': cliente.ddd_pessoal_2, 'Telefone Pessoal 2': cliente.telefone_pessoal_2,
            'DDD Residencial': cliente.ddd_residencial, 'Telefone Residencial': cliente.telefone_residencial,
            'DDD Comercial': cliente.ddd_comercial, 'Telefone Comercial': cliente.telefone_comercial,
            'CPF': cliente.cpf, 'RG': cliente.rg, 'Data de Nascimento': cliente.data_nascimento, 'Profissão': cliente.profissao,
            'Estado Civil': cliente.estado_civil.value if cliente.estado_civil else '',
            'Status': cliente.status.value if cliente.status else '',
            'Temperatura': cliente.temperatura.value if cliente.temperatura else '',
            'Origem do Lead': cliente.origem_lead, 'Renda': cliente.faixa_renda, 'Valor Buscado': cliente.valor_imovel_buscado,
            'Observações': cliente.observacoes
        })
    df = pd.DataFrame(dados_para_planilha)
    output_csv = df.to_csv(index=False, encoding='utf-8-sig', sep=';')
    return Response(output_csv, mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=relatorio_clientes.csv"})

@app.route('/importar', methods=['GET', 'POST'])
@login_required
def importar_clientes():
    if request.method == 'POST':
        if 'arquivo' not in request.files or request.files['arquivo'].filename == '':
            flash('Nenhum arquivo selecionado.', 'danger')
            return redirect(request.url)
        file = request.files['arquivo']
        if file and file.filename.endswith('.csv'):
            try:
                df = pd.read_csv(file, encoding='utf-8', sep=';')
                clientes_novos = []
                for index, row in df.iterrows():
                    cpf = str(row['CPF']) if pd.notna(row['CPF']) else None
                    email = str(row['Email Pessoal']) if pd.notna(row['Email Pessoal']) else None
                    if cpf and db.session.execute(db.select(Cliente).filter_by(cpf=cpf)).scalar_one_or_none(): continue
                    if email and db.session.execute(db.select(Cliente).filter_by(email=email)).scalar_one_or_none(): continue
                    data_nasc_obj = pd.to_datetime(row['Data de Nascimento'], dayfirst=True, errors='coerce').date() if pd.notna(row['Data de Nascimento']) else None
                    novo_cliente = Cliente(
                        proprietario_id=session['usuario_id'],
                        nome_completo=row['Nome Completo'], data_nascimento=data_nasc_obj, cpf=cpf, rg=str(row['RG']) if pd.notna(row['RG']) else None,
                        profissao=str(row['Profissão']) if pd.notna(row['Profissão']) else None, email=email, 
                        ddd_pessoal=str(row['DDD Pessoal']) if pd.notna(row['DDD Pessoal']) else None, 
                        telefone_pessoal=str(row['Telefone Pessoal']) if pd.notna(row['Telefone Pessoal']) else None, 
                        estado_civil=EstadoCivil[row['Estado Civil'].upper().replace(" ", "_")] if pd.notna(row['Estado Civil']) else None
                    )
                    clientes_novos.append(novo_cliente)
                if clientes_novos:
                    db.session.add_all(clientes_novos)
                    db.session.commit()
                    flash(f'{len(clientes_novos)} novos clientes importados com sucesso!', 'success')
                else:
                    flash('Nenhum cliente novo para importar (contatos já podem existir).', 'info')
            except Exception as e:
                flash(f'Ocorreu um erro ao processar o arquivo. Verifique se os nomes das colunas estão corretos. Erro: {e}', 'danger')
            return redirect(url_for('lista_clientes'))
        else:
            flash('Formato de arquivo inválido. Por favor, envie um arquivo .csv.', 'danger')
            return redirect(request.url)
    return render_template('importar_clientes.html')


# --- ROTAS DE API PÚBLICA E IA ---
@app.route('/api/v1/empreendimentos')
def api_empreendimentos():
    empreendimentos_publicos = db.session.execute(db.select(Empreendimento).filter_by(publico=True).order_by(Empreendimento.nome)).scalars().all()
    lista_para_json = []
    for emp in empreendimentos_publicos:
        lista_para_json.append({'id': emp.id, 'nome': emp.nome, 'endereco': emp.endereco, 'status': emp.status, 'descricao': emp.descricao})
    return jsonify(lista_para_json)

@app.route('/empreendimento/ler_pdf', methods=['POST'])
@login_required
def ler_pdf_empreendimento():
    files = request.files.getlist('documento')
    if not files or files[0].filename == '':
        flash('Nenhum documento enviado.', 'danger')
        return redirect(url_for('adicionar_empreendimento'))

    texto_extraido_completo = ""
    nomes_arquivos_salvos = []
    for file in files:
        if file and file.filename.endswith('.pdf'):
            try:
                nome_original = file.filename
                # Cria um nome de arquivo seguro e único para evitar substituições
                nome_seguro = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(nome_original)}"
                caminho_salvar = os.path.join(app.config['UPLOAD_FOLDER'], nome_seguro)
                
                # Salva o arquivo no disco
                file.seek(0)
                file.save(caminho_salvar)
                # Guarda o nome original e o nome seguro para uso posterior
                nomes_arquivos_salvos.append(f"{nome_original}|{nome_seguro}")

                # Extrai o texto para a IA
                file.seek(0)
                with fitz.open(stream=file.read(), filetype="pdf") as doc:
                    for page in doc:
                        texto_extraido_completo += page.get_text() + "\n\n"
            except Exception as e:
                flash(f"Erro ao processar o arquivo {file.filename}: {e}", "danger")
    
    if not texto_extraido_completo.strip():
        flash("Não foi possível extrair texto dos PDFs enviados (verifique se não são PDFs de imagem).", "warning")
        # Mesmo se a extração de texto falhar, ainda passamos os arquivos salvos para o template
        return render_template('empreendimento_form.html', dados_extraidos={}, arquivos_para_anexar=nomes_arquivos_salvos)
    prompt = f"""Você é um robô assistente altamente preciso, especialista em extrair dados de documentos do mercado imobiliário para um CRM. Analise o texto abaixo e retorne as informações em um formato JSON. REGRAS RÍGIDAS: Sua resposta deve ser APENAS e EXCLUSIVAMENTE um objeto JSON válido. Se uma informação não for encontrada, o valor do campo no JSON deve ser uma string vazia "". Use este formato: {{"nome": "...", "status": "...", "endereco": "...", "descricao": "...", "previsao_entrega": "...", "valor_a_partir_de": "...", "tamanho_apartamentos_planta": "...", "vagas_garagem": "...", "quantidade_torres": 1, "subsolos": 2, "andares": 25, "campanha_promocional": "..."}} TEXTO DOS DOCUMENTOS: --- {texto_extraido_completo[:8000]} ---"""
    dados_extraidos = {}
    try:
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        response = model.generate_content(prompt)
        resposta_texto = response.text
        inicio_json = resposta_texto.find('{')
        fim_json = resposta_texto.rfind('}') + 1
        if inicio_json != -1 and fim_json != 0:
            json_limpo = resposta_texto[inicio_json:fim_json]
            dados_extraidos = json.loads(json_limpo)
            if 'project' in dados_extraidos: dados_extraidos = dados_extraidos['project']
            flash("Documento analisado com IA! Por favor, revise os campos preenchidos.", "success")
        else:
            flash("A IA respondeu, mas não em um formato JSON válido. Tentando autocorreção...", "warning")
            prompt_correcao = f"Sua resposta anterior não estava no formato JSON correto. Sua resposta foi: '{response.text}'. Por favor, corrija seu erro e forneça APENAS o objeto JSON válido baseado no documento original que te enviei, sem nenhuma outra palavra ou explicação."
            response_corrigida = model.generate_content(prompt_correcao)
            resposta_texto_corrigido = response_corrigida.text
            inicio_json_c = resposta_texto_corrigido.find('{')
            fim_json_c = resposta_texto_corrigido.rfind('}') + 1
            if inicio_json_c != -1 and fim_json_c != 0:
                json_limpo_c = resposta_texto_corrigido[inicio_json_c:fim_json_c]
                dados_extraidos = json.loads(json_limpo_c)
                if 'project' in dados_extraidos: dados_extraidos = dados_extraidos['project']
                flash("Autocorreção da IA bem-sucedida! Por favor, revise os campos.", "success")
            else:
                 flash(Markup(f"A autocorreção da IA também falhou. A resposta da IA foi: <pre>{escape(response_corrigida.text)}</pre>"), "danger")
    except Exception as e:
        print(f"Erro ao processar com a IA ou ao fazer o parse do JSON: {e}")
        flash(f"A IA não conseguiu processar os documentos. Erro: {e}", "danger")
        
    return render_template('empreendimento_form.html', dados_extraidos=dados_extraidos, texto_original_para_salvar=texto_extraido_completo, arquivos_para_anexar=nomes_arquivos_salvos)
