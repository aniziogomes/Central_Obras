# Documentação de Regra de Negócio - Canteiro

Data da análise: 09/05/2026

Este documento descreve o Canteiro como produto operacional, não como implementação técnica. O objetivo é registrar o funcionamento do sistema, suas regras de negócio, permissões, dependências entre módulos, fluxos operacionais e pontos de atenção para evolução do produto.

## 1. Visão Geral do Produto

O Canteiro é um SaaS operacional para construtoras de pequeno e médio porte acompanharem obras, custos, orçamento, medições, fornecedores, equipe, alertas e comunicação com cliente.

O sistema resolve um problema central: dar ao gestor uma visão contínua do que está acontecendo nas obras, quanto está sendo gasto, qual é o estágio físico, quais riscos existem e o que pode ser mostrado ao cliente sem expor informações internas.

O produto se organiza ao redor de uma entidade principal: a obra. Quase todos os demais módulos existem para complementar a obra, medir sua execução, registrar seus custos, acompanhar sua equipe ou publicar sua evolução no portal do cliente.

Principais objetivos operacionais:

- Centralizar o cadastro e acompanhamento das obras.
- Controlar custos reais por obra e categoria.
- Comparar custo realizado, orçamento previsto e receita/contrato.
- Acompanhar medições físicas e financeiras.
- Monitorar alertas automáticos de prazo, custo, status e pagamentos.
- Permitir que o cliente veja um portal simplificado da obra, sem dados financeiros internos.
- Segregar dados por empresa para uso multiempresa.
- Dar ao gestor um painel diário de decisão rápida.

## 2. Usuários e Perfis

O sistema possui quatro perfis conceituais: admin, gestor, leitura e cliente.

### Admin

Objetivo: administrar usuários, empresas e acessar a operação interna.

Pode:

- Entrar no sistema interno.
- Visualizar todos os módulos operacionais.
- Criar, editar, ativar, desativar, excluir e redefinir senha de usuários internos.
- Administrar usuários vinculados à sua empresa ou, quando está sem empresa vinculada, atuar como admin global.
- Criar usuários gestores e usuários de leitura.
- Visualizar dados operacionais conforme o escopo de empresa.
- Exportar dados de módulos que oferecem exportação.

Regras importantes:

- O admin global é identificado por não estar vinculado a uma empresa.
- Admin global pode criar ou selecionar empresas para usuários.
- Admin vinculado a uma empresa fica restrito à sua própria empresa.
- Admin não pode desativar ou excluir a própria conta.
- Usuários de perfil cliente não são administrados no fluxo principal de usuários internos.

### Gestor

Objetivo: operar a rotina da construtora.

Pode:

- Criar e editar obras.
- Lançar, editar e excluir custos.
- Cadastrar fornecedores.
- Cadastrar equipe.
- Registrar medições.
- Importar planilhas.
- Gerar e revogar portal da obra.
- Atualizar canteiro, fotos e mensagens para o cliente.
- Visualizar dashboards, alertas e logs.

Regras importantes:

- Gestor recém-criado pode cair em onboarding pendente.
- Enquanto o onboarding estiver pendente, o gestor é direcionado para criar a primeira obra, o primeiro custo opcional e o link do portal.
- O gestor não administra usuários, salvo se também for admin.

### Leitura

Objetivo: consultar a operação sem alterar dados.

Pode:

- Acessar telas internas.
- Visualizar dashboards, obras, custos, fornecedores, equipe, medições, orçamento, alertas e logs.
- Exportar dados quando a tela permitir.

Não pode:

- Criar, editar ou excluir registros operacionais.
- Gerar ou revogar link de portal.
- Atualizar canteiro.
- Administrar usuários.

### Cliente

Objetivo: acompanhar uma obra pelo portal público.

Regras importantes:

- Cliente não acessa o sistema interno.
- Se tentar login interno, o acesso é bloqueado.
- O acesso do cliente acontece via link público do portal da obra.
- O portal mostra apenas informações escolhidas para comunicação: progresso, fase, previsão, fotos, mensagens e linha do tempo.
- O portal não mostra custos, fornecedores, equipe, orçamento interno, margem, documentos ou dados administrativos.

## 3. Empresas e Segregação de Dados

O Canteiro funciona com segregação por empresa. Cada obra, custo, fornecedor, equipe, medição, importação, foto e log carrega vínculo com uma empresa.

Objetivo da segregação:

- Impedir que uma empresa veja dados de outra.
- Permitir operação multiempresa.
- Permitir que o admin global gerencie empresas e usuários de forma centralizada.

Regras de empresa:

- Usuários internos normalmente pertencem a uma empresa.
- Admin global pode não pertencer a nenhuma empresa.
- Registros criados por usuários de empresa recebem o `empresa_id` da sessão.
- Registros filhos de uma obra herdam a empresa da obra.
- Quando uma obra muda de empresa, seus registros relacionados também precisam acompanhar essa mudança.
- Se não houver empresa explícita para inserção, o sistema usa uma empresa padrão operacional.

Ponto de atenção:

- A existência de uma empresa padrão resolve continuidade operacional, mas pode mascarar cadastros sem empresa correta. Em um SaaS multiempresa, isso deve ser monitorado para evitar dados colocados na empresa errada.

## 4. Entidades Principais do Produto

### Empresa

Representa uma construtora, cliente interno ou organização que usa o sistema.

Dados operacionais:

- Nome.
- Documento.
- Status ativo/inativo.
- Data de criação.

Impacto:

- Define o escopo de visibilidade dos usuários e registros.
- Serve como barreira de segurança operacional.

### Usuário

Representa uma pessoa com acesso ao sistema interno ou, conceitualmente, ao portal.

Dados operacionais:

- Nome.
- Username.
- Email.
- Perfil.
- Empresa vinculada.
- Status ativo.
- Foto de perfil.
- Estado de onboarding.

Impacto:

- Define permissões.
- Define empresa atual.
- Gera rastreabilidade via logs.

### Obra

É o centro do sistema.

Dados operacionais:

- Código único.
- Nome.
- Endereço.
- Tipologia.
- Tipo de obra.
- Área.
- Datas de início e fim prevista.
- Orçamento previsto.
- Receita total ou valor de contrato.
- Percentual de execução.
- Status.
- Fase atual.
- Observação para cliente.
- Foto de capa.
- Próxima etapa do portal.
- Token público do portal.

Impacto:

- Concentra custos, equipe, medições, fotos, importações e alertas.
- Alimenta dashboard, orçamento, portal e relatórios.

### Custo

Representa um gasto lançado contra uma obra.

Dados operacionais:

- Obra.
- Descrição.
- Categoria.
- Fornecedor.
- Data de lançamento.
- Valor total.
- Quantidade.
- Valor unitário.
- Status de entrega.
- Datas de entrega.
- Nota fiscal.
- Observação.

Impacto:

- Afeta custo realizado.
- Afeta saldo, margem e alertas financeiros.
- Alimenta ranking por categoria.
- Material funciona como base operacional de compras.

### Fornecedor

Representa uma empresa ou pessoa fornecedora de material, serviço ou apoio.

Dados operacionais:

- Código.
- Nome.
- Categoria.
- Contato.
- Documento.
- Prazo médio.
- Nota de qualidade.
- Nota de preço.
- Nota de prazo.
- Observação.

Impacto:

- Ajuda a comparar fornecedores.
- Alimenta ranking de fornecedores no dashboard.
- Pode ser informado em custos, mas não há vínculo obrigatório forte entre custo e cadastro de fornecedor.

### Equipe

Representa profissionais alocados em obras.

Dados operacionais:

- Obra.
- Nome.
- Função.
- Contrato.
- Data de início.
- Valor contratado.
- Valor pago.
- Status de pagamento.
- Observação.

Impacto:

- Permite acompanhar mão de obra por obra.
- Pode gerar alertas de pagamento pendente.
- Contribui para controle operacional, mas não soma automaticamente no custo se não for lançado também como custo.

### Medição

Representa avanço físico e/ou financeiro medido em uma obra.

Dados operacionais:

- Obra.
- Mês.
- Nome da medição.
- Etapa.
- Percentual da medição.
- Percentual acumulado.
- Valor realizado.
- Data da medição.
- Observação.

Impacto:

- Alimenta dashboard.
- Alimenta gráficos e evolução da obra.
- Pode indicar avanço físico e financeiro, mas não altera automaticamente o percentual de execução da obra.

### Importação

Representa a entrada de dados por planilha.

Dados operacionais:

- Arquivo importado.
- Obra vinculada.
- Observação.
- Data da importação.

Impacto:

- Pode criar ou atualizar obra.
- Pode atualizar orçamento, receita e progresso.
- Pode substituir categorias importadas e medições importadas da obra.

### Orçamento Importado

Representa custos previstos por categoria vindos da planilha.

Dados operacionais:

- Obra.
- Categoria.
- Valor total.
- Origem.

Impacto:

- Serve para comparação entre orçamento planejado e custos lançados.
- Alimenta análise de diferença por categoria no dashboard.

### Foto da Obra

Representa registros visuais que podem aparecer no portal.

Dados operacionais:

- Obra.
- Caminho da imagem.
- Título.
- Fase.
- Data de registro.

Impacto:

- Alimenta galeria do portal.
- Pode virar capa do portal.
- Ajuda a comunicação com cliente.

### Log

Representa histórico de eventos operacionais.

Dados operacionais:

- Empresa.
- Usuário.
- Ação.
- Entidade.
- Entidade relacionada.
- Descrição.
- Data/hora.

Impacto:

- Alimenta histórico interno.
- Alimenta atualizações publicadas no portal quando a ação é de atualização de canteiro.
- Dá rastreabilidade para criação, edição, exclusão, login e eventos relevantes.

## 5. Módulo Visão Geral

Objetivo: ser a central diária do gestor.

Função operacional:

- Mostrar situação consolidada das obras.
- Destacar custos, receita, saldo, orçamento usado, alertas, movimentações recentes e próximos passos.
- Ajudar o usuário a decidir onde atuar primeiro.

Usuários envolvidos:

- Admin, gestor e leitura.

Fluxo operacional:

1. Usuário acessa a visão geral.
2. Sistema carrega obras, custos, fornecedores, medições e orçamento importado da empresa atual.
3. Usuário pode filtrar por obra, categoria, status, tipo de obra e período.
4. Os KPIs e listas são recalculados conforme os filtros.
5. Usuário pode ir para detalhes da obra, alertas, exportação ou módulos relacionados.

Dados manipulados:

- Obras.
- Custos.
- Medições.
- Fornecedores.
- Orçamento importado.
- Alertas.

KPIs principais:

- Receita prevista.
- Custo total realizado.
- Saldo disponível.
- Percentual de custo sobre receita.
- Obras atrasadas.
- Obras em andamento.
- Obras concluídas.
- Total de medições.
- Total importado do orçamento.
- Alertas ativos.
- Execução média das obras.
- Custo por categoria.
- Margem por obra.

Regras de negócio:

- Receita total é a soma da receita cadastrada nas obras filtradas.
- Custo total é a soma dos custos lançados nas obras filtradas.
- Saldo ou margem é receita total menos custo total.
- Percentual de custo é custo total dividido pela receita total quando há receita.
- Execução média é a média do percentual de execução das obras filtradas.
- Obra atrasada é contabilizada pelo status `atrasada`.
- Obra ativa inclui status de andamento e, em algumas leituras, planejamento.
- Obra concluída inclui `concluida` e `vendida`.
- Orçamento importado é comparado com custo lançado por categoria.

Comportamentos automáticos:

- Atualização parcial dos dados por requisições assíncronas.
- Recalculo visual ao aplicar ou limpar filtros.
- Estado vazio quando não há obras nem custos.
- Gráfico financeiro aparece quando existe base financeira.
- Alertas aparecem agrupados por severidade.

Dependências:

- Depende de obras como base.
- Depende de custos para leitura financeira.
- Depende de medições para evolução.
- Depende de alertas para priorização.
- Depende de portal/fotos para indicação de comunicação com cliente.

Pontos de atenção:

- O cartão "Orçamento usado" usa, na prática, a receita como base de percentual em vários pontos da tela. Conceitualmente, orçamento usado deveria comparar custo realizado contra orçamento previsto. Isso pode confundir o gestor.
- A visão geral mistura "receita", "orçamento" e "saldo" em alguns textos. Como produto financeiro, precisa separar com clareza: receita/contrato, custo previsto/orçamento, custo realizado e resultado.

## 6. Módulo Obras

Objetivo: cadastrar e acompanhar cada obra da empresa.

Função operacional:

- Servir como registro central do empreendimento.
- Mostrar situação, financeiro, execução, status e acesso ao portal.
- Permitir abertura da página detalhada da obra.

Usuários envolvidos:

- Admin e gestor podem criar/editar/excluir.
- Leitura pode visualizar.

Fluxo operacional:

1. Usuário acessa a lista de obras.
2. Pode buscar por texto ou filtrar por status.
3. Gestor pode criar uma nova obra.
4. Cada obra pode ser aberta em detalhes.
5. Gestor pode editar ou excluir.
6. A obra pode ter portal gerado, canteiro atualizado, fotos adicionadas e medições/custos vinculados.

Dados manipulados:

- Código da obra.
- Nome.
- Tipologia.
- Tipo de obra.
- Área.
- Datas.
- Status.
- Orçamento previsto.
- Receita ou valor de contrato.
- Progresso.
- Fase.
- Portal.

Tipos de obra:

- Por contrato / reforma / serviço.
- Para venda.

Estados possíveis:

- Planejamento.
- Em andamento.
- Atrasada.
- Concluída.
- Vendida.

Regras de negócio:

- Toda obra tem código único.
- Se o código não for informado na criação, o sistema sugere o próximo no padrão OBR-001, OBR-002 e assim por diante.
- Nome, tipologia e status são obrigatórios no cadastro principal.
- A obra nasce com 0% de conclusão.
- Área, orçamento e receita não podem ser negativos.
- Percentual de execução deve ficar entre 0 e 100.
- O tipo inválido volta para "contrato".
- Uma obra pertence a uma empresa.
- O resumo financeiro da obra é calculado somando custos lançados.
- Saldo disponível é receita total menos custo realizado.
- Ao excluir obra, o sistema remove seus custos, medições, equipe, compras, orçamento importado e fotos.

Impacto no sistema:

- Criar obra libera controle financeiro, medições, equipe, portal e alertas.
- Editar obra altera dashboards e filtros.
- Alterar empresa da obra exige sincronizar os registros filhos.
- Excluir obra remove histórico operacional vinculado.

Pontos de atenção:

- Excluir obra é uma ação de alto impacto porque apaga diversos registros relacionados.
- O sistema diferencia "detalhes da obra" e "central do portal da obra"; isso pode ser útil, mas deve ser claro para o usuário.
- A obra tem campos internos e campos publicados ao cliente. Essa fronteira é essencial para manter segurança operacional.

## 7. Detalhes da Obra e Central do Canteiro

Objetivo: concentrar a leitura profunda de uma obra e permitir atualizar o que o cliente verá.

Função operacional:

- Mostrar custos, medições, equipe, compras, orçamento importado e fotos da obra.
- Permitir atualizar fase, progresso, próxima etapa e mensagem para cliente.
- Controlar fotos e capa do portal.

Usuários envolvidos:

- Admin e gestor operam.
- Leitura consulta.

Fluxo operacional:

1. Usuário abre uma obra.
2. Visualiza resumo financeiro e operacional.
3. Gestor atualiza fase, progresso e mensagem.
4. O sistema registra uma atualização de canteiro no histórico.
5. Essa atualização pode aparecer no portal público se estiver dentro do padrão de publicação.
6. Gestor pode adicionar fotos e definir capa.

Dados manipulados:

- Fase atual.
- Progresso percentual.
- Observação do responsável.
- Próxima etapa do portal.
- Fotos.
- Capa.
- Histórico de atualizações.

Regras de negócio:

- Progresso deve estar entre 0 e 100.
- Atualizações do canteiro geram logs específicos para o cliente.
- Fotos aceitas são imagens em formatos comuns.
- Foto marcada como capa passa a ser a imagem principal do portal.
- Ao excluir a foto que era capa, a capa da obra é limpa.

Impacto:

- Atualiza dashboard.
- Atualiza portal.
- Gera rastreabilidade.
- Melhora comunicação com cliente.

## 8. Módulo Custos

Objetivo: controlar os gastos reais das obras.

Função operacional:

- Registrar custos por obra, categoria, fornecedor, data e valor.
- Agrupar lançamentos por obra.
- Permitir análise por categoria.
- Alimentar dashboard financeiro e alertas.

Usuários envolvidos:

- Admin e gestor podem lançar/editar/excluir.
- Leitura pode visualizar.

Fluxo operacional:

1. Usuário acessa custos.
2. Pode filtrar por obra, categoria e período.
3. Gestor cria lançamento informando obra, categoria e descrição.
4. Pode informar valor total direto ou quantidade e valor unitário.
5. Sistema calcula o valor total quando quantidade e valor unitário são informados sem valor total.
6. O custo aparece agrupado na obra e alimenta KPIs.

Categorias válidas:

- Material.
- Mão de Obra.
- Equipamento.
- Projeto/Engenharia.
- Taxas e Impostos.
- Outros.

Estados de entrega:

- Aguardando.
- Entregue no prazo.
- Entregue com atraso.
- Cancelado.

Regras de negócio:

- Obra, descrição e categoria são obrigatórias.
- Categoria precisa estar na lista válida.
- Valor total não pode ser negativo.
- Quantidade não pode ser negativa.
- Valor unitário não pode ser negativo.
- O custo precisa ter valor total maior que zero.
- Custos pertencem à empresa da obra.
- Custos são filtrados pela empresa do usuário.
- Custos de material funcionam como representação prática de compras.

Impacto:

- Afeta custo realizado da obra.
- Afeta saldo e margem.
- Pode gerar alerta por custo acima do previsto ou acima da receita.
- Alimenta dashboards, exportações e detalhes da obra.

Pontos de atenção:

- O cadastro de fornecedor em custos é textual, não obrigatoriamente ligado ao módulo Fornecedores.
- O módulo Compras existe como entrada conceitual, mas na prática redireciona para Custos com foco em Material.
- Se equipe tem valor contratado/pago, isso não vira custo automaticamente; o gestor precisa lançar custo de mão de obra se quiser refletir no financeiro.

## 9. Módulo Fornecedores

Objetivo: manter um cadastro de fornecedores e avaliar qualidade, preço e prazo.

Função operacional:

- Registrar fornecedores usados pela construtora.
- Guardar contato, categoria e documento.
- Atribuir notas para avaliação.
- Alimentar ranking no dashboard.

Usuários envolvidos:

- Admin e gestor podem criar/editar/excluir.
- Leitura pode consultar.

Fluxo operacional:

1. Gestor cadastra fornecedor com código, nome e categoria.
2. Pode informar contato, documento, prazo médio e observações.
3. Pode atribuir notas de qualidade, preço e prazo.
4. Dashboard calcula média simples das notas e mostra ranking.

Dados manipulados:

- Código.
- Nome.
- Categoria.
- Contato.
- Documento.
- Prazo médio.
- Notas.
- Observação.

Regras de negócio:

- Código, nome e categoria são obrigatórios.
- Código deve ser único.
- Prazo médio não pode ser negativo.
- Notas devem ficar entre 0 e 10.
- Fornecedor pertence à empresa atual.

Impacto:

- Apoia decisão de compra e contratação.
- Ajuda a comparar fornecedores recorrentes.

Pontos de atenção:

- Como custos usam fornecedor em texto livre, o sistema ainda não garante consistência entre custo e cadastro de fornecedor.

## 10. Módulo Equipe

Objetivo: controlar profissionais vinculados às obras.

Função operacional:

- Registrar quem está trabalhando em cada obra.
- Registrar função e valores de contratação/pagamento.
- Monitorar pagamentos pendentes.

Usuários envolvidos:

- Admin e gestor podem criar/editar/excluir.
- Leitura pode visualizar.

Fluxo operacional:

1. Gestor escolhe uma obra.
2. Cadastra profissional e função.
3. Pode informar valor contratado e valor pago.
4. Sistema lista equipe com obra de origem.
5. Alertas podem ser gerados quando há pagamento pendente.

Dados manipulados:

- Obra.
- Nome.
- Função.
- Valor contratado.
- Valor pago.
- Status de pagamento.

Regras de negócio:

- Obra e nome são obrigatórios.
- Valor contratado não pode ser negativo.
- Valor pago não pode ser negativo.
- Profissional pertence à empresa da obra.
- Usuários sem permissão de gestor não podem alterar equipe.

Impacto:

- Permite visão de mão de obra por obra.
- Pode gerar alerta operacional.

Pontos de atenção:

- Edição atual da equipe é mais limitada que o cadastro, pois foca em nome e função.
- Valores de equipe não entram automaticamente em custos.

## 11. Módulo Medições

Objetivo: registrar avanço físico e financeiro medido por etapa.

Função operacional:

- Controlar execução por medição.
- Acompanhar percentual do período e acumulado.
- Registrar valor realizado.
- Alimentar visão da obra e dashboard.

Usuários envolvidos:

- Admin e gestor podem criar/editar/excluir.
- Leitura pode visualizar.

Fluxo operacional:

1. Gestor escolhe a obra.
2. Informa nome da medição, etapa, percentual, acumulado, valor e data.
3. Sistema valida percentuais e valores.
4. Medição aparece na lista geral, nos detalhes da obra e no dashboard.

Dados manipulados:

- Obra.
- Mês.
- Nome da medição.
- Etapa.
- Percentual.
- Percentual acumulado.
- Valor realizado.
- Data.
- Observação.

Regras de negócio:

- Obra, nome da medição e etapa são obrigatórios.
- Percentuais devem ficar entre 0 e 100.
- Valor realizado não pode ser negativo.
- Medição pertence à empresa da obra.
- Medições podem ser criadas manualmente ou importadas por planilha.

Impacto:

- Ajuda a entender evolução física.
- Alimenta gráficos da obra.
- Contribui para atividade recente no dashboard.

Ponto de atenção:

- Medição não atualiza automaticamente o percentual de execução da obra. Isso permite flexibilidade, mas pode gerar divergência entre medição acumulada e execução exibida.

## 12. Módulo Alertas

Objetivo: transformar dados operacionais em prioridade de ação.

Função operacional:

- Detectar riscos automaticamente.
- Separar alertas por criticidade.
- Direcionar o usuário para obra, custos, cronograma ou equipe.

Usuários envolvidos:

- Admin, gestor e leitura visualizam.
- Gestor executa ações corretivas.

Fluxo operacional:

1. Sistema calcula alertas com base nas obras, custos e equipe.
2. Alertas aparecem no sino global, no dashboard e na página de alertas.
3. Usuário filtra por todos, críticos, atenção ou informativos.
4. Ao clicar, usuário é levado para obra ou equipe.

Regras de geração:

- Custo total maior que receita prevista gera alerta crítico de resultado negativo.
- Custo total maior que 105% do custo previsto gera alerta de atenção.
- Custo total igual ou superior a 90% da receita prevista gera alerta de atenção.
- Obra com status atrasada gera alerta crítico.
- Obra em andamento com 0% de execução gera alerta de atenção.
- Obra com prazo final em até 7 dias gera alerta de atenção.
- Obra com prazo final ultrapassado gera alerta crítico.
- Profissional com pagamento pendente gera alerta de atenção.

Estados:

- Crítico.
- Atenção.
- Informativo.

Impacto:

- Priorização visual no dashboard.
- Painel específico de alertas.
- Sino global no topo do sistema.

Regras implícitas:

- Alertas não são registros persistidos; são calculados a partir do estado atual dos dados.
- Resolver um alerta significa alterar o dado que o gerou.
- A mesma condição não deve aparecer duplicada para a mesma obra/mensagem.

Pontos de atenção:

- Como alertas são calculados em tempo real, filtros e escopo de empresa alteram o que aparece.
- Alguns textos ainda indicam problemas de encoding em fontes internas, o que afeta percepção de qualidade.
- Há mistura entre alerta operacional real e mensagem informativa. Produto pode evoluir para separar "risco" de "recomendação".

## 13. Módulo Portal do Cliente

Objetivo: permitir que o cliente acompanhe a obra sem acessar o sistema interno.

Função operacional:

- Publicar uma visão segura e simplificada da obra.
- Mostrar progresso, fase, fotos, mensagem e linha do tempo.
- Evitar exposição de dados financeiros e internos.

Usuários envolvidos:

- Gestor gera e atualiza.
- Cliente acessa por link.
- Leitura interna pode visualizar.

Fluxo operacional:

1. Gestor gera link público para uma obra.
2. Sistema cria token público.
3. Cliente recebe link.
4. Cliente acessa portal sem login.
5. Gestor atualiza fase, progresso, próxima etapa, observação e fotos.
6. Portal reflete as informações publicadas.
7. Gestor pode revogar o link.

Dados exibidos ao cliente:

- Nome da obra.
- Endereço quando houver.
- Tipologia.
- Área.
- Data de início.
- Data final prevista.
- Progresso.
- Status.
- Fase atual.
- Próxima etapa.
- Mensagem do responsável.
- Fotos selecionadas.
- Histórico de atualizações publicadas.
- Linha do tempo resumida.

Dados não exibidos:

- Custos.
- Orçamento.
- Receita.
- Margem.
- Fornecedores.
- Equipe.
- Notas fiscais.
- Usuários internos.
- Logs administrativos gerais.

Regras de negócio:

- Portal só abre com token válido.
- Token precisa estar ativo e não revogado.
- Token pode ter expiração configurável.
- Se token expirar ou for revogado, o portal retorna indisponível.
- Atualizações exibidas são apenas as registradas como atualização para o cliente.
- Fotos exibidas pertencem à obra e à empresa da obra.
- Foto de capa tem prioridade; se não houver capa, usa foto mais recente.

Impacto:

- Reduz necessidade de mensagens manuais para cliente.
- Dá percepção de transparência sem expor operação interna.
- Ajuda construtor a profissionalizar acompanhamento.

Pontos de atenção:

- O portal depende da disciplina do gestor em atualizar fase, mensagem e fotos.
- Sem atualização frequente, o portal pode transmitir abandono mesmo que a obra esteja avançando.

## 14. Módulo Orçamento e Importação

Objetivo: trazer dados planejados de planilhas e permitir comparação com custo real.

Função operacional:

- Importar planilha de obra.
- Criar ou atualizar obra a partir da planilha.
- Importar orçamento por categoria.
- Importar medições.
- Exibir resumo do orçamento importado.

Usuários envolvidos:

- Admin e gestor importam.
- Leitura visualiza.

Fluxo operacional:

1. Gestor acessa Importação.
2. Envia planilha e informa código e nome da obra.
3. Sistema localiza obra existente ou cria nova.
4. Sistema registra importação.
5. Se houver aba administrativa, atualiza orçamento, receita e progresso.
6. Sistema extrai categorias de custo planejado.
7. Sistema substitui categorias importadas anteriores da obra.
8. Se houver aba de medições, substitui medições importadas anteriores.
9. Tela Orçamento mostra categorias importadas e resumo das obras.

Dados manipulados:

- Arquivo.
- Obra.
- Orçamento.
- Receita.
- Progresso.
- Categorias importadas.
- Medições importadas.

Regras de negócio:

- Arquivo precisa ser planilha aceita.
- Código e nome da obra são obrigatórios.
- Se a obra já existe, a importação atualiza dados da obra.
- Se não existe, a importação cria uma obra em planejamento.
- Categorias importadas por planilha substituem o orçamento importado anterior da obra.
- Medições importadas por planilha substituem medições anteriores da obra.
- Percentuais em decimal podem ser convertidos para percentual.

Impacto:

- Acelera implantação inicial.
- Permite comparar planejado versus realizado.
- Pode alterar dados centrais da obra.

Pontos de atenção:

- Importação substitui dados importados/medições da obra; isso deve estar claro para o usuário antes de importar.
- O mapeamento da planilha é rígido. Mudanças no modelo de planilha podem quebrar a leitura operacional.
- Algumas categorias importadas não coincidem exatamente com as categorias de custo manual, o que pode dificultar comparação direta.

## 15. Módulo Usuários e Conta

Objetivo: controlar acesso interno e segurança operacional.

Função operacional:

- Login.
- Logout.
- Perfil.
- Alteração de senha.
- Foto de perfil.
- Esqueci senha.
- Gestão de usuários internos.

Usuários envolvidos:

- Todos acessam perfil.
- Admin gerencia usuários.

Fluxo de login:

1. Usuário informa username e senha.
2. Sistema valida credenciais.
3. Conta inativa é bloqueada.
4. Perfil cliente é impedido de acessar o sistema interno.
5. Sessão recebe usuário, perfil, empresa e foto.
6. Usuário entra no dashboard ou onboarding.

Regras de segurança:

- Existe limite de tentativas de login.
- Após muitas tentativas, usuário/IP fica bloqueado temporariamente.
- Senha de redefinição por email usa token com expiração.
- Links de redefinição são invalidáveis e de uso único.
- Nova senha pública precisa ter pelo menos 8 caracteres.
- Senha criada ou resetada por admin usa regra mínima de 6 caracteres.
- Toda requisição interna de alteração exige token de proteção contra envio indevido.

Fluxo de usuários:

1. Admin acessa usuários.
2. Cria usuário com nome, username, email, empresa, perfil, senha e status.
3. Se email inativo já existir, pode reativar cadastro.
4. Gestor novo pode ficar com onboarding pendente.
5. Admin pode editar, ativar/desativar, excluir, resetar senha e alterar foto.

Regras de negócio:

- Username é único.
- Email ativo é único.
- Perfil inválido volta para leitura.
- Usuário não pode desativar ou excluir a si mesmo.
- Admin global pode escolher ou criar empresa.
- Admin de empresa não pode gerenciar fora da própria empresa.
- Perfil gestor inicia onboarding pendente quando criado.

Impacto:

- Define acesso aos dados.
- Define responsabilidades.
- Mantém rastreabilidade por logs.

## 16. Onboarding

Objetivo: fazer o novo gestor chegar rapidamente a uma operação mínima funcional.

Fluxo:

1. Criar primeira obra.
2. Adicionar primeiro custo ou pular.
3. Gerar link do portal para cliente.
4. Concluir onboarding.

Regras de negócio:

- Apenas gestor com onboarding pendente passa por esse fluxo.
- Se tentar acessar outras telas antes de concluir, é redirecionado ao onboarding.
- A primeira obra recebe código automático.
- A obra nasce com 0% de progresso.
- O custo inicial é opcional.
- O portal é gerado automaticamente no passo final.
- Ao concluir, usuário deixa de ser redirecionado.

Impacto:

- Reduz tela vazia inicial.
- Ensina fluxo principal do produto.
- Cria a primeira base operacional.

## 17. Compras

Objetivo conceitual: acompanhar compras de materiais.

Funcionamento atual:

- O módulo Compras redireciona para Custos com categoria Material.
- Criar, editar e excluir compras não possui fluxo próprio ativo.

Regra operacional implícita:

- Compra é tratada como custo de material.
- Status de entrega, quantidade, valor unitário, datas de entrega e nota fiscal ficam no lançamento de custo.

Ponto de atenção:

- Como produto, "Compras" é um módulo conceitual importante para construção civil, mas atualmente está incorporado em Custos. Se o negócio exigir controle de pedidos, aprovação, recebimento e fornecedor formal, este módulo precisará ganhar fluxo próprio.

## 18. Logs e Auditoria Operacional

Objetivo: registrar eventos relevantes.

Eventos registrados:

- Login.
- Criação, edição e exclusão de obras.
- Criação, edição e exclusão de custos.
- Criação, edição e exclusão de fornecedores.
- Criação, edição e exclusão de medições.
- Geração e revogação de portal.
- Atualizações de canteiro.
- Fotos da obra.
- Alterações de senha e usuários.
- Importações.

Regras:

- Log tenta associar empresa pelo registro envolvido.
- Se não encontrar empresa pela entidade, usa empresa da sessão.
- Logs são visíveis conforme escopo de empresa.

Impacto:

- Aumenta rastreabilidade.
- Alimenta histórico do portal quando a ação é atualização de canteiro.
- Ajuda investigação de alterações.

Ponto de atenção:

- Logs são genéricos e textuais. Para auditoria mais forte, seria útil padronizar tipos e separar logs internos de publicações ao cliente.

## 19. Exportações

Objetivo: permitir análise externa em planilha.

Telas com exportação:

- Dashboard.
- Obras.
- Custos.
- Fornecedores.
- Equipe.
- Medições.
- Compras redireciona para exportação de custos/material.

Regras:

- Usuários com permissão de visualização podem exportar.
- Exportação respeita filtros e empresa.
- Arquivos são gerados em formato Excel.

Impacto:

- Permite prestação de contas externa.
- Ajuda backup operacional.
- Facilita análise fora do sistema.

## 20. Fluxo Operacional Completo

Fluxo recomendado de uso:

1. Admin cria empresa e usuários.
2. Gestor acessa sistema.
3. Gestor conclui onboarding ou cria obra manualmente.
4. Gestor informa dados principais da obra: tipo, tipologia, área, datas, orçamento, receita e status.
5. Gestor lança custos conforme a obra avança.
6. Gestor registra medições por etapa.
7. Gestor cadastra equipe e fornecedores quando necessário.
8. Gestor atualiza canteiro: fase, progresso, próxima etapa e mensagem.
9. Gestor adiciona fotos e define capa.
10. Gestor gera portal e compartilha com cliente.
11. Dashboard monitora custo, saldo, execução, alertas e atividade.
12. Alertas direcionam o gestor para correções.
13. Leitura consulta operação sem alterar.
14. Admin acompanha usuários, acessos e manutenção da operação.

## 21. Fluxo Financeiro

Conceitos financeiros do produto:

- Receita total: valor previsto de contrato ou venda.
- Orçamento previsto: custo-base esperado para executar a obra.
- Custo realizado: soma dos custos lançados.
- Saldo/margem atual: receita total menos custo realizado.
- Lucro previsto: receita total menos orçamento previsto.
- Orçamento importado: planejamento por categoria vindo de planilha.
- Diferença por categoria: custo lançado menos valor importado daquela categoria.

Regras financeiras:

- Custo realizado nasce dos lançamentos manuais de custos.
- Custo importado por categoria serve como referência, não como custo realizado.
- Medição com valor realizado não vira custo automaticamente.
- Equipe com valor contratado/pago não vira custo automaticamente.
- Fornecedor não cria custo automaticamente.
- Resultado negativo ocorre quando custo realizado passa a receita prevista.
- Custo acima do previsto ocorre quando custo realizado passa o orçamento previsto com tolerância.

Pontos de atenção:

- Produto precisa reforçar diferença entre orçamento de custo e receita de contrato.
- Para construtor, "orçamento usado" deve ser preferencialmente custo realizado sobre orçamento previsto.
- "Saldo disponível" deve explicar quando é sobra e quando é estouro.

## 22. Relação Entre Módulos

Obras é o módulo central.

- Custos dependem de obras.
- Medições dependem de obras.
- Equipe depende de obras.
- Fotos dependem de obras.
- Portal depende de obras, fotos e logs de atualização.
- Orçamento importado depende de obras.
- Dashboard depende de obras, custos, medições, fornecedores e orçamento importado.
- Alertas dependem de obras, custos e equipe.
- Logs dependem de ações realizadas nos módulos.
- Usuários dependem de empresa.
- Empresas delimitam todos os dados internos.

Relação operacional:

- Criar obra abre espaço para operação.
- Lançar custos muda financeiro.
- Registrar medições muda leitura de evolução.
- Atualizar canteiro muda comunicação com cliente.
- Importar planilha muda planejamento.
- Alertas apontam onde os dados indicam risco.

## 23. Mapa de Telas e Navegação

### Login

Finalidade: entrada segura no sistema interno.

Comportamento esperado:

- Usuário interno informa credenciais.
- Conta inativa não entra.
- Perfil cliente não entra no sistema interno.
- Muitas tentativas incorretas bloqueiam temporariamente o acesso.
- Usuário autenticado vai para Visão Geral ou Onboarding, conforme seu estado.

### Esqueci Senha e Redefinição

Finalidade: recuperação de acesso sem intervenção manual.

Comportamento esperado:

- Usuário informa email.
- Se o email existir e estiver ativo, recebe link de redefinição.
- O link expira.
- Senha nova exige confirmação.

### Visão Geral

Finalidade: painel operacional diário.

Comportamento esperado:

- Exibe KPIs, alertas, financeiro, próximas etapas e tabela de situação.
- Permite filtrar sem sair da tela.
- Permite navegar para detalhes da obra e alertas.
- Oferece exportação.

### Obras

Finalidade: cadastro e leitura operacional das obras.

Comportamento esperado:

- Lista obras com status, progresso, valores e ações.
- Permite criar obra para gestores.
- Permite abrir detalhes.
- Permite editar e excluir para gestores.
- Permite filtrar e buscar.

### Detalhes da Obra

Finalidade: leitura profunda de uma obra.

Comportamento esperado:

- Mostra custos, medições, equipe, compras/material, orçamento importado e fotos.
- Permite acessar o painel de publicação do portal.
- Permite visualizar gráficos e resumo financeiro.

### Central do Portal da Obra

Finalidade: preparar e controlar a visão do cliente.

Comportamento esperado:

- Gestor atualiza fase, progresso, próxima etapa e mensagem.
- Gestor adiciona fotos e define capa.
- Gestor gera, copia, abre ou revoga link do portal.
- Usuário de leitura vê estado, mas não altera.

### Custos

Finalidade: central financeira operacional.

Comportamento esperado:

- Agrupa custos por obra.
- Exibe total lançado, quantidade de lançamentos e tabela detalhada.
- Permite filtro por obra, categoria e período.
- Permite lançar, editar e excluir custos para gestores.
- Permite exportar.

### Fornecedores

Finalidade: cadastro e avaliação de fornecedores.

Comportamento esperado:

- Lista fornecedores.
- Permite criar, editar e excluir para gestores.
- Permite exportar.
- Alimenta ranking de fornecedores.

### Equipe

Finalidade: controle de profissionais por obra.

Comportamento esperado:

- Lista membros vinculados às obras.
- Permite criar, editar e excluir para gestores.
- Permite exportar.
- Pode alimentar alertas de pagamento pendente.

### Medições

Finalidade: controle de avanço físico/financeiro.

Comportamento esperado:

- Lista medições por obra.
- Permite cadastrar medição com etapa, percentual e valor.
- Permite editar e excluir para gestores.
- Permite exportar.

### Alertas

Finalidade: central de monitoramento de riscos.

Comportamento esperado:

- Exibe alertas calculados automaticamente.
- Permite filtrar por severidade.
- Cada alerta direciona para a área mais provável de resolução.

### Orçamento

Finalidade: leitura de orçamento importado e visão planejada.

Comportamento esperado:

- Mostra categorias importadas por obra.
- Mostra resumo das obras importadas.
- Ajuda a comparar planejamento e execução.

### Importação

Finalidade: entrada de dados via planilha.

Comportamento esperado:

- Gestor envia arquivo e informa obra.
- Sistema cria ou atualiza a obra.
- Sistema registra importação.
- Sistema alimenta orçamento importado e medições.

### Usuários

Finalidade: administração de acesso interno.

Comportamento esperado:

- Disponível para admin.
- Lista usuários internos.
- Permite criar, editar, ativar/desativar, excluir e resetar senha.
- Admin global pode trabalhar com empresas.

### Perfil

Finalidade: configurações da própria conta.

Comportamento esperado:

- Usuário altera senha.
- Usuário atualiza foto.
- Admin pode ter visão adicional de usuários conforme escopo.

### Logs

Finalidade: histórico de eventos operacionais.

Comportamento esperado:

- Exibe ações registradas no sistema.
- Respeita empresa do usuário.
- Ajuda a rastrear alterações.

### Portal Público

Finalidade: acompanhamento externo da obra pelo cliente.

Comportamento esperado:

- Acesso por link com token.
- Não exige login.
- Mostra apenas dados publicados e seguros.
- Bloqueia acesso se token for inválido, expirado ou revogado.

## 24. Matriz de Permissões

| Área | Admin | Gestor | Leitura | Cliente |
| --- | --- | --- | --- | --- |
| Login interno | Sim | Sim | Sim | Não |
| Dashboard | Visualiza | Visualiza | Visualiza | Não |
| Obras | Cria, edita, exclui e visualiza | Cria, edita, exclui e visualiza | Visualiza | Não |
| Custos | Cria, edita, exclui e visualiza | Cria, edita, exclui e visualiza | Visualiza | Não |
| Fornecedores | Cria, edita, exclui e visualiza | Cria, edita, exclui e visualiza | Visualiza | Não |
| Equipe | Cria, edita, exclui e visualiza | Cria, edita, exclui e visualiza | Visualiza | Não |
| Medições | Cria, edita, exclui e visualiza | Cria, edita, exclui e visualiza | Visualiza | Não |
| Importação | Importa e visualiza | Importa e visualiza | Visualiza | Não |
| Orçamento | Visualiza | Visualiza | Visualiza | Não |
| Alertas | Visualiza | Visualiza | Visualiza | Não |
| Logs | Visualiza | Visualiza | Visualiza | Não |
| Portal público | Gera, revoga e visualiza | Gera, revoga e visualiza | Visualiza estado interno | Acessa link público |
| Usuários | Gerencia | Não | Não | Não |
| Perfil próprio | Edita | Edita | Edita | Não |
| Exportação | Sim | Sim | Sim | Não |

Observações:

- Admin global tem alcance sobre empresas; admin vinculado a empresa fica restrito à própria empresa.
- Gestor possui poder operacional, mas não administrativo sobre usuários.
- Leitura tem acesso informativo e não deve alterar dados.
- Cliente só acessa o portal público e nunca vê dados internos.

## 25. Regras Críticas do Sistema

- Cliente nunca acessa sistema interno.
- Usuário inativo não acessa sistema.
- Usuário sem login não acessa rotas internas.
- Gestor e admin alteram dados; leitura consulta.
- Admin gerencia usuários.
- Dados são segregados por empresa.
- Obra é obrigatória para custos, equipe e medições.
- Valores financeiros não podem ser negativos.
- Percentuais devem ficar entre 0 e 100.
- Código de obra é único.
- Código de fornecedor é único.
- Categoria de custo deve estar na lista válida.
- Portal só abre com token válido, ativo e não expirado.
- Portal não mostra dados financeiros internos.
- Excluir obra remove registros operacionais vinculados.
- Importar planilha pode substituir orçamento importado e medições da obra.
- Alertas são consequência dos dados atuais, não tarefas independentes.

## 26. Regras Implícitas

- A obra em andamento com 0% de execução é considerada problema operacional.
- Atraso é determinado tanto por status manual quanto por prazo ultrapassado.
- Custo acima da receita é mais grave que custo acima do orçamento.
- Custo acima de 90% da receita exige atenção.
- Custo acima de 105% do orçamento previsto exige atenção.
- Portal desatualizado é risco de comunicação, mesmo quando a obra está avançando.
- O gestor é responsável por manter o portal útil para o cliente.
- A planilha importada é tratada como fonte de planejamento.
- Custos manuais são tratados como realidade executada.
- Medições são evidência de avanço, mas não governam automaticamente a execução da obra.

## 27. Gargalos e Riscos de Produto

### Risco financeiro conceitual

Há mistura de termos entre receita, orçamento, custo previsto e saldo. Isso pode levar o construtor a interpretar margem como orçamento restante.

Recomendação:

- Separar explicitamente "Receita/Contrato", "Orçamento de custo", "Custo realizado", "Lucro previsto" e "Resultado atual".

### Compras ainda não é módulo completo

Compras está absorvido por custos de material.

Recomendação:

- Evoluir para pedido, fornecedor, previsão de entrega, recebimento, atraso e conversão para custo.

### Fornecedor sem vínculo forte com custo

Fornecedor no custo é texto livre.

Recomendação:

- Permitir selecionar fornecedor cadastrado, mantendo texto livre como fallback.

### Equipe fora do financeiro automático

Equipe tem valores, mas esses valores não entram em custos.

Recomendação:

- Definir se equipe é apenas cadastro operacional ou se deve gerar custo de mão de obra.

### Medições não sincronizam execução

Percentual acumulado da medição não altera automaticamente o progresso da obra.

Recomendação:

- Criar regra opcional: última medição acumulada pode sugerir atualização do progresso.

### Importação substitui dados

Importação pode apagar e recriar medições/categorias importadas.

Recomendação:

- Mostrar confirmação clara antes da importação: "esta planilha substituirá medições importadas anteriores".

### Encoding ainda é risco de qualidade percebida

Foram identificados textos corrompidos em arquivos internos e possivelmente em mensagens.

Recomendação:

- Revisar todos os textos de produto para UTF-8 real, especialmente labels, categorias, alertas e mensagens de erro.

### Logs misturam auditoria e publicação

O mesmo mecanismo registra eventos internos e atualizações publicadas ao cliente.

Recomendação:

- Separar "auditoria interna" de "publicações do portal" para reduzir risco de comunicação indevida.

## 28. Oportunidades de Melhoria de Produto

- Criar uma tela de "Plano x Realizado" por obra com orçamento importado, custos lançados e diferença.
- Transformar alertas em tarefas acompanháveis: aberto, visto, resolvido.
- Criar rotina semanal de atualização do portal.
- Criar indicador "obra sem atualização há X dias".
- Criar indicador "obra sem fotos recentes".
- Criar fluxo real de compras com recebimento e atraso.
- Criar vínculo formal entre custo e fornecedor.
- Criar dashboard financeiro por obra com curva de custo.
- Criar relatório de margem por obra e por tipo de obra.
- Criar permissões mais granulares: financeiro, operacional, portal, usuários.
- Criar status de obra mais orientados à construção: orçamento, contrato fechado, em execução, pausada, atrasada, entregue, vendida.
- Criar regras de aprovação para exclusão de obra e exclusão de custo.
- Criar histórico de alteração por campo para dados críticos.
- Criar bloqueio de exclusão quando houver portal ativo ou custos relevantes.
- Criar indicador de confiabilidade do portal: progresso, foto recente e mensagem recente.

## 29. Conclusão Operacional

O Canteiro já possui a estrutura de um SaaS operacional consistente: obra como centro, custos como realidade financeira, medições como avanço, alertas como inteligência operacional e portal como comunicação controlada com cliente.

A regra de negócio mais importante é a separação entre operação interna e comunicação externa. Internamente, o gestor vê custos, orçamento, equipe, medições e riscos. Externamente, o cliente vê apenas progresso, fotos, fase e mensagem selecionada.

O ponto mais sensível para evolução é o financeiro: o produto deve deixar muito claro o que é receita, o que é orçamento de custo, o que é custo realizado e o que é margem. Essa clareza é essencial para o público-alvo tomar decisões rápidas e confiar nos indicadores.

Como produto, o Canteiro está bem posicionado para ser uma central de acompanhamento de obras. As próximas evoluções deveriam focar em: clareza financeira, compras reais, alertas resolvíveis, vínculo de fornecedor, sincronização opcional de medições com execução e separação mais forte entre auditoria interna e publicações do portal.
