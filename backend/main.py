# main.py — Coração do sistema: servidor FastAPI

# Rotas disponíveis:
#   POST /login            → autentica e retorna token JWT
#   GET  /me               → retorna dados do usuário logado
#   GET  /scripts          → lista os scripts disponíveis
#   POST /scripts/{nome}   → executa um script
#   WS   /ws/logs/{nome}   → transmite logs em tempo real
# ============================================================

import os
import subprocess
import asyncio
from datetime import datetime

from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import (
    CORSMiddleware,
)  # permite o frontend acessar o backend
from fastapi.staticfiles import StaticFiles  # serve os arquivos HTML/CSS/JS
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel  # valida os dados recebidos nas requisições
from dotenv import load_dotenv

from auth import autenticar_usuario, criar_token, verificar_token
from database import get_conn, init_db

# Carrega variáveis do .env
load_dotenv()

# ── Inicialização ────────────────────────────────────────────
# Cria o banco de dados (tabelas + usuário admin) se ainda não existir
init_db()

# Cria a aplicação FastAPI
app = FastAPI(title="Talk System", version="1.0.0")

# ── CORS ────────────────────────────────────────────────────
# Permite que o frontend (HTML rodando no navegador) acesse o backend
# Em produção, trocar "*" pelo domínio real do sistema
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Arquivos estáticos ───────────────────────────────────────
# Serve os arquivos da pasta frontend (HTML, CSS, JS)
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(FRONTEND_DIR, "static")),
    name="static",
)

# ── Segurança ────────────────────────────────────────────────
# HTTPBearer lê o token JWT do cabeçalho Authorization da requisição
security = HTTPBearer()


def obter_usuario_atual(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    Função de proteção: verifica se o token JWT é válido.
    Usada como dependência nas rotas protegidas (Depends).
    Se o token for inválido, retorna erro 401 (não autorizado).
    """
    token = credentials.credentials  # pega o token do cabeçalho
    usuario = verificar_token(token)

    if not usuario:
        raise HTTPException(
            status_code=401, detail="Token inválido ou expirado. Faça login novamente."
        )

    return usuario


# ── Scripts disponíveis ──────────────────────────────────────
# Cada script tem: nome, arquivo .py, perfis que podem executar
SCRIPTS = {
    "tendencia": {
        "label": "Tendência de Vendas",
        "arquivo": "tendencia.py",
        "perfis": ["admin", "diretoria", "logistica"],
    },
    "lancamentos": {
        "label": "Lançamentos",
        "arquivo": "lancamentos.py",
        "perfis": ["admin", "diretoria", "logistica"],
    },
    "parcial_dia": {
        "label": "Parcial do Dia",
        "arquivo": "parcial_dia.py",
        "perfis": ["admin", "diretoria", "logistica"],
    },
    "reposicao": {
        "label": "Reposição de Estoque",
        "arquivo": "reposicao.py",
        "perfis": ["admin", "logistica"],
    },
    "remanejamento": {
        "label": "Remanejamento",
        "arquivo": "remanejamento.py",
        "perfis": ["admin", "logistica"],
    },
    "peliculas_norte": {
        "label": "Películas — Rota Norte",
        "arquivo": "peliculas_norte.py",
        "perfis": ["admin", "logistica"],
    },
    "peliculas_sul": {
        "label": "Películas — Rota Sul",
        "arquivo": "peliculas_sul.py",
        "perfis": ["admin", "logistica"],
    },
    "cashback": {
        "label": "Cashback",
        "arquivo": "cashback.py",
        "perfis": ["admin", "diretoria"],
    },
}

# Caminho da pasta onde ficam os scripts
SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "scripts")

# Python do venv (garante que usa as bibliotecas instaladas)
PYTHON = os.path.join(os.path.dirname(__file__), "..", ".venv", "bin", "python3")


# ── Modelos de dados ─────────────────────────────────────────


class LoginInput(BaseModel):
    """Dados esperados no corpo da requisição de login."""

    username: str
    senha: str


# ── Rotas do frontend ────────────────────────────────────────


@app.get("/", include_in_schema=False)
def raiz():
    """Redireciona a raiz para a tela de login."""
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/dashboard", include_in_schema=False)
def dashboard():
    """Serve a tela do dashboard."""
    return FileResponse(os.path.join(FRONTEND_DIR, "dashboard.html"))


# ── Rotas da API ─────────────────────────────────────────────


@app.post("/login")
def login(dados: LoginInput):
    """
    Rota de login.
    Recebe username e senha, verifica no banco e retorna um token JWT.
    """
    # Tenta autenticar o usuário
    usuario = autenticar_usuario(dados.username, dados.senha)

    if not usuario:
        # Usuário não encontrado ou senha errada
        raise HTTPException(status_code=401, detail="Usuário ou senha incorretos.")

    # Gera o token JWT com os dados do usuário
    token = criar_token(
        {
            "id": usuario["id"],
            "username": usuario["username"],
            "perfil": usuario["perfil"],
        }
    )

    return {
        "token": token,
        "username": usuario["username"],
        "perfil": usuario["perfil"],
    }


@app.get("/me")
def meus_dados(usuario: dict = Depends(obter_usuario_atual)):
    """
    Rota protegida: retorna os dados do usuário logado.
    O frontend usa essa rota para saber quem está logado.
    """
    return usuario


@app.get("/scripts")
def listar_scripts(usuario: dict = Depends(obter_usuario_atual)):
    """
    Retorna a lista de scripts que o usuário atual pode executar,
    filtrando pelo perfil dele.
    """
    perfil = usuario["perfil"]

    scripts_visiveis = {}
    for nome, info in SCRIPTS.items():
        if perfil in info["perfis"]:
            scripts_visiveis[nome] = {
                "label": info["label"],
                "perfis": info["perfis"],
            }

    return scripts_visiveis


@app.post("/scripts/{nome}")
def executar_script(nome: str, usuario: dict = Depends(obter_usuario_atual)):
    """
    Executa um script pelo nome.
    Verifica se o usuário tem permissão antes de executar.
    Registra a execução no banco de dados.
    """
    # Verifica se o script existe
    if nome not in SCRIPTS:
        raise HTTPException(status_code=404, detail=f"Script '{nome}' não encontrado.")

    script_info = SCRIPTS[nome]

    # Verifica se o perfil do usuário tem permissão para esse script
    if usuario["perfil"] not in script_info["perfis"]:
        raise HTTPException(
            status_code=403,
            detail="Seu perfil não tem permissão para executar esse script.",
        )

    # Caminho completo do arquivo .py
    caminho = os.path.join(SCRIPTS_DIR, script_info["arquivo"])

    if not os.path.exists(caminho):
        raise HTTPException(
            status_code=500, detail=f"Arquivo do script não encontrado: {caminho}"
        )

    # Registra o início da execução no banco
    conn = get_conn()
    c = conn.cursor()
    inicio = datetime.now().isoformat()
    c.execute(
        "INSERT INTO execucoes (user_id, script, status, inicio) VALUES (?, ?, 'rodando', ?)",
        (usuario["id"], nome, inicio),
    )
    execucao_id = c.lastrowid
    conn.commit()
    conn.close()

    # Executa o script como subprocesso (em segundo plano)
    subprocess.Popen([PYTHON, caminho])

    return {
        "mensagem": f"Script '{script_info['label']}' iniciado com sucesso.",
        "execucao_id": execucao_id,
    }


# ── WebSocket — Logs em tempo real ──────────────────────────


@app.websocket("/ws/logs/{nome}")
async def websocket_logs(websocket: WebSocket, nome: str):
    """
    Conexão WebSocket que transmite os logs de um script em tempo real.
    O frontend conecta aqui e recebe cada linha de saída do script.
    """
    await websocket.accept()

    # Verifica se o script existe
    if nome not in SCRIPTS:
        await websocket.send_text("❌ Script não encontrado.")
        await websocket.close()
        return

    caminho = os.path.join(SCRIPTS_DIR, SCRIPTS[nome]["arquivo"])

    try:
        # Inicia o script capturando a saída linha por linha
        processo = await asyncio.create_subprocess_exec(
            PYTHON,
            caminho,
            stdout=asyncio.subprocess.PIPE,  # captura o print() do script
            stderr=asyncio.subprocess.STDOUT,  # junta erros com saída normal
        )

        # Envia cada linha de log para o frontend via WebSocket
        async for linha in processo.stdout:
            texto = linha.decode("utf-8", errors="replace").rstrip()
            if texto:
                await websocket.send_text(texto)

        await processo.wait()
        await websocket.send_text("✅ Script finalizado.")

    except WebSocketDisconnect:
        # Usuário fechou o navegador antes de terminar
        pass
    except Exception as e:
        await websocket.send_text(f"❌ Erro: {str(e)}")
    finally:
        await websocket.close()


# ── Iniciar o servidor ───────────────────────────────────────
# Rode com: .venv/bin/uvicorn main:app --reload --port 8000

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
