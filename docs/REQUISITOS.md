# Especificação de Requisitos — Rede de Vendas

**Versão:** 0.4.0 · **Data:** 18/10/2026 · **Autor:** Ginaldo Ribeiro da Silva

## 1. Visão geral

### 1.1 Objetivo
Gerenciar uma rede de lojas físicas: cadastros, estoque independente por loja, vendas com
desconto e comissão, transferências entre lojas e relatórios gerenciais.

### 1.2 Escopo
Aplicação web (frontend React + API FastAPI) e de linha de comando, com banco SQLite local.
Atende uma rede pequena ou média (dezenas de lojas, milhares de vendas por mês).

**Fora do escopo desta versão:** emissão fiscal (NF-e/NFC-e),
pagamentos, devolução parcial de itens, múltiplos usuários simultâneos.

### 1.3 Atores
| Ator | Descrição |
|------|-----------|
| Gerente da rede | Cadastra lojas, produtos e vendedores; consulta relatórios; transfere estoque |
| Vendedor | Registra vendas na loja em que está lotado |
| Estoquista | Registra entradas de mercadoria |

Na versão 0.4.0 os atores viraram dois perfis de acesso: **Gerente** (gerente da rede e
estoquista) e **Vendedor**. A matriz de permissões está na seção 3.1.

### 1.4 Glossário
| Termo | Significado |
|-------|-------------|
| SKU | Código único do produto na rede |
| Saldo | Quantidade de um produto disponível em uma loja |
| Faturamento | Soma dos totais líquidos (após desconto) das vendas concluídas |
| Margem | (preço de venda − custo) × quantidade, com valores do momento da venda |
| Ticket médio | Faturamento ÷ número de vendas |

## 2. Requisitos funcionais

| ID | Requisito | Comando CLI | Prioridade |
|----|-----------|-------------|------------|
| RF01 | Cadastrar loja (nome, cidade, UF) | `loja` | Alta |
| RF02 | Cadastrar produto (SKU, nome, preço, custo) | `produto` | Alta |
| RF03 | Cadastrar vendedor vinculado a uma loja, com % de comissão | `vendedor` | Alta |
| RF04 | Cadastrar cliente (nome, CPF e cidade opcionais) | `cliente` | Média |
| RF05 | Registrar entrada de estoque em uma loja | `entrada` | Alta |
| RF06 | Transferir estoque entre lojas, com histórico | `transferir` | Média |
| RF07 | Registrar venda com um ou mais itens, cliente opcional e desconto | `vender` | Alta |
| RF08 | Cancelar venda, devolvendo os itens ao estoque | `cancelar` | Alta |
| RF09 | Relatório de faturamento, nº de vendas e ticket médio por loja | `relatorio lojas` | Alta |
| RF10 | Ranking de vendedores com faturamento e comissão | `relatorio vendedores` | Alta |
| RF11 | Produtos mais vendidos com receita bruta e margem | `relatorio produtos` | Média |
| RF12 | Lista de itens com estoque abaixo de um mínimo, por loja | `relatorio estoque-baixo` | Média |
| RF13 | Faturamento mensal de um ano | `relatorio mensal` | Média |
| RF14 | Filtrar relatórios RF09–RF11 por período (data inicial e final) | `--inicio` / `--fim` | Média |
| RF15 | Gerar dados de demonstração em banco vazio | `exemplo` | Baixa |
| RF16 | Listar lojas, produtos, vendedores e clientes; inativos só com `--todos` | `listar` | Alta |
| RF17 | Editar loja, produto, vendedor ou cliente, alterando só os campos informados | `editar` | Alta |
| RF18 | Desativar e reativar vendedor ou produto, sem apagar histórico | `desativar` / `reativar` | Alta |
| RF19 | Migrar automaticamente bancos da versão 0.1.0 ao abrir | (automático) | Alta |
| RF20 | API REST sob `/api` com todas as operações de RF01–RF18, documentação interativa em `/docs` | `uvicorn rede_vendas.api:app` | Alta |
| RF21 | Frontend web com as telas Painel, Nova venda, Vendas, Estoque e Cadastros | `frontend/` | Alta |
| RF22 | Listar o estoque por loja e as vendas recentes com o detalhe dos itens | `listar estoque`, `listar vendas`, `GET /api/vendas/{id}` | Média |
| RF23 | Entrar e sair com login e senha; sessão de 12 horas | tela de login, `/api/auth/*` | Alta |
| RF24 | Perfis Gerente e Vendedor com permissões diferentes (seção 3.1) | (todas as rotas) | Alta |
| RF25 | Gerente cria acessos, redefine senhas e desativa/reativa usuários | Cadastros → Acessos, `/api/usuarios` | Alta |
| RF26 | Usuário troca a própria senha | Minha conta, `POST /api/auth/senha` | Alta |
| RF27 | Criar o primeiro gerente pelas variáveis de ambiente ou pelo terminal | `criar-usuario`, `REDE_VENDAS_ADMIN_*` | Alta |
| RF28 | Backup consistente do banco com o sistema em uso | `backup`, `deploy/backup.sh` | Alta |
| RF29 | Implantação com Docker Compose e HTTPS automático | `docker-compose.yml`, `docs/DEPLOY.md` | Alta |

## 3. Regras de negócio

| ID | Regra |
|----|-------|
| RN01 | Valores monetários são armazenados em centavos (inteiros) e exibidos no formato `R$ 1.234,56` |
| RN02 | A venda ocorre na loja do vendedor e baixa o estoque daquela loja |
| RN03 | O saldo de estoque nunca pode ficar negativo |
| RN04 | O desconto por venda vai de 0% a 30% |
| RN05 | Vendedor inativo não pode registrar vendas; produto inativo não pode ser vendido |
| RN06 | O custo de um produto não pode ser maior que o preço de venda |
| RN07 | Cada venda guarda os valores do momento: preço e custo de cada item, loja e % de comissão do vendedor. Edições posteriores não alteram vendas passadas |
| RN08 | Venda, cancelamento e transferência são atômicos: ou tudo é gravado, ou nada |
| RN09 | Relatórios consideram apenas vendas com status `CONCLUIDA` |
| RN10 | Uma venda cancelada não pode ser cancelada novamente |
| RN11 | Origem e destino de uma transferência devem ser lojas diferentes |
| RN12 | SKU de produto, nome de loja e CPF de cliente são únicos; UF tem exatamente 2 letras |
| RN13 | Comissão de cada venda = total líquido × % de comissão gravada na venda; o ranking soma por vendedor e loja da venda |
| RN14 | Quantidades de entrada, transferência e itens devem ser positivas |
| RN15 | Cadastros não são apagados, apenas desativados, para preservar o histórico de vendas |
| RN16 | Uma edição precisa informar pelo menos um campo; campos de texto obrigatórios não podem ficar vazios |
| RN17 | Ao editar preço ou custo, a regra RN06 vale para o par final (o valor novo com o valor atual do outro campo) |
| RN18 | Comissão do vendedor entre 0% e 100%; ativar quem já está ativo (ou desativar quem já está inativo) é recusado |
| RN19 | Produtos inativos não aparecem no relatório de estoque baixo |
| RN20 | Dinheiro usa arredondamento comercial (meio centavo sobe) no servidor e na tela, para o total exibido ser o total cobrado |
| RN21 | O limite de "estoque baixo" é o mesmo no indicador e na lista do painel (10 unidades) |
| RN22 | Senha com no mínimo 8 caracteres; login único (sem diferenciar maiúsculas), só letras, números, ponto e sublinhado |
| RN23 | Usuário vendedor é ligado a exatamente um vendedor cadastrado, e cada vendedor tem no máximo um acesso |
| RN24 | O vendedor logado vende sempre em nome próprio e na própria loja, mesmo que a requisição informe outro vendedor |
| RN25 | Após 5 senhas erradas seguidas, o login fica bloqueado por 15 minutos; a mensagem não revela se o login existe |
| RN26 | Trocar ou redefinir a senha, ou desativar o usuário, encerra todas as sessões dele |
| RN27 | Ninguém desativa o próprio usuário; a rede sempre mantém pelo menos um gerente ativo |
| RN28 | O primeiro gerente das variáveis de ambiente só é criado se não houver nenhum gerente ativo |

### 3.1 Permissões por perfil

| Ação | Gerente | Vendedor |
|------|:-------:|:--------:|
| Registrar venda | sim, escolhendo o vendedor | sim, só em nome próprio |
| Ver vendas e detalhes | todas | só as próprias |
| Cancelar venda | sim | não |
| Ver estoque | todas as lojas | só a própria loja (na tela de venda) |
| Entrada e transferência de estoque | sim | não |
| Ver produtos | todos, inclusive inativos | só os ativos |
| Cadastrar cliente | sim | sim |
| Editar cadastros, ativar/desativar | sim | não |
| Painel e relatórios | sim | não |
| Gerenciar acessos | sim | não |
| Trocar a própria senha | sim | sim |

## 4. Requisitos não funcionais

| ID | Categoria | Requisito |
|----|-----------|-----------|
| RNF01 | Plataforma | Python 3.10 ou superior; Windows, Linux e macOS |
| RNF02 | Dependências | Núcleo e CLI só com a biblioteca padrão; API com FastAPI e Uvicorn (extra `api`); frontend com React e Vite |
| RNF03 | Persistência | SQLite com chaves estrangeiras ativas e restrições `CHECK` no próprio banco |
| RNF04 | Integridade | Transações explícitas em operações que alteram mais de uma tabela (RN08) |
| RNF05 | Segurança | Consultas SQL sempre parametrizadas; nomes de tabela validados contra lista fixa |
| RNF06 | Usabilidade | Mensagens de erro em português, sem stack trace: código de saída 1 na CLI; 400/404/409/422 com `detail` na API; aviso na tela no frontend |
| RNF11 | Interface | Telas utilizáveis a partir de 390 px de largura (celular), sem rolagem horizontal da página |
| RNF12 | Acessibilidade | Foco visível pelo teclado, rótulos em todos os campos, contraste adequado e animações desligadas com `prefers-reduced-motion` |
| RNF13 | Implantação | Em produção, um único processo (Uvicorn, 1 worker) serve API e frontend compilado, atrás do Caddy com HTTPS |
| RNF14 | Segurança: senhas | Hash scrypt com sal aleatório por usuário; comparação em tempo constante; senha nunca guardada nem registrada em log |
| RNF15 | Segurança: sessão | Token aleatório de 256 bits em cookie `HttpOnly`, `Secure` (desligável só em rede local) e `SameSite=Strict`; no banco fica apenas o hash SHA-256 do token |
| RNF16 | Segurança: navegador | Cabeçalhos CSP, `X-Frame-Options: DENY`, `nosniff`, HSTS (Caddy); `Cache-Control: no-store` nas respostas da API; `/docs` desligado em produção |
| RNF17 | Segurança: servidor | Container sem root; só o Caddy expõe portas; segredos em `.env`, fora do Git |
| RNF18 | Operação | Verificação de saúde (`/api/saude`) no container; logs com rotação; backup diário com retenção de 14 dias e cópia fora do volume |
| RNF19 | Entrega contínua | GitHub Actions roda lint, testes, build do frontend e build + teste de subida da imagem a cada envio |
| RNF07 | Idioma | Código, nomes, mensagens e documentação em português do Brasil |
| RNF08 | Qualidade | Python aprovado no `ruff check` e `ruff format`; TypeScript em modo `strict`, sem erros no `npm run build` |
| RNF09 | Testabilidade | Toda regra de negócio coberta por teste automatizado (seção 6) |
| RNF10 | Desempenho | Relatórios em menos de 1 s com até 100 mil vendas (índices em `vendas.data_hora` e `itens_venda.venda_id`) |

## 5. Modelo de dados

```
lojas 1──* vendedores 1──* vendas *──1 clientes (opcional)
  │                          │
  └──* estoque *──1 produtos 1──* itens_venda *──1 vendas
lojas 1──* transferencias *──1 produtos
```

| Tabela | Chave | Observações |
|--------|-------|-------------|
| `lojas` | `id` | `nome` único, `uf` com 2 caracteres |
| `produtos` | `id` | `sku` único; `preco_centavos`, `custo_centavos` ≥ 0; `ativo` 0/1 |
| `estoque` | (`loja_id`, `produto_id`) | `quantidade` ≥ 0 |
| `vendedores` | `id` | `comissao_pct` entre 0 e 100; `ativo` 0/1 |
| `clientes` | `id` | `cpf` único quando informado |
| `vendas` | `id` | `status` ∈ {CONCLUIDA, CANCELADA}; `comissao_pct` congelada (RN07) |
| `itens_venda` | `id` | preço e custo unitários congelados (RN07) |
| `transferencias` | `id` | histórico de movimentação entre lojas |

## 6. Rastreabilidade (regra → teste)

Arquivos: `tests/test_rede_vendas.py` (operações e relatórios), `tests/test_cadastros.py`
(listagem, edição, ativação e migração) e `tests/test_api.py` (API REST).
O frontend foi verificado por navegação automatizada (Playwright), não por testes no repositório (ver RF-F11).

| Requisito / Regra | Teste |
|-------------------|-------|
| RN01 | `test_conversao_monetaria` |
| RF07, RN02, RN04 | `test_venda_baixa_estoque_e_aplica_desconto`, `test_desconto_acima_do_limite_rejeitado` |
| RN03, RN08 | `test_estoque_insuficiente_nao_grava_nada` |
| RF08, RN10 | `test_cancelamento_devolve_estoque` |
| RF06, RN08 | `test_transferencia_atomica` |
| RN05 | `test_vendedor_inativo_nao_vende` |
| RN06 | `test_custo_maior_que_preco_rejeitado` |
| RN11 | `test_transferencia_para_mesma_loja_rejeitada` |
| RN12 | `test_sku_duplicado_rejeitado` |
| RF09–RF11, RN07, RN09, RN13 | `test_relatorios_ignoram_canceladas` |
| RF12 | `test_estoque_baixo_inclui_produto_sem_registro` |
| RF15, RNF06 | `test_cli_fluxo_completo` |
| RF16 | `test_listagens`, `test_produto_inativo_nao_vende_e_sai_das_listagens` |
| RF17, RN16 | `test_editar_altera_somente_campos_informados`, `test_editar_sem_campos_rejeitado`, `test_editar_registro_inexistente_rejeitado`, `test_editar_loja_valida_campos`, `test_editar_cliente_string_vazia_apaga_valor` |
| RN12 (edição) | `test_editar_cpf_duplicado_rejeitado` |
| RN17 | `test_editar_produto_valida_par_preco_custo` |
| RN07 (edição) | `test_mudar_preco_nao_altera_vendas_passadas` |
| RN07, RN13 | `test_mudar_comissao_e_loja_nao_altera_vendas_passadas` |
| RF18, RN05, RN19 | `test_produto_inativo_nao_vende_e_sai_das_listagens`, `test_reativar_vendedor_volta_a_vender` |
| RN18 | `test_editar_vendedor_valida_loja_e_comissao`, `test_desativar_duas_vezes_rejeitado`, `test_desativar_entidade_nao_suportada` |
| RF19 | `test_migracao_de_banco_da_versao_anterior` |
| RF16–RF18 (CLI) | `test_cli_listar_editar_desativar` |
| RN20 | `test_desconto_usa_arredondamento_comercial`, `test_arredondamento_comercial` |
| RF20, RNF06 | `tests/test_api.py` (10 testes: cadastros, venda e cancelamento, estoque, relatórios, 400/404/409/422) |
| RF22 | `test_venda_completa_e_cancelamento`, `test_transferencia` (API) |
| RF23, RN25, RNF15 | `test_login_cria_cookie_seguro_e_sair_encerra_sessao`, `test_senha_errada_e_bloqueio_apos_5_tentativas`, `test_login_inexistente_tem_a_mesma_mensagem`, `test_token_guardado_so_como_hash`, `test_sessao_expirada` |
| RF24, 3.1 | `test_sem_login_tudo_e_401_menos_saude_e_entrar`, `test_vendedor_nao_acessa_rotas_de_gerente`, `test_vendedor_ve_so_proprias_vendas_e_proprio_estoque`, `test_vendedor_cadastra_cliente_mas_nao_edita` |
| RN24 | `test_vendedor_vende_sempre_em_nome_proprio`, `test_gerente_precisa_informar_vendedor` |
| RF25, RN26, RN27 | `test_gerente_gerencia_usuarios`, `test_rede_nunca_fica_sem_gerente` |
| RF26, RN26 | `test_trocar_propria_senha_encerra_sessoes` |
| RF27, RN28 | `test_primeiro_gerente_criado_pelas_variaveis`, `test_cli_criar_usuario_e_backup` |
| RF28 | `test_cli_criar_usuario_e_backup` |
| RN22, RN23, RNF14 | `test_regras_de_criacao_de_usuario`, `test_senha_guardada_como_hash_com_sal` |
| RNF16 | `test_cabecalhos_de_seguranca` |
| RF29, RNF17–RNF19 | Workflow `.github/workflows/ci.yml` (build da imagem e teste de subida com login) |

## 7. Pendências conhecidas e requisitos futuros

Lacunas da versão atual, registradas para não serem confundidas com funcionalidades prontas:

| ID | Descrição |
|----|-----------|
| RF-F01 | ~~Listar, editar e desativar cadastros~~ — **entregue na 0.2.0** (RF16–RF18) |
| RF-F02 | ~~Perfis de acesso com autenticação~~ — **entregue na 0.4.0** (RF23–RF27). Perfil separado de estoquista continua pendente |
| RF-F03 | Validação de dígitos verificadores do CPF |
| RF-F04 | Devolução parcial de itens de uma venda |
| RF-F05 | Metas mensais por loja e por vendedor |
| RF-F06 | ~~API REST~~ — **entregue na 0.3.0** (RF20) |
| RF-F08 | Desativar lojas (exige decidir o destino do estoque e dos vendedores da loja) |
| RF-F09 | Histórico de alterações de cadastro (quem mudou o quê e quando) |
| RF-F10 | Excluir cadastros criados por engano que ainda não têm nenhuma venda |
| RF-F11 | Testes automatizados do frontend (Vitest para componentes, Playwright para fluxos) |
| RF-F12 | Paginação e busca na lista de vendas (hoje mostra as 100 mais recentes) |
| RF-F13 | Migrar para PostgreSQL, para várias instâncias e muitos acessos simultâneos |
| RF-F14 | Registro de auditoria: quem cancelou cada venda e quem alterou cada cadastro (hoje só vai para o log) |
| RF-F15 | Login com mais segurança: verificação em duas etapas para gerentes e aviso de senha fraca |
| RF-F07 | Agente de IA que responda perguntas em linguagem natural usando as funções de `relatorios.py` como ferramentas |

## 8. Histórico de versões

| Versão | Mudanças |
|--------|----------|
| 0.1.0 | Cadastros, estoque, vendas, cancelamento, transferências e relatórios |
| 0.2.0 | Listagem, edição e ativação de cadastros (RF16–RF18); comissão e loja congeladas na venda (RN07, RN13); migração automática (RF19). Correção: o ranking de vendedores passava a recalcular vendas antigas ao mudar comissão ou loja |
| 0.3.0 | API FastAPI (RF20), frontend React (RF21), listagem de estoque e vendas (RF22). Correção: arredondamento do desconto diferia entre tela e servidor em meio centavo (RN20) |
| 0.4.0 | Autenticação e perfis (RF23–RF27), backup (RF28), deploy com Docker Compose e Caddy (RF29), cabeçalhos de segurança e CI |
