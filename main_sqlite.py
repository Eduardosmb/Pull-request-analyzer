

import os
import pandas as pd
import sqlite3
import time
from datetime import datetime
from dotenv import load_dotenv
from github import Github, Auth
from github.GithubException import RateLimitExceededException, GithubException

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    raise ValueError("Token do GitHub não encontrado. Verifique seu arquivo .env")

# Lista de repositórios (ex.: "owner/repo")
REPOSITORIOS_ALVO = [
    # "jax-ml/jax", 
    # "google/material-design-icons", 
    # "google/guava", 
    # "matplotlib/matplotlib"
    # "plotly/plotly.py",
    # "apache/commons-lang",
    # "mwaskom/seaborn",
    # "twbs/icons",
    # "chartjs/Chart.js",
    # "apache/commons-collections4",
    # "bokeh/bokeh",
    # "lodash/lodash"
]

PRS_POR_REPOSITORIO = 300
DB_PATH = "pull_requests.db"
CSV_OUTPUT = "pull_requests_aceitos.csv"

COLUNAS = [
    "repo", "pr_number", "title", "author", "state", "was_merged",
    "body", "created_at", "closed_at", "merged_at",
    "additions", "deletions", "changed_files", "commits", "comments_count", "review_comments_count"
]


def to_iso(dt):
    return dt.isoformat() if dt else None


def extrair_dados_pr(pr, repo_name):
    """Extrai um dicionário de dados de um objeto PullRequest."""
    return {
        "repo": repo_name,
        "pr_number": pr.number,
        "title": pr.title,
        "author": pr.user.login if pr.user else None,
        "state": pr.state,
        "was_merged": int(bool(pr.merged)),
        "body": pr.body,
        "created_at": to_iso(pr.created_at),
        "closed_at": to_iso(pr.closed_at),
        "merged_at": to_iso(pr.merged_at),
        "additions": pr.additions,
        "deletions": pr.deletions,
        "changed_files": pr.changed_files,
        "commits": pr.commits,
        "comments_count": pr.comments,
        "review_comments_count": pr.review_comments
    }


def init_db(db_path=DB_PATH):
    """Cria o banco e a tabela se não existirem."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS pull_requests (
            repo TEXT NOT NULL,
            pr_number INTEGER NOT NULL,
            title TEXT,
            author TEXT,
            state TEXT,
            was_merged INTEGER,
            body TEXT,
            created_at TEXT,
            closed_at TEXT,
            merged_at TEXT,
            additions INTEGER,
            deletions INTEGER,
            changed_files INTEGER,
            commits INTEGER,
            comments_count INTEGER,
            review_comments_count INTEGER,
            PRIMARY KEY (repo, pr_number)
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_merged_at ON pull_requests(merged_at)")
    conn.commit()
    conn.close()


def save_rows_to_sqlite(rows, db_path=DB_PATH):
    """Salva uma lista de dicionários no SQLite usando INSERT OR REPLACE."""
    if not rows:
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    insert_sql = """
    INSERT OR REPLACE INTO pull_requests (
        repo, pr_number, title, author, state, was_merged,
        body, created_at, closed_at, merged_at,
        additions, deletions, changed_files, commits, comments_count, review_comments_count
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    params = []
    for r in rows:
        params.append((
            r.get("repo"),
            int(r.get("pr_number")),
            r.get("title"),
            r.get("author"),
            r.get("state"),
            int(r.get("was_merged")),
            r.get("body"),
            r.get("created_at"),
            r.get("closed_at"),
            r.get("merged_at"),
            int(r.get("additions")) if r.get("additions") is not None else None,
            int(r.get("deletions")) if r.get("deletions") is not None else None,
            int(r.get("changed_files")) if r.get("changed_files") is not None else None,
            int(r.get("commits")) if r.get("commits") is not None else None,
            int(r.get("comments_count")) if r.get("comments_count") is not None else None,
            int(r.get("review_comments_count")) if r.get("review_comments_count") is not None else None,
        ))

    cur.executemany(insert_sql, params)
    conn.commit()
    conn.close()


def append_rows_to_csv(rows, csv_path=CSV_OUTPUT):
    """Anexa linhas a um CSV (cria com header se não existir)."""
    if not rows:
        # Se não há dados, garante que o arquivo existe (opcional)
        return

    df = pd.DataFrame(rows, columns=COLUNAS)
    header = not os.path.exists(csv_path)
    df.to_csv(csv_path, mode="a", header=header, index=False, encoding="utf-8-sig")


def coletar_repo(g, repo_name):
    """Coleta PRs aceitos de um repositório, retorna lista de dicionários (já filtrados)."""
    print(f"\n--- Iniciando coleta para: {repo_name} ---")
    repo = g.get_repo(repo_name)
    pulls = repo.get_pulls(state='closed', sort='created', direction='desc')

    coletados = []
    checked = 0
    for pr in pulls:
        # A cada PR verificado, verificamos se o usuário pediu interrupção
        try:
            checked += 1
            if pr.merged:
                print(f"  Coletando PR #{pr.number}: {pr.title[:60]}")
                dados = extrair_dados_pr(pr, repo_name)
                coletados.append(dados)

                if len(coletados) >= PRS_POR_REPOSITORIO:
                    print(f"  Alcançado limite de {PRS_POR_REPOSITORIO} PRs aceitos para {repo_name}.")
                    break
        except KeyboardInterrupt:
            # Permite ao usuário pressionar Ctrl+C dentro do loop de PRs para pular pro próximo repo.
            print("\n  >>> Interrupção detectada durante a coleta deste repositório (Ctrl+C).")
            print("  Salvando o que foi coletado até agora deste repo e pulando para o próximo.")
            break
    print(f"--- Fim da coleta para: {repo_name}. PRs coletados: {len(coletados)} (verificados: {checked}) ---")
    return coletados


def coletar_dados():
    """Função principal para conectar e iterar pelos repositórios."""
    print("Iniciando conexão com a API do GitHub...")
    auth = Auth.Token(GITHUB_TOKEN)
    g = Github(auth=auth, per_page=100)

    try:
        user = g.get_user()
        print(f"Conectado como: {user.login}")
    except Exception as e:
        print(f"Erro ao conectar ao GitHub: {e}")
        return

    # Inicializa DB (cria tabelas caso não existam)
    init_db(DB_PATH)

    for repo_name in REPOSITORIOS_ALVO:
        # Antes de iniciar, checamos limites (opcional)
        try:
            limite = g.get_rate_limit().resources.core
            if limite.remaining < 10:
                # se limite estiver muito baixo, pausamos um pouco para evitar erros; ajuste conforme desejar
                print(f"Limite de requisições baixo ({limite.remaining}). Pausando 60 segundos.")
                time.sleep(60)
        except Exception:
            pass

        try:
            rows = coletar_repo(g, repo_name)

            # Salva os dados deste repo imediatamente no DB e CSV
            if rows:
                save_rows_to_sqlite(rows, DB_PATH)
                append_rows_to_csv(rows, CSV_OUTPUT)
                print(f"  Dados de '{repo_name}' salvos no DB ({DB_PATH}) e anexados em '{CSV_OUTPUT}'.")
            else:
                # Mesmo que não haja PRs coletados, registramos um log
                print(f"  Nenhum PR aceito coletado para '{repo_name}' — nada adicionado.")

        except RateLimitExceededException:
            print("!!! LIMITE DE TAXA DA API ATINGIDO. Salvando progresso e saindo.")
            # Se atingir o limite, salvamos o que tiver sido feito (já salvo por repo) e encerramos.
            break
        except GithubException as e:
            print(f"Erro da API no repositório {repo_name}: {e}")
            # Pula para próximo repo
            continue
        except KeyboardInterrupt:
            # Caso o usuário aperte Ctrl+C fora do loop de PRs (ex.: durante espera), paramos inteiramente.
            print("\nExecução interrompida pelo usuário. Saindo.")
            break
        except Exception as e:
            print(f"Erro inesperado processando {repo_name}: {e}")
            continue

    print("\nColeta finalizada.")


if __name__ == "__main__":
    print("AVISO: pressione Ctrl+C durante a coleta de um repositório para pular para o próximo.")
    coletar_dados()
