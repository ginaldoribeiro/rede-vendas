# Guia de deploy — Rede de Vendas

Este guia coloca o sistema no ar num servidor próprio (VPS) com HTTPS, usando Docker Compose.
A mesma estrutura serve para a rede local de uma loja ou escola (seção 6) e para plataformas
como Render ou Railway (seção 7).

```
navegador ──HTTPS──▶ Caddy (portas 80/443, certificado automático)
                        └──▶ app (uvicorn: API + frontend) ──▶ /dados/rede_vendas.db (volume)
```

## 1. O que você precisa

- Um servidor Linux com 1 GB de RAM ou mais (Ubuntu 22.04/24.04, por exemplo).
- Docker e o plugin Compose instalados (`docker compose version` deve funcionar).
- Um domínio ou subdomínio apontando para o IP do servidor (registro DNS do tipo **A**),
  por exemplo `vendas.minhaloja.com.br`.
- Portas **80** e **443** liberadas no firewall do servidor e do provedor.

## 2. Primeira instalação

```bash
git clone https://github.com/<seu-usuario>/rede_vendas.git
cd rede_vendas
cp .env.example .env
nano .env        # preencha DOMINIO, ADMIN_LOGIN e uma ADMIN_SENHA forte
docker compose up -d --build
```

Acompanhe a subida com `docker compose logs -f`. Na primeira vez o Caddy leva alguns segundos
para obter o certificado HTTPS. Quando aparecer `Gerente inicial '...' criado`, abra
`https://SEU_DOMINIO`.

**Logo no primeiro acesso:**
1. Entre com `ADMIN_LOGIN` e `ADMIN_SENHA`.
2. Vá em **Minha conta** e troque a senha. A senha do `.env` deixa de valer depois disso.
3. Em **Cadastros**, cadastre lojas, produtos e vendedores.
4. Em **Cadastros → Acessos**, crie um acesso para cada vendedor.

> Dados de demonstração (opcional, só para testar):
> `docker compose exec app python -m rede_vendas exemplo`
> Não rode isso num sistema que já está em uso real.

## 3. Backup — configure no primeiro dia

O banco inteiro é um arquivo no volume `dados`. O script `deploy/backup.sh` faz uma cópia
consistente (segura com o sistema em uso), mantém 14 dias de backups e copia o mais recente
para fora do Docker, em `~/backups_rede_vendas`.

```bash
crontab -e
# todo dia às 3h30:
30 3 * * * /home/SEU_USUARIO/rede_vendas/deploy/backup.sh >> /home/SEU_USUARIO/backup.log 2>&1
```

Um backup que só existe no mesmo servidor não protege contra a perda do servidor. Envie a
pasta `~/backups_rede_vendas` para outro lugar (outro disco, Google Drive com `rclone`, etc.).

**Restaurar um backup:**
```bash
docker compose stop app
docker compose cp ~/backups_rede_vendas/rede_vendas_AAAAMMDD_HHMMSS.db app:/dados/rede_vendas.db
# o arquivo copiado chega como root; devolva-o ao usuário da aplicação, senão ele fica só leitura
docker compose run --rm --no-deps --user root app chown rede:rede /dados/rede_vendas.db
docker compose start app
```

## 4. Atualizar para uma nova versão

```bash
cd rede_vendas
./deploy/backup.sh               # sempre faça um backup antes
git pull
docker compose up -d --build
```

O banco é migrado automaticamente na subida. Se algo der errado, volte o código
(`git checkout <versão anterior>`), restaure o backup (seção 3) e suba de novo.

## 5. Operação do dia a dia

| Tarefa | Comando |
|--------|---------|
| Ver se está tudo de pé | `docker compose ps` (a coluna STATUS deve mostrar `healthy`) |
| Ver os logs | `docker compose logs -f app` |
| Criar gerente pelo terminal | `docker compose exec app python -m rede_vendas criar-usuario maria "Maria Souza" --perfil gerente` |
| Relatório rápido pelo terminal | `docker compose exec app python -m rede_vendas relatorio lojas` |
| Reiniciar | `docker compose restart app` |
| Senha esquecida | outro gerente usa **Acessos → Redefinir senha** |

## 6. Variante: rede local (sem internet, sem domínio)

Para usar só dentro da loja ou da escola, acessando pelo IP do computador servidor
(por exemplo `http://192.168.0.10`), use no `.env`:

```
DOMINIO=:80
COOKIE_SEGURO=0
```

Sem HTTPS, as senhas trafegam sem criptografia dentro da rede local. Só use essa variante numa
rede de confiança e nunca com a porta liberada para a internet.

## 7. Variante: plataformas gerenciadas (Render, Railway, Fly.io)

O `Dockerfile` funciona direto nessas plataformas, sem o Caddy, porque elas já fornecem HTTPS.

- **Disco persistente montado em `/dados`.** Sem isso, cada deploy apaga todas as vendas.
- **Uma única instância.** O SQLite e o limite de tentativas de login vivem num processo só.
  Não ative escalonamento horizontal.
- Variáveis: `REDE_VENDAS_ADMIN_LOGIN`, `REDE_VENDAS_ADMIN_SENHA`, `REDE_VENDAS_DOCS=0`
  (deixe `REDE_VENDAS_COOKIE_SEGURO` no padrão, ligado).
- Porta interna: 8000. Verificação de saúde: `/api/saude`.

Para várias instâncias ou muitos acessos simultâneos, o próximo passo é migrar para PostgreSQL
(pendência RF-F13 em `docs/REQUISITOS.md`).

## 8. O que este deploy já cuida

- HTTPS com certificado renovado automaticamente (Caddy) e HSTS.
- Login com senha protegida por scrypt; sessão em cookie `HttpOnly`, `Secure` e `SameSite=Strict`.
- Bloqueio de 15 minutos após 5 senhas erradas seguidas no mesmo login.
- Perfis: vendedor só vende em nome próprio e só vê as próprias vendas.
- Cabeçalhos de segurança (CSP, X-Frame-Options, nosniff) e `/docs` desligado em produção.
- Aplicação roda sem privilégios de root; só o Caddy fica exposto.
- Logs com rotação (10 MB × 3 arquivos) e verificação de saúde no container.
- CI no GitHub: testes, lint, build do frontend e da imagem a cada envio.

## 9. Problemas comuns

| Sintoma | Causa provável |
|---------|----------------|
| Login "funciona" mas volta para a tela de entrar | Acesso por `http://` com `COOKIE_SEGURO=1`. Use HTTPS ou, só em rede local, `COOKIE_SEGURO=0`. |
| Caddy não obtém certificado | DNS ainda não aponta para o servidor, ou portas 80/443 fechadas. Veja `docker compose logs caddy`. |
| `defina ADMIN_LOGIN no arquivo .env` | Falta o arquivo `.env` (passo 2). |
| "Muitas tentativas erradas" | Aguarde 15 minutos ou peça a um gerente para redefinir a senha. |
| Nenhum gerente consegue entrar | `docker compose exec app python -m rede_vendas criar-usuario novo_gerente "Nome" --perfil gerente` |
