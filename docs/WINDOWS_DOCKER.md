\# Instalação do Rede de Vendas no Windows



\## Requisitos



\- Windows 10 ou 11

\- Docker Desktop instalado e em execução

\- Docker Compose disponível



\## Configuração



1\. Abra o PowerShell na pasta do projeto.

2\. Crie o arquivo `.env` a partir de `.env.example`, caso ainda não exista.

3\. Configure as variáveis necessárias no `.env`.

4\. Para utilização local via HTTP, defina `DOMINIO=:80` e `COOKIE\_SEGURO=0`.

5\. Defina uma senha forte para o administrador.



\## Iniciar a aplicação



Execute:



```powershell

docker compose up -d --build

```



Para verificar os contêineres:



```powershell

docker compose ps

```



Para visualizar os registros:



```powershell

docker compose logs --tail=100

```



\## Encerrar a aplicação



```powershell

docker compose down

```



\## Segurança



\- Nunca publique o arquivo `.env` no GitHub.

\- Não inclua senhas reais nos exemplos.

\- Não publique arquivos de banco de dados ou backups.

\- Em produção com HTTPS, revise as configurações de domínio e cookies seguros.



