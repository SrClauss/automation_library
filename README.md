# Guia de Adaptação do Framework de Automação

Este documento explica como adaptar e integrar novas fontes de entrada (Input) e destinos de saída (Storage) ao framework genérico de automação. Está escrito para desenvolvedores que querem transformar uma fonte específica (Excel, CSV, JSON, SQLite, PostgreSQL, etc.) em um provedor de tarefas utilizável pela UI e pelos workers.

Conteúdo
- Visão geral
- Contratos (interfaces) principais
- Implementando um `BaseInput` (ex.: ExcelInput)
- Implementando um `BaseStorage` (ex.: SQLiteStorage)
 Como integrar ao adapter
 Como integrar à UI
 Boas práticas e notas
---
## Integrando ao adapter
<!-- Menções específicas a adaptadores concretos foram removidas. Use `input_class` e `input_id_key` para integrar qualquer adapter generically. -->
O framework separa responsabilidades em três peças principais:

- Authenticator: cuida do login e retorno de uma sessão (driver). (ver `BaseAuthenticator`)
- Extractor: dado um `TaskItem` e uma sessão, extrai os dados do site. (ver `BaseExtractor`)
- Input: provedor de entradas (gera `TaskItem`s a processar). (ver `BaseInput`)
- Storage: persiste os resultados extraídos. (ver `BaseStorage`)

O fluxo típico é:

1. Input fornece uma sequência (preferencialmente lazy) de `TaskItem`s.
2. UI enfileira esses itens para os workers.
3. Workers usam Authenticator/Extractor para obter dados para cada `TaskItem`.
4. Results são coletados e enviados ao Storage para persistência.

Importante: para cada `TaskItem` de entrada deve haver uma saída correspondente (mesmo que nula). Itens que forem considerados inválidos devem ser marcados/filtrados pelo usuário e não retornarem para a fila.

---

## Contratos (interfaces) principais

As interfaces ficam em `core/interfaces.py`. Resumo dos métodos relevantes:

- BaseInput
  - uses_file: bool (atributo de classe). Se True a UI deve exibir controles de arquivo.
  - open(): prepara o provedor (abrir arquivo/abrir conexões).
  - get_items() -> Iterable[TaskItem]: gera `TaskItem`s. Cada `TaskItem` deve conter ao menos um identificador (ex: `code`, `id`, `uuid`).
  - close(): libera recursos.

- BaseStorage
  - open(): prepara a persistência (criar arquivo/conexão/tabela).
  - save_items(items: List[DataItem]): salva lote de itens.
  - get_processed_items() -> Iterable[TaskItem]: retorna ids já processados para permitir continuação.
  - close(): finalizar gravação.

---

## Implementando um `BaseInput` (ex.: ExcelInput)

Recomendação: `get_items()` deve ser lazy (usar `yield`) para não carregar tudo na memória.

Exemplo mínimo (esqueleto) — já existe uma implementação `adapters/input/excel_input.py`:

```python
class ExcelInput(BaseInput):
    uses_file = True

    def __init__(self, file_path: str, sheet_name: Optional[str] = None, code_column: str = 'A', start_row: int = 2, id_key: str = 'code'):
        ...

    def open(self):
        # abrir workbook em modo read_only
        ...

    def get_items(self):
        # iterar linhas e yield { id_key: '...', 'description': '...', 'row_num': ... }
        ...

    def close(self):
        # fechar workbook
        ...
```

Observações importantes:
- Garanta que cada item retornado contenha a chave identificadora acordada (ex: `code`).
- Inclua metadados úteis (`row_num`, `origin`, `description`) quando possível.
- Se o formato for CSV/JSON/DB, crie classes específicas (CSVInput, JSONInput, SQLInput) e marque `uses_file=False` para DBs.

---

## Implementando um `BaseStorage` (ex.: SQLiteStorage)

Requisitos básicos:

- A tabela deve ter uma coluna que corresponda ao `task_id_key` (ex: `row_num` ou `code`) e ser PRIMARY KEY para permitir upsert.
- `get_processed_items()` deve retornar os ids já presentes para permitir continuação parcial.

Exemplo (esquemático):

```python
class SQLiteStorage(BaseStorage):
    def __init__(self, db_path: str, table_name: str, headers: Dict[str,str], input_file_hash: str, task_id_key: str):
        ...

    def open(self):
        # conectar e criar tabela se não existir

    def save_items(self, items):
        # INSERT OR REPLACE por task_id_key

    def get_processed_items(self):
        # SELECT task_id_key FROM table

    def close(self):
        # fechar conexão

```

Nota: para sqlite, cuidado com escrita concorrente — prefira um escritor único (o pipeline central chama `save_items`) ou use uma fila e lock.

---

## Integrando ao adapter (ex.: AtlasCopco)

Cada adapter (ex.: `adapters/automation_adapter.py`) deve expor ao menos:

- `authenticator_class` — classe que herda de `BaseAuthenticator`.
- `extractor_class` — classe que herda de `BaseExtractor`.
- `input_class` — classe que herda de `BaseInput` (pode ser um placeholder até implementar concretamente).
- `input_id_key` — string com o nome do campo do `TaskItem` que contém o identificador (ex: `'code'`).

No adapter AtlasCopco já existe um placeholder `AtlasCopcoInput` e foi adicionada uma implementação `AtlasCopcoExcelInput`. O extractor espera `task_item['code']` por padrão; para maior flexibilidade, o extractor pode ler `task_item.get(input_id_key)`.

---

## Integrando à UI (`core/ui.py`)

Passos principais que a UI deve realizar ao iniciar o processamento:

1. Descobrir/selecionar `input_class` do adapter (ou via configuração).
2. Se `input_class.uses_file` for True: mostrar botão para selecionar arquivo e coletar `file_path`.
3. Instanciar input: `input = input_class(file_path=..., ...)` e chamar `input.open()`.
4. Enfileirar itens: `for task in input.get_items(): tasks_queue.put(task)`.
5. Iniciar pool de workers (autenticador/extractor) como já implementado.
6. Ao finalizar chamar `input.close()` e `storage.close()`.

Pseudocódigo dentro de `start_process()`:

```python
input = input_class(file_path=selected_file, sheet_name=...)  # argumentos conforme implementação
input.open()
for item in input.get_items():
    tasks_queue.put(item)

# prosseguir com criação de workers
```

Observação: ao usar a mesma fonte como input e output (ex.: mesma tabela SQLite), garanta que o storage faça upsert para preencher os dados sem duplicar.

---

## Tratamento de 'buracos' e itens inválidos

- Buracos (resultados nulos por timeout ou falha temporária): marque-os com um status (ex.: `"status": "NULO"`) e mantenha o `task_id` para reprocessamento posterior.
- Itens inválidos (ex.: descontinuado): defina um status definitivo (ex.: `"status": "INVALIDO"`) e opte por não reenfileirá-los.
- Recomenda-se que o storage mantenha uma coluna `status` para rastrear esses estados.

---

## Boas práticas

- Não commit suas credenciais — mantenha `config.json` como template e use `config_local.json` (ou variáveis de ambiente) para credenciais.
- Teste o Input localmente (executando um pequeno script que instancia e percorre `get_items()`).
- Prefira `get_items()` por streaming para arquivos grandes.
- Documente os `id_key` usados por cada adapter para evitar divergências.

---

## Como rodar rapidamente

1. Instale dependências (recomendo um virtualenv):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Execute a GUI:

```bash
python3 run_gui.py
```

3. Se quiser testar apenas um Input:

```python
from adapters.input.excel_input import ExcelInput

inp = ExcelInput('/caminho/para/arquivo.xlsx', code_column='A')
inp.open()
for t in inp.get_items():
    print(t)
inp.close()
```

---

Se quiser, eu posso:

- Ajustar `core/ui.py` para integrar automaticamente `input_class` e enfileirar itens.
- Implementar `SQLiteStorage` e um `SQLiteInput` para testes de integração.

Contribuições, dúvidas e solicitações: abra uma issue ou peça para eu implementar a etapa seguinte.
