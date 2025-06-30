from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import enum
from datetime import date, datetime

db = SQLAlchemy()

interesses_table = db.Table('interesses',
    db.Column('cliente_id', db.Integer, db.ForeignKey('cliente.id'), primary_key=True),
    db.Column('empreendimento_id', db.Integer, db.ForeignKey('empreendimento.id'), primary_key=True)
)

class StatusCliente(enum.Enum):
    LEAD_NOVO = "Lead Novo"; EM_CONTATO = "Em Contato"; EM_NEGOCIACAO = "Em Negociação"; COMPROU = "Comprou"; DESCARTADO = "Descartado"
class TemperaturaLead(enum.Enum):
    QUENTE = "Quente"; MORNO = "Morno"; FRIO = "Frio"
class EstadoCivil(enum.Enum):
    SOLTEIRO = "Solteiro(a)"; CASADO = "Casado(a)"; DIVORCIADO = "Divorciado(a)"; VIUVO = "Viúvo(a)"; UNIAO_ESTAVEL = "União Estável"
class PerfilUsuario(enum.Enum):
    ADMIN = "Admin"; CORRETOR = "Corretor"
class TipoAtividade(enum.Enum):
    LIGACAO = "Ligação"; EMAIL = "Email"; WHATSAPP = "WhatsApp"; REUNIAO = "Reunião"; VISITA = "Visita"; FOLLOW_UP = "Follow-up"; OUTRO = "Outro"

class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome_completo = db.Column(db.String(150), nullable=False)
    data_nascimento = db.Column(db.Date, nullable=True)
    cpf = db.Column(db.String(14), nullable=True, unique=True)
    rg = db.Column(db.String(20), nullable=True)
    profissao = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(120), nullable=True, unique=True)
    email_comercial = db.Column(db.String(120), nullable=True, unique=True)
    ddd_pessoal = db.Column(db.String(2), nullable=False)
    telefone_pessoal = db.Column(db.String(9), nullable=False)
    ddd_pessoal_2 = db.Column(db.String(2), nullable=True)
    telefone_pessoal_2 = db.Column(db.String(9), nullable=True)
    ddd_residencial = db.Column(db.String(2), nullable=True)
    telefone_residencial = db.Column(db.String(9), nullable=True)
    ddd_comercial = db.Column(db.String(2), nullable=True)
    telefone_comercial = db.Column(db.String(9), nullable=True)
    cep_residencial = db.Column(db.String(9), nullable=True)
    logradouro_residencial = db.Column(db.String(200), nullable=True)
    numero_residencial = db.Column(db.String(20), nullable=True)
    complemento_residencial = db.Column(db.String(50), nullable=True)
    bairro_residencial = db.Column(db.String(100), nullable=True)
    cidade_residencial = db.Column(db.String(100), nullable=True)
    estado_residencial = db.Column(db.String(2), nullable=True)
    empresa_cliente = db.Column(db.String(150), nullable=True)
    endereco_comercial_cliente = db.Column(db.Text, nullable=True)
    estado_civil = db.Column(db.Enum(EstadoCivil), nullable=True)
    nome_conjuge = db.Column(db.String(150), nullable=True)
    cpf_conjuge = db.Column(db.String(14), nullable=True)
    profissao_conjuge = db.Column(db.String(100), nullable=True)
    email_conjuge = db.Column(db.String(120), nullable=True)
    email_conjuge_comercial = db.Column(db.String(120), nullable=True)
    ddd_conjuge = db.Column(db.String(2), nullable=True)
    telefone_conjuge = db.Column(db.String(9), nullable=True)
    empresa_conjuge = db.Column(db.String(150), nullable=True)
    endereco_comercial_conjuge = db.Column(db.Text, nullable=True)
    origem_lead = db.Column(db.String(100), nullable=True)
    data_primeiro_contato = db.Column(db.Date, nullable=True, default=date.today)
    temperatura = db.Column(db.Enum(TemperaturaLead), nullable=True, default=TemperaturaLead.MORNO)
    status = db.Column(db.Enum(StatusCliente), nullable=False, default=StatusCliente.LEAD_NOVO)
    faixa_renda = db.Column(db.String(50), nullable=True)
    valor_imovel_buscado = db.Column(db.String(50), nullable=True)
    observacoes = db.Column(db.Text, nullable=True)
    descartado = db.Column(db.Boolean, default=False, nullable=False)
    empreendimentos_interesse = db.relationship('Empreendimento', secondary=interesses_table, back_populates='interessados')
    proprietario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    proprietario = db.relationship('Usuario', back_populates='clientes')
    agendamentos = db.relationship('Agendamento', back_populates='cliente', cascade='all, delete-orphan')
    atividades = db.relationship('Atividade', back_populates='cliente', cascade='all, delete-orphan', lazy='dynamic')

class Empreendimento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    status = db.Column(db.String(50), nullable=True)
    endereco = db.Column(db.String(250), nullable=True)
    descricao = db.Column(db.Text, nullable=True)
    publico = db.Column(db.Boolean, default=False, nullable=False)
    prazo_entrega = db.Column(db.Date, nullable=True)
    previsao_entrega = db.Column(db.String(100), nullable=True)
    valor_medio_unidades = db.Column(db.String(50), nullable=True)
    valor_a_partir_de = db.Column(db.String(50), nullable=True)
    tamanho_apartamentos_planta = db.Column(db.String(100), nullable=True)
    vagas_garagem = db.Column(db.String(50), nullable=True)
    tamanho_terreno = db.Column(db.String(50), nullable=True)
    quantidade_torres = db.Column(db.Integer, nullable=True)
    subsolos = db.Column(db.Integer, nullable=True)
    andares = db.Column(db.Integer, nullable=True)
    campanha_promocional = db.Column(db.Text, nullable=True)
    materiais = db.relationship('Material', back_populates='empreendimento', cascade='all, delete-orphan')
    interessados = db.relationship('Cliente', secondary=interesses_table, back_populates='empreendimentos_interesse')
    agendamentos = db.relationship('Agendamento', back_populates='empreendimento', cascade='all, delete-orphan')

class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    _senha_hash = db.Column(db.String(256), nullable=False)
    perfil = db.Column(db.Enum(PerfilUsuario), nullable=False, default=PerfilUsuario.CORRETOR)
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    clientes = db.relationship('Cliente', back_populates='proprietario')
    agendamentos = db.relationship('Agendamento', back_populates='usuario', cascade='all, delete-orphan')
    atividades = db.relationship('Atividade', back_populates='usuario', cascade='all, delete-orphan')
    def definir_senha(self, senha): self._senha_hash = generate_password_hash(senha)
    def verificar_senha(self, senha): return check_password_hash(self._senha_hash, senha)

class Material(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome_original = db.Column(db.String(200), nullable=False)
    nome_arquivo_servidor = db.Column(db.String(200), nullable=False, unique=True)
    empreendimento_id = db.Column(db.Integer, db.ForeignKey('empreendimento.id'), nullable=False)
    empreendimento = db.relationship('Empreendimento', back_populates='materiais')

class Agendamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    data_inicio = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    data_fim = db.Column(db.DateTime, nullable=True)
    descricao = db.Column(db.Text, nullable=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=True)
    empreendimento_id = db.Column(db.Integer, db.ForeignKey('empreendimento.id'), nullable=True)
    usuario = db.relationship('Usuario', back_populates='agendamentos')
    cliente = db.relationship('Cliente', back_populates='agendamentos')
    empreendimento = db.relationship('Empreendimento', back_populates='agendamentos')

class Atividade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data_criacao = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    tipo = db.Column(db.Enum(TipoAtividade), nullable=False)
    resumo = db.Column(db.Text, nullable=False)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    cliente = db.relationship('Cliente', back_populates='atividades')
    usuario = db.relationship('Usuario', back_populates='atividades')

class ExemploIA(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    texto_documento = db.Column(db.Text, nullable=False)
    json_resultado_corrigido = db.Column(db.Text, nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)