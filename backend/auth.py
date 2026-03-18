# auth.py — Responsável pelo login e geração de tokens JWT

import os
from datetime import datetime, timedelta
from jose import JWTError, jwt          # biblioteca para criar e ler tokens JWT
from passlib.context import CryptContext # biblioteca para verificar senhas com hash
from dotenv import load_dotenv           # biblioteca para ler o arquivo .env
from database import get_conn            # função que abre conexão com o banco SQLite

# Carrega as variáveis do arquivo .env para não deixar chaves expostas no código
load_dotenv()

# ── Configurações do Token ──────────────────────────────────
# Lê a chave secreta do .env (nunca deixar fixo no código!)
SECRET_KEY = os.getenv("SECRET_KEY")

# Algoritmo de criptografia do token
ALGORITHM = "HS256"

# Tempo de validade do token: 8 horas (tempo de um turno de trabalho)
EXPIRE_HOURS = 8

# ── Configuração do Hash de Senha ───────────────────────────
# bcrypt é um algoritmo seguro para armazenar senhas
# Nunca salvamos a senha pura no banco, apenas o hash dela
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Funções de Senha ────────────────────────────────────────


def verificar_senha(senha_digitada: str, hash_salvo: str) -> bool:
    """
    Compara a senha digitada pelo usuário com o hash salvo no banco.
    Retorna True se bater, False se não bater.
    """
    return pwd_context.verify(senha_digitada, hash_salvo)


def gerar_hash(senha: str) -> str:
    """
    Transforma uma senha pura em hash seguro para salvar no banco.
    Ex: "admin123" → "$2b$12$abc...xyz"
    """
    return pwd_context.hash(senha)


# ── Funções de Token ────────────────────────────────────────


def criar_token(dados: dict) -> str:
    """
    Gera um token JWT com os dados do usuário.
    O token expira após EXPIRE_HOURS horas.
    """
    # Copia os dados para não alterar o original
    payload = dados.copy()

    # Define quando o token vai expirar
    expiracao = datetime.utcnow() + timedelta(hours=EXPIRE_HOURS)
    payload["exp"] = expiracao

    # Gera e retorna o token assinado
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token


def verificar_token(token: str) -> dict | None:
    """
    Lê e valida um token JWT.
    Retorna os dados do usuário se o token for válido.
    Retorna None se o token for inválido ou expirado.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        # Token inválido, adulterado ou expirado
        return None


# ── Autenticação Principal ──────────────────────────────────


def autenticar_usuario(username: str, senha: str) -> dict | None:
    """
    Verifica se o usuário existe no banco e se a senha está correta.
    Retorna os dados do usuário se tudo certo.
    Retorna None se o usuário não existir ou a senha estiver errada.
    """
    conn = get_conn()
    c = conn.cursor()

    # Busca o usuário pelo nome no banco
    c.execute("SELECT * FROM users WHERE username = ? AND ativo = 1", (username,))
    usuario = c.fetchone()
    conn.close()

    # Se não encontrou o usuário, retorna None
    if not usuario:
        return None

    # Verifica se a senha digitada bate com o hash salvo no banco
    if not verificar_senha(senha, usuario["password_hash"]):
        return None

    # Retorna os dados do usuário (sem a senha)
    return {
        "id": usuario["id"],
        "username": usuario["username"],
        "perfil": usuario["perfil"],
    }
