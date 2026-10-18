# Rede de Vendas

Sistema para gerenciar uma rede de lojas: cadastros, estoque por loja, vendas com desconto
e comissão, cancelamento com estorno, transferências e relatórios gerenciais.

```
frontend/ (React)  →  /api (FastAPI)  →  servicos.py / relatorios.py  →  SQLite
```

| Camada | Pasta | Tecnologia |
|--------|-------|------------|
| Frontend | `frontend/` | React 19, TypeScript, Vite |
| API | `rede_vendas/api.py` | FastAPI (documentação em `/docs`) |
| Regras de negócio | `rede_vendas/servicos.py`, `relatorios.py` | Python puro |
| Banco de dados | `rede_vendas/banco.py` | SQLite, criado e migrado automaticamente |
| Linha de comando | `rede_vendas/cli.py` | `python -m rede_vendas` |

- Especificação (requisitos, regras de negócio, modelo de dados, rastreabilidade): [docs/REQUISITOS.md](docs/REQUISITOS.md)
- **Colocar no ar** (servidor com HTTPS, rede local ou Render/Railway): [docs/DEPLOY.md](docs/DEPLOY.md)

## Acesso e perfis
Todo acesso exige login.
- **Gerente:** acessa tudo, inclusive cancelar vendas, relatórios e criar acessos.
- **Vendedor:** registra vendas em nome próprio (na loja dele) e vê só as próprias vendas.

## Requisitos
- Python 3.10+
- Node.js 20+ (só para o frontend)

## Instalação
```bash
pip install -e ".[dev]"          # API + ferramentas de teste e qualidade
cd frontend && npm install && cd ..
python -m rede_vendas exemplo    # opcional: 3 lojas na Paraíba e ~150 vendas de demonstração
python -m rede_vendas criar-usuario gerente "Seu Nome" --perfil gerente   # pede a senha
```

## Rodando em desenvolvimento
Dois terminais:
```bash
# terminal 1: API em http://127.0.0.1:8000 (documentação em /docs)
# COOKIE_SEGURO=0 permite o login por http:// no desenvolvimento
REDE_VENDAS_COOKIE_SEGURO=0 uvicorn rede_vendas.api:app --reload

# terminal 2: frontend em http://localhost:5173 (repassa /api para a porta 8000)
cd frontend && npm run dev
```
O banco usado é `rede_vendas.db` na pasta onde a API roda. Para usar outro arquivo:
`REDE_VENDAS_DB=caminho/outro.db uvicorn rede_vendas.api:app`.

## Rodando em produção
O caminho recomendado é Docker Compose com HTTPS automático:
```bash
cp .env.example .env   # preencha domínio e gerente inicial
docker compose up -d --build
```
O passo a passo completo, com backup e atualização, está em [docs/DEPLOY.md](docs/DEPLOY.md).

## Telas
- **Painel:** faturamento, vendas, ticket médio, gráfico mensal, lojas, melhores vendedores e produtos para repor.
- **Nova venda:** escolha do vendedor (o estoque é o da loja dele), busca de produtos e um cupom com quantidades, desconto e total.
- **Vendas:** últimas vendas com detalhes dos itens e cancelamento.
- **Estoque:** saldos por loja, entrada de mercadoria e transferência entre lojas.
- **Cadastros:** lojas, produtos, vendedores e clientes, com edição e ativação/desativação.

## API
Todas as rotas ficam sob `/api`; veja e teste todas em `http://127.0.0.1:8000/docs`.
Valores monetários entram e saem em **centavos** (inteiros).
Erros: sem login → 401, sem permissão → 403, regra de negócio → 400, não encontrado → 404,
duplicado → 409, dado mal formatado → 422.

## Linha de comando
A CLI continua disponível e usa as mesmas regras:
```bash
python -m rede_vendas relatorio lojas
python -m rede_vendas vender 1 1:2 2:1 --desconto 5
python -m rede_vendas listar produtos --todos
python -m rede_vendas backup pasta/de/backups
python -m rede_vendas --help
```

## Qualidade
```bash
python -m pytest -q              # testes de regras, CLI e API
ruff format . && ruff check .    # formatação e lint do Python
cd frontend && npm run build     # checagem de tipos do TypeScript + build
```

## Regras de negócio principais
- Valores em **centavos**; arredondamento comercial (meio centavo sobe), igual na tela e no servidor.
- A venda acontece na loja do vendedor e baixa o estoque daquela loja.
- Venda, cancelamento e transferência são **atômicos**: se algo falha, nada é gravado.
- A venda guarda preço, custo, loja e comissão do momento: editar cadastros não altera o passado.
- Cadastros não são apagados, só desativados. Produto ou vendedor inativo não vende.
- Desconto de 0% a 30%. Custo não pode superar o preço. Relatórios ignoram vendas canceladas.
