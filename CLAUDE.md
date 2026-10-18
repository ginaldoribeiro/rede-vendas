# Rede de Vendas — instruções para o agente

## Comandos
- Testes: `python -m pytest -q` (devem passar antes de qualquer entrega)
- Frontend: `cd frontend && npm run build` (checa tipos; deve passar sem erros)
- Rodar: `REDE_VENDAS_COOKIE_SEGURO=0 uvicorn rede_vendas.api:app --reload` + `cd frontend && npm run dev`
- Deploy: `docker compose up -d --build` (guia em `docs/DEPLOY.md`)
- Qualidade: `ruff format . && ruff check .` (sem apontamentos)
- Demo: `python -m rede_vendas --db demo.db exemplo` e depois `relatorio lojas`

## Convenções
- Código, nomes e mensagens em português do Brasil.
- Somente biblioteca padrão em `rede_vendas/`; dependências novas só com justificativa.
- Dinheiro sempre em centavos (`int`); converter só na borda (`reais_para_centavos`, `formatar_reais`).
- Regras de negócio ficam em `servicos.py` e lançam `ErroNegocio` (ou `NaoEncontrado`); CLI e API só traduzem (API: 400/404/409).
- O frontend nunca é a fonte da verdade: cálculos mostrados na tela devem bater com o servidor.
- Arredondamento de dinheiro: sempre `arredondar()` (meio centavo sobe), nunca `round()`.
- API: rotas sob `/api`, dinheiro em centavos, um teste em `tests/test_api.py` por rota nova.
- Permissões: toda rota nova entra num dos routers `publico`, `logado` ou `gerencia` (api.py), e ganha teste de 401/403 em `tests/test_autenticacao.py`. Rotas de vendedor filtram pelo `usuario` logado no servidor, nunca por parâmetro do cliente.
- Segurança: nunca guardar senha ou token em texto puro; nunca logar senhas.
- Frontend: textos em português, sentence case; cores e espaçamentos só via variáveis de `estilo.css`.
- Operações que alteram várias tabelas usam `with conn:` (transação atômica).
- Relatórios filtram `status = 'CONCLUIDA'`.
- Todo recurso novo ganha teste em `tests/` usando banco `:memory:`.
- Nova regra de negócio: registrar em `docs/REQUISITOS.md` (RF/RN) e na tabela de rastreabilidade.
- Dados que podem mudar no cadastro (preço, comissão, loja) são copiados para a venda; relatórios usam a cópia.
- Mudança de esquema: atualizar `SCHEMA` e adicionar o passo em `_migrar` (banco.py), com teste.
