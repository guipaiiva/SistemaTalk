# ============================================================
# users.py — Gerenciamento de usuários do sistema
# ============================================================
# Esse arquivo cuida de tudo relacionado a usuários:
#   - Listar usuários
#   - Criar novo usuário
#   - Atualizar dados (senha, perfil, ativo)
#   - Desativar usuário (nunca deletamos, só desativamos)
#
# Todas as rotas aqui são protegidas e só o perfil "admin"
# pode acessá-las.
# ============================================================

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel          # valida os dados recebidos
from typing import Optional

from auth import gerar_hash, obter_usuario_atual
from database import get_conn

# APIRouter agrupa as rotas de usuário para importar no main.py
router = APIRouter(prefix="/api/usuarios", tags=["Usuários"])


# ── Modelos de dados ─────────────────────────────────────────

class NovoUsuario(BaseModel):
    """Dados necessários para criar um novo usuário."""
    username: str
    senha: str
    perfil: str  # admin, diretoria ou logistica


class AtualizarUsuario(BaseModel):
    """Dados que podem ser atualizados. Todos são opcionais."""
    senha: Optional[str] = None    # None = não alterar a senha
    perfil: Optional[str] = None   # None = não alterar o perfil
    ativo: Optional[bool] = None   # None = não alterar o status


# ── Verificação de permissão ─────────────────────────────────

def apenas_admin(usuario: dict = Depends(obter_usuario_atual)) -> dict:
    """
    Garante que apenas administradores acessem a rota.
    Se o perfil não for 'admin', retorna erro 403 (proibido).
    """
    if usuario["perfil"] != "admin":
        raise HTTPException(status_code=403, detail="Apenas administradores podem gerenciar usuários.")
    return usuario


# ── Rotas ────────────────────────────────────────────────────

@router.get("/")
def listar_usuarios(admin: dict = Depends(apenas_admin)):
    """
    Lista todos os usuários cadastrados.
    Não retorna o hash da senha por segurança.
    """
    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT id, username, perfil, ativo FROM users ORDER BY id")
    usuarios = [dict(row) for row in c.fetchall()]
    conn.close()

    return usuarios


@router.post("/")
def criar_usuario(dados: NovoUsuario, admin: dict = Depends(apenas_admin)):
    """
    Cria um novo usuário no sistema.
    A senha é transformada em hash antes de salvar — nunca guardamos a senha pura.
    """
    # Valida o perfil informado
    perfis_validos = ["admin", "diretoria", "logistica"]
    if dados.perfil not in perfis_validos:
        raise HTTPException(
            status_code=400,
            detail=f"Perfil inválido. Use: {', '.join(perfis_validos)}"
        )

    # Gera o hash da senha
    hash_senha = gerar_hash(dados.senha)

    conn = get_conn()
    c = conn.cursor()

    try:
        c.execute(
            "INSERT INTO users (username, password_hash, perfil) VALUES (?, ?, ?)",
            (dados.username, hash_senha, dados.perfil)
        )
        conn.commit()
        novo_id = c.lastrowid
    except Exception:
        # Username já existe no banco (campo UNIQUE)
        raise HTTPException(status_code=400, detail=f"Usuário '{dados.username}' já existe.")
    finally:
        conn.close()

    return {"mensagem": f"Usuário '{dados.username}' criado com sucesso.", "id": novo_id}


@router.patch("/{user_id}")
def atualizar_usuario(user_id: int, dados: AtualizarUsuario, admin: dict = Depends(apenas_admin)):
    """
    Atualiza dados de um usuário existente.
    Só atualiza os campos que forem enviados (os outros ficam intactos).
    """
    conn = get_conn()
    c = conn.cursor()

    # Verifica se o usuário existe
    c.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    # Monta apenas os campos que foram enviados para atualizar
    campos = []
    valores = []

    if dados.senha is not None:
        campos.append("password_hash = ?")
        valores.append(gerar_hash(dados.senha))  # converte para hash antes de salvar

    if dados.perfil is not None:
        perfis_validos = ["admin", "diretoria", "logistica"]
        if dados.perfil not in perfis_validos:
            conn.close()
            raise HTTPException(status_code=400, detail=f"Perfil inválido. Use: {', '.join(perfis_validos)}")
        campos.append("perfil = ?")
        valores.append(dados.perfil)

    if dados.ativo is not None:
        campos.append("ativo = ?")
        valores.append(1 if dados.ativo else 0)  # SQLite usa 1/0 para booleano

    # Se nada foi enviado, não há o que atualizar
    if not campos:
        conn.close()
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar foi enviado.")

    # Executa o UPDATE apenas nos campos alterados
    valores.append(user_id)
    c.execute(f"UPDATE users SET {', '.join(campos)} WHERE id = ?", valores)
    conn.commit()
    conn.close()

    return {"mensagem": "Usuário atualizado com sucesso."}


@router.delete("/{user_id}")
def desativar_usuario(user_id: int, admin: dict = Depends(apenas_admin)):
    """
    Desativa um usuário (ele não consegue mais fazer login).
    Nunca deletamos usuários do banco para manter o histórico de execuções.
    """
    conn = get_conn()
    c = conn.cursor()

    # Verifica se o usuário existe
    c.execute("SELECT username FROM users WHERE id = ?", (user_id,))
    usuario = c.fetchone()

    if not usuario:
        conn.close()
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    # Apenas desativa, não deleta
    c.execute("UPDATE users SET ativo = 0 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    return {"mensagem": f"Usuário '{usuario['username']}' desativado com sucesso."}


@router.get("/execucoes/")
def listar_execucoes(admin: dict = Depends(apenas_admin)):
    """
    Lista o histórico de todas as execuções de scripts.
    Mostra quem executou, qual script, quando e o resultado.
    """
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        SELECT
            e.id,
            u.username,
            e.script,
            e.status,
            e.inicio,
            e.fim
        FROM execucoes e
        JOIN users u ON e.user_id = u.id
        ORDER BY e.id DESC
        LIMIT 100
    """)

    execucoes = [dict(row) for row in c.fetchall()]
    conn.close()

    return execucoes
