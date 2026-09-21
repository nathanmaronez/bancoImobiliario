import random
import sqlite3
import string
from datetime import datetime
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Banco Imobiliário - Cartão Digital", page_icon="🏦", layout="centered")

DB_PATH = Path(__file__).parent / "banco_imobiliario.db"

VALORES_INICIAIS = {
    "Clássico (R$ 4.000)": 4000,
    "Edição atual (R$ 8.000)": 8000,
    "Jogo rápido (R$ 2.000)": 2000,
    "Personalizado": None,
}

# ---------------------------------------------------------------------------
# Banco de dados (compartilhado entre todos os dispositivos conectados
# ao mesmo servidor Streamlit)
# ---------------------------------------------------------------------------

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS games (
            game_id TEXT PRIMARY KEY,
            valor_inicial INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS players (
            game_id TEXT NOT NULL,
            name TEXT NOT NULL,
            saldo INTEGER NOT NULL,
            PRIMARY KEY (game_id, name)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS historico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id TEXT NOT NULL,
            hora TEXT NOT NULL,
            origem TEXT NOT NULL,
            destino TEXT NOT NULL,
            valor INTEGER NOT NULL,
            motivo TEXT
        )"""
    )
    conn.commit()
    conn.close()


def gerar_codigo():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=5))


def criar_sala(valor_inicial):
    game_id = gerar_codigo()
    conn = get_conn()
    while conn.execute("SELECT 1 FROM games WHERE game_id=?", (game_id,)).fetchone():
        game_id = gerar_codigo()
    conn.execute(
        "INSERT INTO games (game_id, valor_inicial, created_at) VALUES (?, ?, ?)",
        (game_id, valor_inicial, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    return game_id


def get_sala(game_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM games WHERE game_id=?", (game_id,)).fetchone()
    conn.close()
    return row


def get_jogadores(game_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT name, saldo FROM players WHERE game_id=? ORDER BY rowid", (game_id,)
    ).fetchall()
    conn.close()
    return {r["name"]: r["saldo"] for r in rows}


def entrar_na_sala(game_id, nome, valor_inicial):
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO players (game_id, name, saldo) VALUES (?, ?, ?)",
        (game_id, nome, valor_inicial),
    )
    conn.commit()
    conn.close()


def get_historico(game_id, limite=100):
    conn = get_conn()
    rows = conn.execute(
        "SELECT hora, origem, destino, valor, motivo FROM historico "
        "WHERE game_id=? ORDER BY id DESC LIMIT ?",
        (game_id, limite),
    ).fetchall()
    conn.close()
    return rows


def registrar(game_id, origem, destino, valor, motivo):
    conn = get_conn()
    saldos = get_jogadores(game_id)
    if origem != "Banco" and saldos.get(origem, 0) < valor:
        conn.close()
        return False, "Saldo insuficiente."
    if origem != "Banco":
        conn.execute(
            "UPDATE players SET saldo = saldo - ? WHERE game_id=? AND name=?",
            (valor, game_id, origem),
        )
    if destino != "Banco":
        conn.execute(
            "UPDATE players SET saldo = saldo + ? WHERE game_id=? AND name=?",
            (valor, game_id, destino),
        )
    conn.execute(
        "INSERT INTO historico (game_id, hora, origem, destino, valor, motivo) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (game_id, datetime.now().strftime("%H:%M:%S"), origem, destino, valor, motivo),
    )
    conn.commit()
    conn.close()
    return True, None


def encerrar_sala(game_id):
    conn = get_conn()
    conn.execute("DELETE FROM games WHERE game_id=?", (game_id,))
    conn.execute("DELETE FROM players WHERE game_id=?", (game_id,))
    conn.execute("DELETE FROM historico WHERE game_id=?", (game_id,))
    conn.commit()
    conn.close()


def fmt(v):
    return f"R$ {v:,.0f}".replace(",", ".")


# ---------------------------------------------------------------------------
# Sessão do jogador neste dispositivo — guardada também na URL, para que um
# refresh normal do navegador (ou reabrir a aba) não perca o lugar na sala.
# ---------------------------------------------------------------------------

def entrar_na_sessao(game_id, nome):
    st.session_state.game_id = game_id
    st.session_state.meu_nome = nome
    st.query_params["sala"] = game_id
    st.query_params["nome"] = nome


def sair_da_sessao():
    for chave in ("game_id", "meu_nome"):
        st.session_state.pop(chave, None)
    st.query_params.clear()


def restaurar_sessao_da_url():
    if "game_id" in st.session_state and "meu_nome" in st.session_state:
        return
    sala = st.query_params.get("sala")
    nome = st.query_params.get("nome")
    if sala and nome and get_sala(sala):
        st.session_state.game_id = sala
        st.session_state.meu_nome = nome


# ---------------------------------------------------------------------------
# Telas
# ---------------------------------------------------------------------------

def tela_entrada():
    st.title("🏦 Banco Imobiliário — Cartão Digital")
    st.caption(
        "Sem dinheiro físico e sem banqueiro: cada jogador entra na mesma sala "
        "pelo próprio celular e faz suas próprias transações."
    )

    aba_criar, aba_entrar = st.tabs(["➕ Criar sala", "🔑 Entrar em uma sala"])

    with aba_criar:
        opcao = st.selectbox("Valor inicial de cada jogador", list(VALORES_INICIAIS.keys()))
        if VALORES_INICIAIS[opcao] is None:
            valor_inicial = st.number_input(
                "Valor inicial personalizado (R$)", min_value=0, step=1000, value=400000
            )
        else:
            valor_inicial = VALORES_INICIAIS[opcao]

        nome = st.text_input("Seu nome", key="criar_nome")
        if st.button("Criar sala", type="primary", use_container_width=True):
            if nome.strip():
                game_id = criar_sala(valor_inicial)
                entrar_na_sala(game_id, nome.strip(), valor_inicial)
                entrar_na_sessao(game_id, nome.strip())
                st.rerun()
            else:
                st.error("Digite seu nome.")

    with aba_entrar:
        codigo = st.text_input("Código da sala", key="entrar_codigo").strip().upper()
        nome2 = st.text_input("Seu nome", key="entrar_nome")
        if st.button("Entrar na sala", type="primary", use_container_width=True):
            sala = get_sala(codigo) if codigo else None
            if not sala:
                st.error("Sala não encontrada. Confira o código com quem criou o jogo.")
            elif not nome2.strip():
                st.error("Digite seu nome.")
            else:
                entrar_na_sala(codigo, nome2.strip(), sala["valor_inicial"])
                entrar_na_sessao(codigo, nome2.strip())
                st.rerun()


def tela_jogo():
    game_id = st.session_state.game_id
    meu_nome = st.session_state.meu_nome
    sala = get_sala(game_id)

    if sala is None:
        st.warning("Esta sala foi encerrada.")
        if st.button("Voltar ao início"):
            sair_da_sessao()
            st.rerun()
        return

    saldos = get_jogadores(game_id)
    outros = [j for j in saldos if j != meu_nome]

    # Barra de ações sempre visível no topo (sem depender da sidebar, que no
    # celular fica escondida atrás do menu ☰).
    col_titulo, col_atualizar = st.columns([3, 1])
    with col_titulo:
        st.title("🏦 Banco Imobiliário")
    with col_atualizar:
        st.write("")
        if st.button("🔄 Atualizar", use_container_width=True, key="atualizar_topo"):
            st.rerun()

    st.caption(f"Sala **{game_id}** · você é **{meu_nome}**")
    st.caption(
        "💡 Um refresh normal do navegador também funciona agora — você não perde seu lugar na sala."
    )

    with st.sidebar:
        st.subheader("🔑 Código da sala")
        st.code(game_id, language=None)
        st.caption("Compartilhe este código para outros jogadores entrarem pelo próprio dispositivo.")
        st.write(f"Você é: **{meu_nome}**")
        if st.button("Atualizar agora", key="atualizar_sidebar"):
            st.rerun()
        st.divider()
        if st.button("Sair da sala (só neste dispositivo)"):
            sair_da_sessao()
            st.rerun()
        with st.expander("⚠️ Encerrar sala para todos"):
            st.caption("Apaga o jogo e o histórico para todo mundo.")
            if st.button("Encerrar definitivamente", type="secondary"):
                encerrar_sala(game_id)
                sair_da_sessao()
                st.rerun()

    cols = st.columns(len(saldos))
    for c, (nome, saldo) in zip(cols, saldos.items()):
        label = f"{nome} (você)" if nome == meu_nome else nome
        c.metric(label, fmt(saldo))

    st.divider()

    if len(outros) == 0:
        st.info("Aguardando outros jogadores entrarem com o código da sala ao lado.")

    aba1, aba2, aba3, aba4 = st.tabs(
        ["💸 Pagar jogador", "🏦 Pagar ao banco", "💰 Receber do banco", "📜 Histórico"]
    )

    with aba1:
        if outros:
            destino = st.selectbox("Pagar para", outros, key="p_destino")
            valor = st.number_input("Valor (R$)", min_value=1000, step=1000, key="p_valor")
            motivo = st.text_input(
                "Motivo (opcional)", placeholder="Ex: aluguel da Rua XV", key="p_motivo"
            )
            if st.button("Confirmar pagamento", type="primary", key="p_btn"):
                ok, erro = registrar(game_id, meu_nome, destino, valor, motivo or "Pagamento")
                if ok:
                    st.success(f"Você pagou {fmt(valor)} para {destino}.")
                    st.rerun()
                else:
                    st.error(erro)
        else:
            st.info("Ainda não há outros jogadores na sala.")

    with aba2:
        valor = st.number_input("Valor (R$)", min_value=1000, step=1000, key="b_valor")
        motivo = st.text_input(
            "Motivo (opcional)", placeholder="Ex: Imposto de Renda", key="b_motivo"
        )
        if st.button("Confirmar pagamento ao banco", type="primary", key="b_btn"):
            ok, erro = registrar(game_id, meu_nome, "Banco", valor, motivo or "Pagamento ao banco")
            if ok:
                st.success(f"Você pagou {fmt(valor)} ao banco.")
                st.rerun()
            else:
                st.error(erro)

    with aba3:
        valor = st.number_input("Valor (R$)", min_value=1000, step=1000, key="r_valor")
        motivo = st.text_input(
            "Motivo (opcional)", placeholder="Ex: Passou pelo início", key="r_motivo"
        )
        if st.button("Confirmar recebimento", type="primary", key="r_btn"):
            registrar(game_id, "Banco", meu_nome, valor, motivo or "Recebimento do banco")
            st.success(f"Você recebeu {fmt(valor)} do banco.")
            st.rerun()

    with aba4:
        hist = get_historico(game_id)
        if not hist:
            st.info("Nenhuma transação ainda.")
        else:
            for h in hist:
                st.write(f"`{h['hora']}` **{h['origem']}** → **{h['destino']}**: {fmt(h['valor'])} — {h['motivo']}")


def main():
    init_db()
    restaurar_sessao_da_url()
    if "game_id" not in st.session_state or "meu_nome" not in st.session_state:
        tela_entrada()
    else:
        tela_jogo()


if __name__ == "__main__":
    main()
