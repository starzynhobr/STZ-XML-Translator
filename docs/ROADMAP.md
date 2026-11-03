# Roadmap — Projetos de tradução

Objetivo: tirar o STZ XML Translator do modelo "um arquivo por vez" e levar para
**projetos de tradução** que guardam tudo, continuam de onde pararam e cobrem um
jogo inteiro (caso de referência: Marvel Avengers Alliance Redux, 76 XMLs em
`MAA Redux_Data/StreamingAssets/XMLs`).

Inspiração: o modelo de projeto do GF UI Editor (`gf-ui-editor/src/gf_ui_editor/project.py`):
cópia de trabalho fora da pasta do jogo, `project.db` em SQLite, histórico de
salvamentos, tela inicial com recentes e "Testar no jogo" (F5).

---

## Estado atual (1.6.0)

- O progresso fica em `checkpoints/<arquivo>_<idioma>_<assinatura>_<hash>.json`,
  com a chave formada por caminho absoluto, idioma e seleção de tags (`core/project.py`, `checkpoint_path`).
- Pontos fortes: já separa o progresso por idioma e por seleção de tags, e restaura sozinho.
- Limitações:
  - O checkpoint depende do **caminho absoluto**. Se o jogo for reinstalado ou movido
    (ex.: uma pasta nova em Downloads a cada build), o progresso "some".
  - Abre um arquivo por vez, sem visão do jogo inteiro.
  - Não existe o conceito de "projeto": não há nome, lista de recentes nem
    um lugar para guardar configuração por jogo.
  - Os presets de tags são globais, não pertencem a um jogo.

---

## Conceito: Projeto

```
Documentos/STZ Translation Projects/<Nome do projeto>/
  project.db          SQLite: metadados, arquivos, entradas, traduções por idioma, histórico
  source/             cópia dos XMLs originais (snapshot da build usada como base)
  exports/<idioma>/   saída pronta para copiar no jogo / compartilhar
  .history/           backups automáticos dos exports anteriores
```

Um projeto =

| Campo | Exemplo |
| --- | --- |
| Nome | MAA Redux |
| Pasta do jogo | `...\MAA Redux_Data\StreamingAssets\XMLs` (pode mudar a qualquer hora) |
| Idioma de origem | en |
| **Idiomas de destino** | pt-BR, tr (vários, cada um com o próprio progresso) |
| Perfil de tags por arquivo | `characters.xml`: traduzir `bio`, `cogBio`, `dispName`; contexto `name` |
| Glossário do projeto | nomes de heróis, S.H.I.E.L.D., HYDRA… |
| Provedor / modelo padrão | Gemini |

### Vários idiomas no mesmo projeto

Esse é o cenário em que alguém fala mais de uma língua e quer contribuir com
pt-BR e turco ao mesmo tempo:

- Os textos originais são guardados **uma vez**. As traduções ficam numa tabela
  `(entrada, idioma) → texto, status`.
- Um seletor de idioma na barra superior troca a camada de tradução sem recarregar nada.
- O glossário pode ter termos globais e termos por idioma.
- O export é feito por idioma: `exports/pt-BR/`, `exports/tr/`.
- É viável: o checkpoint atual já separa o progresso por idioma, então é uma
  evolução direta do modelo que existe hoje.

### Identidade estável das entradas (o ponto central)

Para o progresso sobreviver a reinstalações e builds novas, a chave da entrada
deixa de ser o caminho absoluto e passa a ser
`caminho relativo do arquivo + xpath + hash do texto original`.

- Se o xpath bate e o hash bate, a tradução é reaproveitada sem perguntar.
- Se o xpath bate mas o hash mudou, a entrada vai para "Original alterado":
  a tradução antiga é mostrada para revisão.
- Se o texto é igual mas está em outro xpath, a tradução é sugerida pela memória de tradução.

---

## Fases

### Fase 0 — Progresso que sobrevive à reinstalação (feito)
- [x] Checkpoint identificado pelo nome do arquivo, idioma e seleção de tags,
      sem o caminho absoluto (`checkpoint_path(..., portable=True)`).
- [x] O checkpoint guarda o texto original de cada entrada. Ao carregar, só aplica
      a tradução se o original ainda for igual; o que mudou numa build nova
      continua pendente.
- [x] Checkpoints antigos, presos ao caminho, continuam sendo lidos como fallback.

### Fase 1 — Projeto básico (alto impacto, baixo risco)
- [x] `core/workspace.py`: projeto = nome + pasta de XMLs + idioma de destino +
      campos escolhidos por arquivo, salvo em `projects/<id>.stzproj.json`. As
      traduções continuam nos checkpoints portáteis da Fase 0, então projetos
      com a mesma pasta e idiomas diferentes não se misturam.
- [x] Tela inicial com projetos (progresso, pasta, idioma), **Novo projeto** e
      **Abrir XML avulso** (o modo antigo continua existindo).
- [x] Tela do projeto: todos os XMLs da pasta (até 3 níveis), progresso por
      arquivo, busca, **Continuar** no último arquivo e **Trocar pasta** quando
      o jogo é reinstalado.
- [x] Campos lembrados por arquivo: na segunda vez o arquivo abre direto na tradução.
- [x] Cópia dos originais guardada no projeto (`projects/<id>/originals/`): feita pela
      importação abaixo; com ela, os arquivos abrem sempre do inglês. Base para a Fase 4.

### Fase 1.6 — Importar tradução feita fora do app (feito)
- [x] Quem já traduziu editando os XMLs à mão escolhe uma cópia limpa do jogo
      (qualquer nível da pasta). O app compara arquivo por arquivo, posição por
      posição no XML, com os campos do projeto (ou os sugeridos).
- [x] Prévia com o que foi encontrado por arquivo, arquivos sem cópia limpa e o aviso
      de que tudo entra como "a revisar" (uma cópia de outra build faria textos
      alterados pelos devs parecerem traduzidos).
- [x] Ao confirmar: os originais ficam no projeto, as traduções vão para o banco com a
      origem "Importado", e nada traduzido no app é sobrescrito. A pasta do jogo não
      é alterada.
- [x] Roda em segundo plano com progresso (o MAA inteiro leva ~20 s) e também pelo MCP
      (`import_translation`).
- [x] Escolher o idioma ao criar o projeto e trocar na tela do projeto.

**Viabilidade:** alta. O engine (`engine/session.py`) já centraliza estado e persistência,
e a UI Tauri ganha uma tela nova. O formato SQLite e o padrão de histórico podem
ser copiados quase direto do GF UI Editor.

### Fase 1.5 — Seleção inteligente e perfis de jogo (feito)
- [x] `core/field_analysis.py`: classifica cada campo como texto, nome, ID,
      número, sim/não, caminho, código ou vazio, olhando o nome da tag e uma
      amostra dos valores. Só texto e nome são oferecidos para tradução.
- [x] `core/game_profiles.py`: regras por jogo por cima da análise genérica
      (`(tag, campo) → traduzir | contexto | ignorar`). Perfil do MAA Redux:
      rótulos internos (`villain.name` = "SO32 A.I.M. Bazooka Hard") viram
      contexto, listas resolvidas por texto (`actionLevel.statusEffects`) e
      placeholders (`{AGENT_NAME}`) ficam de fora. Jogos sem perfil usam só a
      análise genérica; um perfil novo não muda o comportamento dos outros.
- [x] Várias tags por arquivo (`Group`): `characters.xml` carrega `villain`,
      `action`, `hero`, `baseVillain`... de uma vez. Uma tag só mantém o mesmo
      nome de checkpoint de antes.
- [x] Tela de seleção nova: tags com texto já marcadas, campos com tipo e
      exemplo, seletor Traduzir/Contexto/Ignorar, campos técnicos ocultos
      (aviso se alguém marcar um para traduzir), prévia com registros que têm texto.
- Resultado no MAA: 103.232 textos em 71 dos 76 XMLs, sem IDs nem caminhos.

### Fase 2 — Jogo inteiro (feito)
- [x] **Traduzir projeto inteiro**: uma fila que passa por todos os XMLs do projeto,
      sem abrir arquivo por arquivo. Arquivos nunca abertos usam os campos sugeridos
      (e passam a lembrá-los). Progresso por arquivo, cancelamento a qualquer momento.
- [x] Para numa cota esgotada ou chave inválida; rodar de novo continua de onde parou.
- [x] Deduplicação, nomes primeiro e pedidos em paralelo (Gemini) valem para a fila.
- [x] Busca no projeto inteiro e progresso por arquivo na lista (SQLite).

### Fase 3 — Testar no jogo (feito)
- [x] **Aplicar no jogo**: grava os arquivos traduzidos na pasta do jogo, gerados a
      partir dos originais guardados + traduções do banco. O arquivo que estava no jogo
      é guardado na primeira vez (`projects/<id>/game-backup/`).
- [x] **Restaurar jogo original** com um clique.
- [x] **Aplicar e abrir o jogo (F5)**: aplica e inicia o executável do jogo
      (detectado pela pasta `*_Data` da Unity).
- [x] Sem originais guardados, eles são copiados do jogo antes da primeira aplicação,
      para o app nunca ler a tradução como se fosse o original.

### Fase 4 — Builds novas do jogo (feito)
- [x] **Nova versão do jogo…**: compara a build nova com o projeto, arquivo por arquivo:
      iguais (tradução vale), alterados (mesmo lugar, texto parecido: tradução anterior
      "a revisar"), movidos (mesmo texto em outro lugar: tradução reaproveitada "a
      revisar") e novos (pendentes).
- [x] Relatório antes de aplicar; ao aplicar, a build nova vira a base do projeto.
- [x] Recusa comparar a pasta do jogo enquanto ela tem a tradução aplicada.

### Fase 5 — Qualidade (parcial, decisão)
- [x] Memória de tradução por idioma e regras de localização nos prompts.
- **Decisão:** sem glossário "pronto" por jogo: o app traduz para vários idiomas e
  manter glossários prontos para todos não escala. Nomes ficam consistentes pela fase
  "nomes primeiro"; o glossário do usuário continua tendo prioridade.
- [ ] Verificações automáticas (tags `<b>`, placeholders, tamanho) — opcional.

### Fase 6 — Compartilhar (feito)
- [x] **Exportar XMLs traduzidos** para uma pasta (para os devs ou a comunidade).
- [x] **Pacote de tradução** (`.stzpack`): traduções de um idioma + glossário.
- [x] **Importar pacote**: entra como "a revisar", nunca sobrescreve o que já está
      traduzido no projeto (conflitos são contados e mantidos), glossário completa os
      termos que faltam.

## Armazenamento em SQLite

**Feito (primeira etapa):** `core/store.py` com um `translations.db` na pasta de
dados do usuário.
- `translations` por arquivo + idioma + xpath, com o original (só aplica se o
  original ainda for igual) e `history` com cada mudança e sua origem
  (IA, edição, confirmação, importação).
- Chave estável: `<id do projeto>:<caminho dentro da pasta>` dentro de um
  projeto, `file:<nome>` fora; o progresso de um arquivo avulso é levado para o
  projeto na primeira abertura.
- Na primeira abertura de cada arquivo, os checkpoints JSON são importados; eles
  continuam sendo gravados como backup portátil.
- A lista do projeto lê o progresso do banco; a tela de tradução mostra o
  histórico da entrada com **Restaurar**.

**Feito (segunda etapa):**
- Busca de texto no projeto inteiro (original ou tradução) na tela do projeto;
  clicar num resultado abre o arquivo já filtrado naquele texto. `LIKE` com
  índice resolve ~100 mil textos sem precisar de FTS5.
- Memória de tradução: o painel da entrada sugere como o mesmo original já foi
  traduzido em qualquer arquivo (confirmadas primeiro); usar uma sugestão fica
  no histórico como "Memória".

**Decisão:** os checkpoints JSON continuam sendo gravados. São um backup legível
e portátil, e custam pouco; o banco é a fonte principal.

**Fica para depois:** exportar/importar o banco de um projeto (entra na Fase 6).

### Análise original

**Hoje:** cada combinação arquivo + idioma + seleção é um JSON em `checkpoints/`;
projetos, glossário e presets são outros JSONs. Funciona, mas:
- não há histórico (uma tradução sobrescrita some);
- buscar no projeto inteiro exige abrir dezenas de JSONs (no MAA, ~100 mil textos);
- a lista do projeto lê um checkpoint por arquivo só para mostrar o progresso;
- memória de tradução (mesmo original → mesma tradução em outro arquivo) não tem onde morar.

**Proposta** (mesmo padrão do GF UI Editor): um `project.db` por projeto em
`Documentos/STZ Translation Projects/<nome>/`.

```
files(id, rel_path, size, mtime, groups_json)
entries(id, file_id, xpath, original, original_hash, source_tag, context_json)
translations(entry_id, lang, text, status, error, updated_at)   -- PK (entry_id, lang)
history(id, entry_id, lang, old_text, new_text, old_status, new_status, source, at)
        -- source: ai | manual | import | confirm
glossary(lang, original, translation)
entries_fts  -- FTS5 sobre original + tradução: busca instantânea no jogo todo
```

- **Viabilidade: alta.** `sqlite3` é da biblioteca padrão (sem dependência nova,
  Nuitka já inclui) e o motor é um processo único, sem disputa de escrita.
- **Ganhos:** histórico por entrada com desfazer; busca global instantânea (FTS5);
  progresso do projeto numa consulta; memória de tradução por `original_hash`;
  backup = copiar um arquivo; Fase 4 (build nova) vira uma comparação de `original_hash`.
- **Custo:** reescrever a persistência do `TranslationProject` (hoje
  `save_checkpoint`/`load_checkpoint`) para gravar por entrada em vez do
  arquivo inteiro; migração automática dos checkpoints JSON na primeira
  abertura; continuar exportando JSON/CSV para backup e compatibilidade.
- **Ordem sugerida:** junto com a Fase 2 (fila global e busca no projeto), porque
  é ela que mais sofre com dezenas de JSONs.

## Integração com agentes de código (MCP)

**Feito:** `engine/mcp_server.py` (SDK oficial `mcp` 2.x, extra `[mcp]` do
`pyproject`), 22 ferramentas sobre a mesma `Session`. Como configurar e a lista
de ferramentas estão em [MCP.md](MCP.md). Traduções do agente entram no
histórico como "Agente".

### Análise original

Um **servidor MCP** é um programa pequeno que um agente (Claude Code, Codex,
Cursor...) inicia e que expõe **ferramentas** com nome, descrição e parâmetros.
O agente decide quando chamá-las. Como o motor já tem uma API HTTP local
(`engine/server.py`), o servidor MCP é um adaptador fino sobre as mesmas funções
da `Session`, usando o SDK oficial em Python (`mcp`, com `FastMCP`).

Ferramentas propostas:

| Ferramenta | O que faz |
| --- | --- |
| `list_projects` / `open_project` | projetos e arquivos com progresso |
| `analyze_file` | tags e campos sugeridos (com o perfil do jogo) |
| `load_file` | carrega um arquivo com os grupos sugeridos ou escolhidos |
| `list_entries` | entradas filtradas por estado, busca ou arquivo, em páginas |
| `set_translation` / `confirm` | grava ou confirma traduções em lote |
| `translate_pending` | usa o provedor configurado (Gemini, Ollama...) |
| `glossary_get` / `glossary_set` | consulta e mantém o glossário |
| `export_xml` / `apply_to_game` | exporta ou aplica no jogo (Fase 3) |

- O agente pode traduzir com o próprio modelo (sem chave de API no app),
  revisar o que a IA do app fez e rodar verificações (tags `<b>`, placeholders).
- Distribuição: um comando `stz-xml-translator mcp` (stdio) que o usuário
  registra no `.mcp.json` do agente; o app e o MCP podem compartilhar o mesmo
  projeto, porque o estado fica em disco (melhor ainda com o SQLite acima).
- **Viabilidade: alta**, pouco código; depende de quais ações devem exigir
  confirmação (aplicar no jogo, sobrescrever confirmadas).

## Fora do escopo do app (anotado para referência)

- **Save do MAA Redux:** fica em `MAA Redux_Data\Resources\Saves\<nome>.save`.
  É assinado e não deve ser editado (o próprio jogo avisa que um save modificado
  volta ao nível 0). Saves de outros jogadores funcionam, então para revisar
  telas avançadas use saves avançados da comunidade. Os menus "COMING SOON"
  dependem de progresso: "Collection" aparece liberado numa conta de nível 123.
- **Textos fora dos XMLs:** uma parte da interface está em `data.unity3d` /
  `GameAssembly.dll`. Esses textos não dá para traduzir de forma limpa; o caminho
  é pedir aos devs que os movam para os XMLs. O app pode ajudar gerando a lista
  de telas e strings que ainda não estão traduzíveis.

## Ordem sugerida

Fase 1 → Fase 2 → Fase 3 entregam a experiência de "abrir o projeto e continuar".
A Fase 4 vem em seguida, porque cada build nova do MAA depende dela.
