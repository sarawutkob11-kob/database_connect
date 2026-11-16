# Claude Code Implementation Brief: Safe Refactor Without Output Regression

## 1. Objective

Refactor `<File>database_connect_gui.py</File>` to address SQL safety, Tkinter thread safety, Auto Sync state consistency, template validation, Excel parameter replacement, large Excel export memory usage, SQL classification, SQL Server ODBC driver selection, and database connection tracking.

The application is a desktop database client built with Python, Tkinter, pandas, SQLAlchemy, openpyxl, and multiple DBAPI drivers.

**Primary constraint:** improve safety, reliability, and scalability **without changing existing intended results or user-visible behavior**, except where this document explicitly requests a safety prompt, preview, validation error, or configuration option.

---

## 2. Non-goals and intentional behavior

Do **not** remove or redesign the following intentional behavior:

1. Profile export may include passwords in plain text when the user explicitly chooses **Yes**.
2. Decrypted database passwords may exist in process memory while the application is running.
3. The application remains a general SQL client and must continue supporting SELECT, DML, DDL, stored procedures, and database-specific SQL where currently supported.
4. Existing database values, result-column names, numeric precision, NULL display, date/time display, Excel cell types, sheet naming, SQL text, job order, and commit behavior must remain unchanged unless explicitly stated.
5. Do not introduce a mandatory external SQL parser dependency unless absolutely necessary. Prefer standard-library implementation plus existing dependencies.
6. Do not redesign the UI or rename existing public methods unless a compatibility wrapper is retained.

For intentional plain-text password export, only improve the warning against accidental use. Do not disable the feature.

---

## 3. Global implementation rules

### 3.1 Preserve behavior

Before editing, identify all call sites of these methods and preserve their contracts:

- `is_select_query`
- `execute_query`
- `_execute_query_background`
- `read_sql_dataframe`
- `run_job`
- `run_selected_job`
- `export_jobs_to_excel`
- `auto_replace_table_variables`
- `check_and_sync_table_data`
- `load_query_template_dialog`
- `_track_engine_connections`
- `get_connection_string`
- `connect_database`

Where a method is replaced internally, keep a backwards-compatible wrapper when other code may call it.

### 3.2 Main-thread-only Tkinter rule

Only the Tkinter main thread may:

- read or write a Tk widget;
- call `.get()` or `.set()` on a Tk variable;
- call `messagebox` or `filedialog`;
- create, destroy, configure, pack, grid, place, bind, or inspect widgets;
- call `root.update()` or `root.update_idletasks()`.

Worker threads may perform only database, filesystem, parsing, formatting, and calculation work on immutable snapshots.

### 3.3 Do not silently change results

The refactor must not silently:

- add `LIMIT`, `TOP`, or `FETCH FIRST` to user SQL;
- reorder rows;
- alter database-returned column names;
- convert exact decimals to floats;
- change `[NULL]` handling;
- trim CHAR values;
- change Excel number/date/text behavior;
- execute skipped non-SELECT jobs during export;
- change current transaction commit semantics;
- alter query text stored in saved jobs, presets, groups, or profiles.

### 3.4 Small, reviewable changes

Implement in phases. After every phase:

1. run syntax checks;
2. run focused unit tests;
3. run regression tests;
4. inspect the diff for unrelated UI or formatting changes.

Do not combine unrelated visual refactoring with the safety changes.

---

## 4. Phase 0: Baseline and regression characterization

Before changing production code, create tests that lock down current intended behavior.

### Required baseline tests

Create a test module such as:

```text
tests/test_database_connect_gui_core.py
```

Tests must not require a real GUI display or live database. Extract or test pure helper functions wherever possible.

Cover at least:

1. `format_db_value`:
   - `None` and `pd.NaT` become `[NULL]`;
   - exact `decimal.Decimal` formatting;
   - integer-looking floats;
   - bytes to uppercase hex;
   - datetime milliseconds.
2. `excel_db_value` and `excel_number_format`:
   - numbers over 15 digits remain text;
   - dates remain real dates;
   - NULL remains `[NULL]`.
3. Excel sheet-name sanitization and duplicate naming.
4. SQL classification examples listed in section 6.
5. SQL token replacement examples listed in section 10.
6. Query-template validation examples listed in section 9.
7. SQL Server driver-selection priority.
8. Large export row splitting without loading all rows into a DataFrame.
9. Auto Sync does not overwrite an edited SQL template.
10. Stale Auto Sync results are ignored.

If direct unit testing is difficult because helpers are nested inside GUI methods, extract pure helpers into the same file near the top or into a small module such as `database_connect_core.py`. Avoid a broad architecture rewrite.

---

## 5. Shared concurrency infrastructure

Add these state members during application initialization:

```python
import queue

self._ui_queue = queue.Queue()
self._state_lock = threading.RLock()
self._closing = False
self._sync_generation = 0
self._editor_revision = 0
self._engine_generation = 0
self._active_db_connections = set()
self._active_db_lock = threading.Lock()
self.root.after(50, self._drain_ui_queue)
```

Add a main-thread queue:

```python
def _post_to_ui(self, callback, *args, **kwargs):
    if self._closing:
        return
    self._ui_queue.put((callback, args, kwargs))


def _drain_ui_queue(self):
    if self._closing:
        return
    try:
        while True:
            callback, args, kwargs = self._ui_queue.get_nowait()
            callback(*args, **kwargs)
    except queue.Empty:
        pass
    except tk.TclError:
        return
    self.root.after(50, self._drain_ui_queue)
```

Update `on_closing` before destroying the root:

```python
self._closing = True
```

### Required refactor pattern

Capture widget values on the main thread before creating a worker:

```python
@dataclass(frozen=True)
class ConnectionSnapshot:
    db_type: str
    user: str
    password: str
    host: str
    port: str
    database: str
```

The worker receives the snapshot and must not call Tkinter.

Replace worker-thread UI callbacks such as:

```python
self.root.after(0, ...)
```

with:

```python
self._post_to_ui(callback, ...)
```

Using `root.after` from workers often appears to work but still invokes a Tk command outside the main thread. Standardize on the queue.

### Audit requirement

Search every `threading.Thread` target. For each target, verify it does not access:

- `self.root`;
- any Tk widget;
- any `tk.*Var`;
- `messagebox`;
- `filedialog`.

Shared non-Tk state must be protected by `_state_lock` or replaced atomically with an immutable object.

---

## 6. Robust SQL classification and execution policy

Replace the current `startswith`-based classification with a shared classifier. Keep `is_select_query(query)` as a compatibility wrapper returning whether the classified statement is read-only/result-producing according to existing application expectations.

### 6.1 Required data model

```python
from dataclasses import dataclass
from enum import Enum, auto


class SqlRisk(Enum):
    READ_ONLY = auto()
    DATA_CHANGE = auto()
    SCHEMA_CHANGE = auto()
    ADMIN = auto()
    UNKNOWN = auto()


@dataclass(frozen=True)
class SqlAssessment:
    command: str
    risk: SqlRisk
    statement_count: int
    reason: str = ""
```

### 6.2 Lexer requirements

Implement a lightweight scanner that understands enough SQL structure to:

- skip whitespace;
- skip `-- line comments`;
- skip `/* block comments */`;
- preserve quoted strings;
- handle doubled quote escapes such as `'O''Brien'`;
- handle quoted identifiers (`"name"`, `[name]`, and backticks where appropriate);
- split statements only on semicolons outside strings/comments;
- ignore an Oracle trailing `/` terminator;
- locate the top-level command after a `WITH` CTE;
- distinguish `WITH ... SELECT` from `WITH ... UPDATE/DELETE/INSERT/MERGE`.

Do not classify every `WITH` statement as SELECT.

### 6.3 Classification expectations

At minimum, classify:

- `SELECT`, `SHOW`, `DESCRIBE`, `DESC`, and read-only `EXPLAIN` as `READ_ONLY`;
- `INSERT`, `UPDATE`, `DELETE`, and `MERGE` as `DATA_CHANGE`;
- `CREATE`, `ALTER`, `DROP`, `TRUNCATE`, `RENAME`, and `COMMENT` as `SCHEMA_CHANGE`;
- administrative statements such as `ALTER SYSTEM`, `DROP DATABASE`, `CREATE USER`, `DROP USER`, `GRANT`, `REVOKE`, `SHUTDOWN`, and `STARTUP` as `ADMIN`;
- unrecognized commands as `UNKNOWN`.

Stored procedure calls (`CALL`, `EXEC`, `EXECUTE`, anonymous PL/SQL blocks) may produce result sets or change data. Classify as `UNKNOWN` unless existing execution behavior requires a database-specific path. Do not falsely label them read-only.

### 6.4 Multi-statement behavior

Do not change the current execution result silently. Before execution:

- if more than one non-empty statement is detected, block by default with a clear validation message;
- add one application constant such as `ALLOW_MULTI_STATEMENT_SQL = False`;
- do not execute partial statements.

### 6.5 Central execution validation

Create one method used by direct execution, single jobs, batch jobs, and relevant exports:

```python
def _assess_sql_for_execution(self, sql):
    assessment = assess_sql(sql)
    if assessment.statement_count != 1 and not ALLOW_MULTI_STATEMENT_SQL:
        raise ValueError("Multiple SQL statements are disabled. Run one statement at a time.")
    return assessment
```

Use the assessment to decide SELECT/result handling and confirmation behavior. Remove duplicated detection logic where safe.

### 6.6 Confirmation behavior

Preserve the existing confirmation for modifying statements, but improve the categories:

- `READ_ONLY`: no modification prompt;
- `DATA_CHANGE`: existing “commit immediately” prompt;
- `SCHEMA_CHANGE`: stronger warning identifying DDL and possible implicit commit;
- `ADMIN`: block by default using an application constant, or require a separate explicit opt-in if existing users require it;
- `UNKNOWN`: warn that the effect cannot be confidently determined.

Do not claim that textual classification alone makes SQL safe. Database permissions remain authoritative.

### Required tests

```sql
-- comment
SELECT 1;
```

```sql
/* comment */ SELECT ';' AS value;
```

```sql
WITH x AS (SELECT 1 AS id) SELECT * FROM x;
```

```sql
WITH x AS (SELECT 1 AS id) DELETE FROM target WHERE id IN (SELECT id FROM x);
```

```sql
WITH x AS (SELECT 1 AS id) UPDATE target SET flag = 1;
```

```sql
SELECT 'DELETE FROM x' AS text;
```

```sql
BEGIN
  UPDATE target SET flag = 1;
END;
/
```

```sql
SELECT 1; DELETE FROM target;
```

---

## 7. SQL execution safety without altering valid query results

Do not rewrite arbitrary user SQL. Add safety around execution instead.

### Required changes

1. Use the shared SQL assessment everywhere.
2. Preserve exact submitted SQL except for existing removal of trailing `;` or Oracle `/` in the DBAPI cursor path.
3. Do not append row limits automatically.
4. Continue using database accounts and their permissions as the final authorization boundary.
5. Add optional read-only mode if it can be integrated without breaking current defaults. Default must preserve current behavior unless product requirements say otherwise.
6. Keep current immediate commit behavior for DML after confirmation.
7. DDL warnings must mention that some databases implicitly commit DDL.
8. Unknown statements must not be treated as SELECT merely because they contain `SELECT` internally.

### Excel/table-derived values

Where feasible, newly implemented parameter paths should use SQLAlchemy bind parameters, particularly expanding `IN` parameters. Do not attempt to reinterpret or rewrite all existing saved raw SQL in this change.

Preferred pattern for new parameter execution:

```python
stmt = text(
    "SELECT * FROM account WHERE account_no IN :account_numbers"
).bindparams(bindparam("account_numbers", expanding=True))
params = {"account_numbers": values}
```

If database-specific limitations prevent binding in a given path, retain current exact SQL literal formatting and use the token-aware renderer in section 10.

---

## 8. Auto Sync: preserve the SQL template and avoid editor overwrite

Current Auto Sync replaces placeholders in the editor. Change the model so Auto Sync refreshes data and rendered preview without silently changing the user’s SQL text.

### 8.1 Required state

Maintain separate values:

```python
self.sql_template
self._table_parameter_values
self._rendered_sql_preview
self._sync_generation
self._editor_revision
```

The SQL editor is the source template unless the existing Excel-template workflow explicitly tracks a different template.

### 8.2 Editor revision tracking

Bind `<<Modified>>` on the SQL editor. When modified by the user:

```python
self._editor_revision += 1
```

Programmatic writes must use a small guard so they do not falsely count as user edits:

```python
self._programmatic_editor_update = True
try:
    ...
finally:
    self._programmatic_editor_update = False
```

### 8.3 Sync workflow

1. Main thread captures:
   - sync generation;
   - editor revision;
   - table-data path;
   - immutable copy of relevant mapping state.
2. Worker reads and validates JSON into a new local object.
3. Worker posts a completed immutable result to the UI queue.
4. Main thread discards the result if its generation is stale.
5. Main thread atomically replaces `loaded_table_data` and parameter snapshot.
6. Main thread renders a preview.
7. Main thread does **not** overwrite the editor automatically.

### 8.4 Execution behavior

When a synced rendered version exists, make the choice explicit:

- `Run` may execute the rendered SQL if that matches existing product intent, but display an indicator that synced parameters are applied;
- provide a “Review/Apply to editor” action if a preview is already present;
- never destroy the original template silently.

If changing Run semantics risks regression, keep Run using current editor SQL and add a separate explicit “Apply synced values” action. Prefer preservation over surprise.

### 8.5 Compatibility wrapper

Keep `auto_replace_table_variables()` callable, but refactor it to produce/render a result without directly rewriting the editor. If another feature explicitly requests application, add an `apply_to_editor=False` argument whose default is safe.

### Required acceptance tests

- Syncing twice updates values each time because placeholders remain in the template.
- Editing SQL during a file read prevents stale sync output from overwriting or applying to the new SQL.
- Two overlapping sync checks apply only the latest generation.
- Invalid JSON leaves the last known-good state untouched.
- A missing variable produces a visible validation error and does not partially modify SQL.

---

## 9. Query-template validation

Validate `query_templates.json` before populating the UI or loading SQL into the editor.

### Validation constraints

Use constants:

```python
MAX_TEMPLATE_COUNT = 1000
MAX_TEMPLATE_NAME_LENGTH = 100
MAX_TEMPLATE_SQL_LENGTH = 1_000_000
```

Validation must require:

- root object is a dictionary;
- number of templates does not exceed the limit;
- each key is a non-empty string within the name limit;
- each value is a dictionary;
- `query` is a non-empty string within the SQL limit;
- optional `created` is a string or `None`;
- no unexpected executable Python/object deserialization is used;
- SQL is assessed and marked with its risk category.

Do not reject valid DML/DDL templates merely because they are modifying. Display the category and enforce confirmation at execution time. Block malformed and multi-statement templates according to the central policy.

### Failure behavior

- show one concise error identifying the invalid template;
- do not partially load the file;
- preserve the previously loaded in-memory template collection;
- do not clear the current SQL editor;
- log the validation error without exposing passwords.

### UI improvement

In the template picker, show a prefix or category such as:

```text
[READ ONLY] Customer lookup
[DATA CHANGE] Reset status
[SCHEMA CHANGE] Create staging table
```

Do not change stored template names.

---

## 10. Token-aware Excel/table parameter replacement

Remove broad `str.replace()` for table variables.

### 10.1 Canonical token format

For newly created variables, use an unambiguous token:

```text
{{TABLE:table_name:column_name}}
```

Continue supporting the legacy format:

```text
{TABLE_TABLE_NAME_COLUMN_NAME}
```

Do not automatically rewrite saved jobs or templates. Support both formats during a migration period.

### 10.2 Renderer requirements

Implement pure functions that:

- recognize only complete tokens;
- replace via `re.sub` callback, not global blind replacement;
- return a new SQL string;
- never mutate the input template;
- detect missing tokens;
- detect ambiguous legacy tokens;
- either replace all exact occurrences intentionally or support an occurrence identifier;
- escape SQL string values exactly once;
- preserve numeric values as numeric literals;
- preserve existing value ordering and duplicates unless current code intentionally deduplicates that path;
- make no replacement inside similar ordinary text.

Suggested result type:

```python
@dataclass(frozen=True)
class TemplateRenderResult:
    sql: str
    replaced_tokens: tuple[str, ...]
    missing_tokens: tuple[str, ...]
```

Do not update the editor if `missing_tokens` is not empty.

### Legacy ambiguity

The legacy token combines table and column using underscores, making names ambiguous. Resolve it using actual loaded table and column metadata:

1. Build all valid legacy token strings from loaded metadata.
2. Match the full token string exactly.
3. If two metadata pairs produce the same token, raise an ambiguity error and request migration to canonical format.

### Required tests

- token repeated twice is replaced twice intentionally;
- a token-like substring is not replaced;
- apostrophes become doubled once;
- `None` handling follows the existing requirement for that path;
- table/column names containing underscores work when metadata disambiguates them;
- ambiguous legacy names fail without modifying the SQL;
- missing values fail atomically;
- the original template remains unchanged.

---

## 11. Scalable Excel export without result changes

The current export loads an entire result into a DataFrame and writes a normal openpyxl workbook. Add a streaming path for query results that are not already cached as DataFrames.

### 11.1 Preserve existing cached-result behavior

If a job contains `_export_dataframe`, continue exporting that exact DataFrame so that “reuse last run results” produces the same result as before.

For newly executed export queries, stream from a DBAPI cursor using `fetchmany`.

### 11.2 Constants

```python
EXPORT_FETCH_SIZE = 10_000
EXCEL_MAX_ROWS = 1_048_576
EXCEL_DATA_ROWS_PER_SHEET = EXCEL_MAX_ROWS - 1
EXPORT_WIDTH_SAMPLE_ROWS = 1_000
```

If SQL text is appended below data, it cannot fit when data reaches the sheet limit. Put SQL in a separate metadata sheet or reserve rows explicitly. Preserve current user access to the original SQL.

Recommended layout:

- result sheets contain header plus data only;
- one `_SQL` or `_Metadata` sheet contains job name, result sheet names, row counts, status, and original SQL;
- if this visible layout change is unacceptable, reserve sufficient rows and document the reduced maximum. Prefer a metadata sheet for correctness.

### 11.3 Streaming cursor

Implement a context-managed iterator:

```python
def iter_query_batches(engine, sql, fetch_size):
    ...
    yield columns, batch
```

Requirements:

- remove the driver-incompatible trailing SQL terminator exactly as existing `read_sql_dataframe` does;
- apply the existing Oracle output type handler so Decimal, CLOB, NCLOB, and BLOB results remain equivalent;
- use `fetchmany(EXPORT_FETCH_SIZE)`;
- close cursor and raw connection in `finally`;
- respond to `_stop_event` between batches;
- do not call `fetchall`;
- do not construct one complete DataFrame.

### 11.4 Write-only workbook

Use:

```python
openpyxl.Workbook(write_only=True)
```

for the streaming path.

Preserve:

- exact column names;
- `excel_db_value` conversion;
- `excel_number_format` behavior;
- header fill if supported by write-only cells;
- borders where practical without excessive memory;
- UTC/timezone conversion behavior;
- illegal character cleaning;
- long-number-as-text behavior;
- `[NULL]` behavior;
- sheet-name sanitization and duplicate suffixing;
- one logical job represented even when split across multiple sheets.

Use `WriteOnlyCell` for styles and number formats.

### 11.5 Sheet splitting

Split when a result exceeds `EXCEL_DATA_ROWS_PER_SHEET`:

```text
JobName
JobName_2
JobName_3
```

Ensure names remain unique and at most 31 characters after suffixing.

### 11.6 Column width trade-off

Because write-only sheets cannot be rescanned, calculate widths from:

- column names;
- at most the first `EXPORT_WIDTH_SAMPLE_ROWS` rows.

Cap width at the existing limit of 80. Apply dimensions before saving if supported. Do not buffer more than the sample plus one fetch batch.

### 11.7 Atomic output

Write to:

```text
<selected path>.tmp
```

and replace the final file only after successful completion:

```python
os.replace(temp_path, file_path)
```

On failure or cancellation, remove the temporary file and do not leave a corrupt final workbook.

### 11.8 UI progress

Worker reports progress through the UI queue. It must not call Text widget methods directly.

Progress may include:

- current job;
- rows written;
- current sheet;
- elapsed time.

Do not require a pre-count query, as that may double database cost and alter performance materially.

---

## 12. Engine generations and active connection tracking

The current global set can mix connections from old and new engines. Track the engine generation with each connection.

### Required representation

```python
self._active_db_connections: set[tuple[int, object]]
```

When installing a new engine:

```python
self._engine_generation += 1
generation = self._engine_generation
self.engine = engine
self._track_engine_connections(engine, generation)
```

Listener callbacks add/remove:

```python
(generation, dbapi_connection)
```

Do not clear the global set during listener registration.

### Stop behavior

`stop_running_queries` should normally cancel connections belonging to the current active run, not every historical connection. Ideally record the generation with each run snapshot.

For drivers:

- call `.cancel()` when available;
- do not assume every DBAPI connection supports cancellation;
- keep current fallback message when current query cannot be cancelled.

### Disposal

Store listener function references on an application-side engine registration object. When disposing an old idle engine:

- remove SQLAlchemy listeners with `event.remove`;
- call `engine.dispose()`;
- remove only that generation’s idle entries where safe.

Do not dispose an engine still used by an active worker. Profile switching must either wait for active work, request stop, or leave the old engine alive until the worker finishes.

### Important clarification

The fix is not merely “avoid calling `event.listen` twice.” New engines legitimately need new listeners. The goal is correct lifecycle and isolation between engine generations.

---

## 13. SQL Server ODBC driver detection and connection string

Replace hardcoded `DRIVER={SQL Server}` with installed-driver detection.

### Selection priority

Use `pyodbc.drivers()` and choose in this order:

1. `ODBC Driver 18 for SQL Server`
2. `ODBC Driver 17 for SQL Server`
3. `SQL Server Native Client 11.0`
4. `SQL Server`

Comparison should be case-insensitive while returning the original installed driver name.

If none is available, raise a clear error listing installed drivers.

### Connection options

For Microsoft ODBC Driver 18:

```text
Encrypt=yes
TrustServerCertificate=no
```

should be the secure default for new profiles, but compatibility matters. Add profile options if required:

```python
sqlserver_encrypt = True
sqlserver_trust_server_certificate = False
```

For old profiles without these fields, choose defaults that do not unexpectedly break existing connections. A safe migration approach is:

- preserve old behavior for existing profiles;
- use secure defaults for newly created profiles;
- display the selected driver and encryption mode in connection details or debug logs without logging passwords.

### Construction

Build a standard ODBC connection string and apply `quote_plus` once to the complete string:

```python
conn_str = ";".join(parts)
return "mssql+pyodbc:///?odbc_connect=" + quote_plus(conn_str)
```

Do not log the resulting URL because it contains the password.

### Required tests

- driver 18 preferred over 17;
- driver 17 selected when 18 absent;
- legacy fallback selected only when modern drivers absent;
- no driver raises a useful message;
- semicolons/special characters in password are safely encoded in the final SQLAlchemy URL;
- `database` defaults to `master` as before.

---

## 14. Intentional plain-text password export safeguards

Keep the existing feature. Improve accidental-use protection without changing the affirmative outcome.

When the user chooses to include passwords:

1. show a second explicit warning;
2. require typing exactly `EXPORT PASSWORDS` or checking an explicit confirmation box;
3. default file name should visibly indicate sensitive content, for example:

```text
db_profiles_WITH_PLAINTEXT_PASSWORDS_YYYYMMDD_HHMMSS.json
```

4. include metadata:

```json
{
  "passwords_included": true,
  "password_storage": "plain_text",
  "warning": "Contains database credentials"
}
```

5. do not print passwords to logs or error dialogs.

If the user chooses no passwords, preserve current compatible import behavior that retains an existing password for a same-named profile.

---

## 15. Error handling and logging

### Required rules

- Never log passwords, full SQLAlchemy connection URLs, or ODBC strings containing `PWD`.
- It is acceptable to log entered SQL because current behavior already does so, but preserve awareness that SQL may contain sensitive literals.
- Worker exceptions must be transformed to plain immutable error details before being posted to the UI.
- Never silently swallow validation errors with bare `except:`.
- Replace bare exceptions in modified code with specific exceptions or `except Exception as error` plus visible/logged handling.
- Preserve last known-good state when file validation or sync fails.
- Do not show success after a cancelled or partially failed export.

---

## 16. Implementation sequence

Use this order to minimize regression risk.

### Step 1: Pure helpers and tests

- SQL scanner/classifier;
- query-template validation;
- table-token renderer;
- ODBC driver selector;
- sheet-name allocator.

### Step 2: Main-thread queue and snapshots

- add queue infrastructure;
- refactor all thread workers to avoid Tkinter;
- add immutable connection/job/export snapshots.

### Step 3: Central SQL assessment

- replace calls to old `is_select_query` implementation;
- keep compatibility wrapper;
- update confirmations.

### Step 4: Auto Sync state model

- generation and editor revision;
- immutable parsed table-data snapshot;
- preview-only rendering;
- stale-result rejection.

### Step 5: Engine lifecycle

- engine generation;
- listener bookkeeping;
- correct stop scope;
- safe disposal.

### Step 6: Streaming export

- batch iterator;
- write-only workbook;
- sheet splitting;
- atomic output;
- cancellation and progress.

### Step 7: SQL Server driver detection

- selection logic;
- profile-compatible TLS options;
- sanitized diagnostics.

### Step 8: Password-export guard

- explicit second confirmation;
- sensitive filename and metadata.

---

## 17. Verification commands

Run at minimum:

```bash
python -m py_compile database_connect_gui.py
```

```bash
python -m unittest discover -s tests -p "test_*.py"
```

If pytest is already part of the project, use:

```bash
pytest -q
```

Do not add a new test framework solely for this task if the repository already uses another one.

Also search for remaining thread-unsafe access:

```bash
grep -n "threading.Thread" database_connect_gui.py
```

```bash
grep -n "root.after" database_connect_gui.py
```

Manually inspect every worker target and every `root.after` call. Main-thread scheduled polling is valid; worker-thread Tk calls are not.

Search for blind table-token replacement:

```bash
grep -n "\.replace(old_var\|sql_query\.replace\|TABLE_" database_connect_gui.py
```

Search for old SELECT detection:

```bash
grep -n "startswith(.*SELECT\|startswith(.*WITH\|is_select_query" database_connect_gui.py
```

---

## 18. Manual regression checklist

Test on Windows because the application uses Tkinter, DPAPI, `os.startfile`, pyodbc, and Windows file APIs.

### Profiles

- create, save, load, switch, delete;
- DPAPI password save/load;
- export without passwords;
- export with passwords through explicit confirmation;
- import both formats;
- last-used profile behavior.

### Connections

- PostgreSQL;
- MySQL;
- SQL Server with ODBC Driver 18 or 17;
- Oracle service name;
- failed connection retry;
- switching profile after connection;
- Stop during a long query where driver supports cancellation.

### SQL

- SELECT with leading comments;
- CTE SELECT;
- CTE UPDATE/DELETE;
- INSERT, UPDATE, DELETE, MERGE;
- CREATE/ALTER/DROP/TRUNCATE warning;
- SQL containing semicolons in strings;
- blocked multi-statement SQL;
- Oracle trailing semicolon/slash;
- stored procedure/unknown statement warning.

### Jobs and groups

- run one job;
- duplicate-click prevention;
- selected jobs;
- run all;
- stop batch;
- script groups;
- DML failure stops remaining modifying work as before;
- result popups and Results Grid show the same data.

### Excel parameters and Auto Sync

- canonical tokens;
- legacy tokens;
- values containing apostrophes;
- multiple occurrences;
- missing/ambiguous token error;
- editor template remains intact;
- sync while editing;
- overlapping sync attempts;
- reset one/all parameters.

### Export

- empty result;
- NULL, Decimal, long integers, dates, datetimes, bytes;
- more than 15 numeric digits;
- illegal control characters;
- duplicate/invalid/long job names;
- result larger than one sheet;
- cancel during export;
- failed query creates correct status representation;
- final file is absent or unchanged after fatal failure;
- memory stays bounded during large streamed export.

---

## 19. Performance acceptance criteria

For a streamed export:

- memory usage should be approximately bounded by one fetch batch, workbook write buffers, and up to 1,000 width-sampling rows;
- memory must not grow linearly with total row count;
- use `fetchmany(10_000)` by default;
- check cancellation at least once per batch;
- do not execute a separate count query;
- split automatically before the Excel row limit;
- do not freeze the Tkinter event loop while database/export work runs.

For UI updates:

- drain queued callbacks in bounded intervals, e.g. every 50 ms;
- avoid posting one UI event per exported row;
- aggregate progress by batch.

---

## 20. Definition of done

The task is complete only when all of the following are true:

1. All requested issues are addressed in code, not merely documented.
2. Existing intended password behavior remains available.
3. The editor is no longer silently overwritten by Auto Sync.
4. Worker threads do not access Tkinter objects.
5. Stale Auto Sync results cannot overwrite newer state.
6. Query templates are validated atomically.
7. Table variables use token-aware replacement.
8. Large query exports have a streaming, bounded-memory path.
9. SQL classification handles comments, strings, CTEs, and multi-statements correctly.
10. SQL Server chooses an installed ODBC driver deterministically.
11. Active database connections are isolated by engine/run generation.
12. Regression tests pass.
13. Syntax checks pass.
14. No passwords or connection URLs are added to logs.
15. The final diff contains no unrelated UI redesign or output-format changes.

---

## 21. Final response required from Claude Code

After implementation, report:

1. files changed;
2. concise summary per phase;
3. exact tests and commands run;
4. test results;
5. any behavior intentionally preserved;
6. any unavoidable visible behavior change;
7. remaining risks or database-specific limitations;
8. confirmation that no password values or full connection strings were logged or committed.

Do not claim completion if tests were not run or if key paths remain TODO.
