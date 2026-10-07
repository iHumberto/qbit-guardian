"""
qbit-guardian — Credenciais da Web UI.

A Web UI passou a exigir autenticacao por padrao (v2.2.0). Como nao existe
tela de cadastro, a primeira senha e **gerada pelo proprio guardian** no
startup e impressa no stdout do container: `docker logs qbit-guardian` mostra
usuario e senha. Depois o usuario troca pela propria Web UI.

Decisoes:

- A senha e guardada como **hash PBKDF2-SHA256**, nunca em texto claro. Antes
  da v2.2.0 ela ia em texto no config.json e era devolvida pelo
  `GET /api/config` — qualquer um que alcancasse a porta lia a senha.
- Config gravada antes da v2.2.0 tem a senha em texto claro. `verificar_senha`
  continua aceitando esse formato e `migrar_credenciais` reescreve como hash no
  primeiro startup: a senha que o usuario ja usava continua valendo.
- Comparacoes usam `hmac.compare_digest`: `==` em string vaza, pelo tempo de
  resposta, quantos caracteres do inicio estao corretos.
"""

import base64
import hashlib
import hmac
import secrets

from app.logger import get_logger

log = get_logger("auth")

USUARIO_PADRAO = "admin"

# Alfabeto sem caracteres ambiguos (0/O, 1/l/I): a senha gerada e LIDA do log
# e digitada a mao, entao confundir zero com O custa um suporte.
ALFABETO = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
TAMANHO_SENHA_GERADA = 20

# Minimo para a senha escolhida pelo usuario na Web UI.
TAMANHO_MINIMO_SENHA = 8

PREFIXO_HASH = "pbkdf2_sha256"
# OWASP (2023) recomenda >= 600k iteracoes para PBKDF2-HMAC-SHA256.
ITERACOES = 600_000


def gerar_senha(tamanho=TAMANHO_SENHA_GERADA):
    """Senha aleatoria criptograficamente segura."""
    return "".join(secrets.choice(ALFABETO) for _ in range(tamanho))


def gerar_secret_key():
    """Chave para assinar o cookie de sessao da Web UI.

    Fica no config.json e sobrevive a restart: regenerar a cada boot
    deslogaria todo mundo sempre que o container reiniciasse.
    """
    return secrets.token_urlsafe(32)


def e_hash(valor):
    """True se o valor ja esta no formato de hash desta funcao."""
    return isinstance(valor, str) and valor.startswith(PREFIXO_HASH + "$")


def hash_senha(senha, salt=None, iteracoes=ITERACOES):
    """Deriva `pbkdf2_sha256$<iteracoes>$<salt_b64>$<hash_b64>`."""
    if salt is None:
        salt = secrets.token_bytes(16)
    derivado = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt, iteracoes)
    return "$".join([
        PREFIXO_HASH,
        str(iteracoes),
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(derivado).decode("ascii"),
    ])


def verificar_senha(senha, armazenado):
    """Confere `senha` contra o valor guardado (hash novo ou texto legado)."""
    if not isinstance(senha, str) or not isinstance(armazenado, str) or not armazenado:
        return False

    if not e_hash(armazenado):
        # Formato legado (ate a v2.1.2): comparacao direta, em tempo constante.
        return hmac.compare_digest(senha, armazenado)

    try:
        _, iteracoes, salt_b64, hash_b64 = armazenado.split("$")
        salt = base64.b64decode(salt_b64)
        esperado = base64.b64decode(hash_b64)
        iteracoes = int(iteracoes)
    except (ValueError, TypeError):
        # Hash corrompido nao autentica ninguem.
        return False

    derivado = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt, iteracoes)
    return hmac.compare_digest(derivado, esperado)


def verificar_usuario(informado, armazenado):
    """Compara o usuario em tempo constante."""
    if not isinstance(informado, str) or not isinstance(armazenado, str):
        return False
    return hmac.compare_digest(informado, armazenado)


def _banner(usuario, senha):
    """Bloco de provisionamento impresso no stdout.

    Vai em `print`, nao em `log`: o compose publicado usa `LOG_LEVEL=ERROR`, e
    uma senha anunciada em INFO nao apareceria em `docker logs` justamente na
    hora em que o usuario precisa dela.
    """
    linha = "=" * 68
    print(
        f"\n{linha}\n"
        f"  qbit-guardian — credenciais da Web UI geradas automaticamente\n"
        f"{linha}\n"
        f"  usuario: {usuario}\n"
        f"  senha:   {senha}\n"
        f"{linha}\n"
        f"  Esta senha aparece UMA VEZ, aqui. Guarde-a agora.\n"
        f"  Para trocar: abra a Web UI, clique no icone de usuario (canto\n"
        f"  superior direito) e informe a senha atual mais a nova.\n"
        f"  Para gerar outra: apague `webui.password` do config.json e\n"
        f"  reinicie o container.\n"
        f"{linha}\n",
        flush=True,
    )


def garantir_credenciais(cfg):
    """Garante usuario e senha utilizaveis em `cfg`.

    Retorna (cfg, alterou). Tres situacoes:

    1. Sem senha (instalacao nova, ou usuario apagou o campo para resetar):
       gera uma, imprime o banner e guarda o hash.
    2. Senha em texto claro (config anterior a v2.2.0): converte para hash sem
       avisar nada — a senha que o usuario ja usa continua valendo.
    3. Ja e hash: nao mexe.

    Em qualquer um dos casos tambem garante `secret_key`, usada para assinar o
    cookie de sessao da tela de login.

    Nao grava em disco; quem chama decide quando persistir.
    """
    webui = cfg.get("webui")
    if not isinstance(webui, dict):
        webui = {}
        cfg["webui"] = webui

    alterou = False

    chave = webui.get("secret_key")
    if not isinstance(chave, str) or not chave.strip():
        webui["secret_key"] = gerar_secret_key()
        alterou = True

    usuario = webui.get("user")
    if not isinstance(usuario, str) or not usuario.strip():
        webui["user"] = USUARIO_PADRAO
        alterou = True

    senha = webui.get("password")

    if isinstance(senha, str) and e_hash(senha):
        return cfg, alterou

    if isinstance(senha, str) and senha.strip():
        # Migracao silenciosa do formato legado.
        webui["password"] = hash_senha(senha)
        log.warning("senha da Web UI migrada de texto claro para hash PBKDF2")
        return cfg, True

    nova = gerar_senha()
    webui["password"] = hash_senha(nova)
    _banner(webui["user"], nova)
    return cfg, True
