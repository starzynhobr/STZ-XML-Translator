# STZ XML Translator para agentes de código (MCP)

O tradutor expõe suas funções como um **servidor MCP**. Um agente de código
(Claude Code, Codex, Cursor, VS Code...) inicia o servidor e passa a usar
ferramentas como `load_file`, `list_entries` e `set_translations`: abre o jogo,
lê o que falta traduzir, grava as traduções e exporta o XML, com o mesmo
projeto, histórico e glossário do app.

O agente pode traduzir com o próprio modelo (sem chave de API no app), revisar o
que a IA do app fez ou usar o provedor configurado no app (`translate_with_provider`).

## Instalação

Na pasta do repositório:

```bash
pip install -e ".[mcp]"
```

## Configurar no agente

O comando é `python -m engine.mcp_server`, executado na pasta do repositório.
Escolha onde ficam os dados:

| Opção | Dados usados |
| --- | --- |
| *(nenhuma)* | a pasta do repositório (o mesmo que `start.bat` / modo de desenvolvimento) |
| `--app-data` | os projetos e traduções do app instalado (`%LOCALAPPDATA%\STZ XML Translator`) |
| `--data-dir PASTA` | qualquer outra pasta |

**Claude Code** — `.mcp.json` na raiz do projeto em que o agente trabalha:

```json
{
  "mcpServers": {
    "stz-xml-translator": {
      "command": "C:/Users/<você>/Documents/PROJETOSGIT/STZ-XML-Translator/.venv/Scripts/python.exe",
      "args": ["-m", "engine.mcp_server", "--app-data"],
      "cwd": "C:/Users/<você>/Documents/PROJETOSGIT/STZ-XML-Translator"
    }
  }
}
```

Ou pela linha de comando:

```bash
claude mcp add stz-xml-translator -- C:/caminho/STZ-XML-Translator/.venv/Scripts/python.exe -m engine.mcp_server --app-data
```

Outros agentes usam o mesmo comando e argumentos no formato de configuração
deles.

## Ferramentas

| Ferramenta | O que faz |
| --- | --- |
| `status` | projeto e arquivo abertos, idioma, provedor e contagens |
| `list_projects` / `create_project` / `open_project` | projetos; `create_project` aceita qualquer nível da pasta do jogo |
| `analyze_file` | tags e campos sugeridos para um XML (com o perfil do jogo) |
| `load_file` | carrega um XML com os campos sugeridos (ou `groups` escolhidos) e restaura o progresso |
| `list_entries` | entradas por estado (`pending`, `translated`, `confirmed`, `error`, `all`), busca e campo, em páginas |
| `set_translations` | grava traduções em lote (`confirm=true` já marca como revisadas) |
| `confirm_entries` | marca como revisadas |
| `translate_with_provider` | traduz pendentes com o provedor do app (Gemini, Ollama...) e espera terminar |
| `search_project` | procura um texto em todos os arquivos já abertos do projeto |
| `entry_history` | versões anteriores de uma entrada e de onde vieram |
| `get_glossary` / `add_glossary_terms` | glossário do idioma atual |
| `export_xml` | grava o XML traduzido, sem mexer na estrutura |

Erros voltam com um código estável (`error: no_file`, `error: folder_not_found`...).

## Como funciona

- O servidor roda num processo próprio com a mesma `Session` do motor do app.
  Projetos, `translations.db` e glossário são compartilhados pela pasta de
  dados; o arquivo aberto é de cada processo.
- O que o agente grava entra no histórico com a origem **Agente**, visível no
  painel da entrada no app, com **Restaurar**.
- Traduções do agente ficam como "a revisar", a menos que ele confirme.
