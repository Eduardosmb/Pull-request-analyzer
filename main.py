import os
import pandas as pd
from github import Github, Auth, GithubException
from github.GithubException import RateLimitExceededException
from dotenv import load_dotenv
import time

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    raise ValueError("Token do GitHub não encontrado. Verifique seu arquivo .env")


REPOSITORIOS_ALVO = [
    # "pytorch/pytorch",
    "pygame/pygame",
    "tensorflow/tensorflow",
    "microsoft/vscode",
    "pandas-dev/pandas"
]
# ----------------------------------------

PRS_POR_REPOSITORIO = 200 

COLUNAS = [
    "repo", "pr_number", "title", "author", "state", "was_merged",
    "body", "created_at", "closed_at", "merged_at",
    "additions", "deletions", "changed_files", "commits", "comments_count", "review_comments_count"
]
# ---------------------

def extrair_dados_pr(pr, repo_name):
    """Extrai um dicionário de dados de um objeto PullRequest."""
    return {
        "repo": repo_name,
        "pr_number": pr.number,
        "title": pr.title,
        "author": pr.user.login if pr.user else None,
        "state": pr.state,
        "was_merged": pr.merged,
        "body": pr.body,
        "created_at": pr.created_at,
        "closed_at": pr.closed_at,
        "merged_at": pr.merged_at,
        "additions": pr.additions,
        "deletions": pr.deletions,
        "changed_files": pr.changed_files,
        "commits": pr.commits,
        "comments_count": pr.comments,
        "review_comments_count": pr.review_comments
    }

def coletar_dados():
    """Função principal para conectar e coletar os dados."""
    
    print("Iniciando conexão com a API do GitHub...")
    try:
        auth = Auth.Token(GITHUB_TOKEN)
        g = Github(auth=auth, per_page=100) 
        user = g.get_user()
        print(f"Conectado como: {user.login}")
        
        limite = g.get_rate_limit().resources.core
        print(f"Requisições restantes: {limite.remaining}/{limite.limit}")
    
    except RateLimitExceededException:
        print("Erro ao conectar: Limite de taxa da API já estourado.")
        return
    except Exception as e:
        print(f"Erro ao conectar ao GitHub: {e}") 
        return

    todos_os_dados = []

    for repo_name in REPOSITORIOS_ALVO:
        print(f"\n--- Processando repositório: {repo_name} ---")
        
        try:
            limite = g.get_rate_limit().resources.core
            print(f"  [Status] Requisições restantes: {limite.remaining}")
            if limite.remaining < 50: 
                print("!! ATENÇÃO: Limite de taxa baixo. Pausando por 15 min... !!")
                time.sleep(15 * 60)
        except RateLimitExceededException:
            print("!!! LIMITE DE TAXA DA API ATINGIDO !!!")
            print("Pausando por 1 hora. O script pode ser interrompido e continuado depois.")
            time.sleep(60 * 60)
            continue 

        try:
            repo = g.get_repo(repo_name)
            pulls = repo.get_pulls(state='closed', sort='created', direction='desc')
            

            contador_aceitos = 0
            iteracoes_totais = 0 

            for pr in pulls:
                if contador_aceitos >= PRS_POR_REPOSITORIO:
                    print(f"Limite de {PRS_POR_REPOSITORIO} PRs ACEITOS atingido para {repo_name}.")
                    break
                
                iteracoes_totais += 1

                if pr.merged:
                    print(f"  Coletando PR ACEITO #{pr.number}: {pr.title[:50]}...")
                    dados_pr = extrair_dados_pr(pr, repo_name)
                    todos_os_dados.append(dados_pr)
                    contador_aceitos += 1

                if iteracoes_totais % 100 == 0:
                     print(f"  [Status] {iteracoes_totais} PRs verificados... {contador_aceitos} aceitos encontrados.")
            
            if contador_aceitos < PRS_POR_REPOSITORIO:
                print(f"  [Aviso] Não foi possível encontrar {PRS_POR_REPOSITORIO} PRs aceitos.")
                print(f"  Total encontrado para {repo_name}: {contador_aceitos}")

        except RateLimitExceededException:
            print("!!! LIMITE DE TAXA DA API ATINGIDO (durante o loop) !!!")
            print("Pausando por 1 hora. Os dados coletados até agora serão salvos.")
            time.sleep(60 * 60) 
        except GithubException as e:
            print(f"Erro ao processar repositório {repo_name}: {e}")
            if e.status == 404:
                print("Repositório não encontrado ou privado.")
            continue 
        except Exception as e:
            print(f"Um erro inesperado ocorreu em {repo_name}: {e}")
            continue

    print("\n--- Coleta concluída! ---")
    
    if not todos_os_dados:
        print("Nenhum dado foi coletado.")
        return

    df = pd.DataFrame(todos_os_dados, columns=COLUNAS)
    
    output_filename = "pull_requests_aceitos.csv"
    df.to_csv(output_filename, index=False, encoding='utf-8-sig')
    
    print(f"Total de {len(df)} Pull Requests (ACEITOS) salvos em '{output_filename}'")
    print("\nResumo dos dados:")
    print(df.head())
    print(f"\nDistribuição por repositório:\n{df['repo'].value_counts()}")

if __name__ == "__main__":
    coletar_dados()