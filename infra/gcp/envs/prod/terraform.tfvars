project_id = "project-7c9b25a3-af2a-416b-ac9"
region     = "us-central1"
zone       = "us-central1-a"
name       = "ai-doc-factory"

# Cota de vCPU do projeto confirmada em 200 (não é o limitador); o tamanho
# aqui é escolha de custo. e2-standard-8 ~ US$196/mês rodando 24x7.
machine_type = "e2-standard-8"
disk_size_gb = 50

repo_url          = "https://github.com/EmmanuelBMoraes/ai-doc-factory.git"
github_repository = "EmmanuelBMoraes/ai-doc-factory"
deploy_branch     = "master"

domain     = ""
acme_email = ""

ssh_source_ranges = ["35.235.240.0/20"]
enable_snapshots  = true
