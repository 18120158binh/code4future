# Known Issues & Lessons Learned

A log of issues encountered during development and setup, with root causes and fixes.
Use this as a reference to avoid repeating mistakes.

---

## 1. Python Version Mismatch

| Field | Detail |
|:------|:-------|
| **Symptom** | `pip install` fails with version incompatibility |
| **Root Cause** | `pyproject.toml` specified `requires-python = ">=3.11"` but the local machine has Python 3.10 (miniconda) |
| **Fix** | Changed to `requires-python = ">=3.10"`. The code is compatible because all 3.11+ type hints (`X | None`) are guarded by `from __future__ import annotations` |
| **Lesson** | Always check the local Python version before setting the minimum. Use `from __future__ import annotations` to backport type hints to 3.10 |

---

## 2. dbt-artifacts-parser Version Does Not Exist

| Field | Detail |
|:------|:-------|
| **Symptom** | `ERROR: No matching distribution found for dbt-artifacts-parser>=1.0.0` |
| **Root Cause** | The latest version on PyPI is `0.13.1`, not `1.0.0`. The version was assumed without checking PyPI |
| **Fix** | Changed to `dbt-artifacts-parser>=0.6.0` |
| **Lesson** | Always verify package versions on PyPI before adding them to `pyproject.toml`. Don't assume semver progression |

---

## 3. Neo4j Docker Container Keeps Dying (Exit Code 0)

| Field | Detail |
|:------|:-------|
| **Symptom** | Neo4j container starts (`Started.`), then shuts down after ~2-17 seconds with `Neo4j Server shutdown initiated by request`. Exit code 0 (graceful) |
| **Root Cause** | The `docker-compose.yml` had `restart: unless-stopped` combined with a `healthcheck` that uses `cypher-shell`. On the first run, the healthcheck may fail during initial setup, causing Docker to restart the container. Each restart cycle resets the password and re-installs plugins, creating an unstable loop. Additionally, stale Docker volumes from previous failed runs compounded the issue |
| **Fix** | 1. Run Neo4j in **foreground mode** (`docker run` without `-d`) to prevent the restart policy from interfering. 2. Use `docker rm -f` and `docker volume rm` to clean up stale state before recreating. 3. Simplify `docker-compose.yml` by removing the healthcheck and reducing restart policy |
| **Lesson** | For development environments, avoid healthchecks + restart policies together — they can create restart loops. Use foreground mode for debugging. Always `docker volume rm` when changing auth settings |

---

## 4. WSL2 Port Forwarding Inconsistency

| Field | Detail |
|:------|:-------|
| **Symptom** | `docker inspect` (inside WSL) shows container as `running`, but Python (on Windows) gets `WinError 10061: connection refused` on `localhost:7687` |
| **Root Cause** | WSL2 port forwarding from Linux→Windows is not instant. When the container is freshly started, ports may take a few seconds to become accessible from the Windows host. Also, if the container dies and restarts quickly, the port mapping is briefly interrupted |
| **Fix** | Wait 15+ seconds after container start before connecting from Windows Python. The foreground mode also stabilized this |
| **Lesson** | When running Docker via WSL2, always add a startup delay before testing connectivity from the Windows side. Don't trust `docker inspect` from WSL as proof that Windows can reach the port |

---

## 5. Unicode Emoji Crash on Windows Terminal (CP1252)

| Field | Detail |
|:------|:-------|
| **Symptom** | `UnicodeEncodeError: 'charmap' codec can't encode character '\U0001f4c2'` when Rich library tries to print emoji like 📂, 🚀, ✓ to the Windows console |
| **Root Cause** | Windows PowerShell uses CP1252 encoding by default, which cannot represent emoji characters. The Rich library attempts to write them directly to the console |
| **Fix** | Replaced all emoji in `scripts/ingest.py` with ASCII-safe Rich markup: `📂` → `[bold]Docs path:[/bold]`, `✓` → `>` |
| **Lesson** | Never use raw emoji in CLI output on Windows. Use Rich's markup system (`[green]>[/green]`) or ASCII symbols instead. Alternatively, set `PYTHONIOENCODING=utf-8` or use `Console(force_terminal=True)` |

---

## 6. Google Embedding Model Name Changed

| Field | Detail |
|:------|:-------|
| **Symptom** | `404 NOT_FOUND: models/text-embedding-004 is not found for API version v1beta` |
| **Root Cause** | Google renamed their embedding models. The old `text-embedding-004` no longer exists. Available models are now `gemini-embedding-001`, `gemini-embedding-2-preview`, `gemini-embedding-2` |
| **Fix** | Changed `.env` from `GOOGLE_EMBED_MODEL=models/text-embedding-004` to `GOOGLE_EMBED_MODEL=models/gemini-embedding-001` |
| **Discovery** | Used `client.models.list()` to enumerate available models |
| **Lesson** | Google's model naming is unstable. Always enumerate available models with `ListModels` API before hardcoding. Pin model names in `.env` not in code |

---

## 7. Google Free Tier Embedding Rate Limit (429)

| Field | Detail |
|:------|:-------|
| **Symptom** | `429 RESOURCE_EXHAUSTED: You exceeded your current quota... limit: 100, model: gemini-embedding-1.0` |
| **Root Cause** | Google's free tier allows 100 embed requests per minute per model. `langchain`'s `aembed_documents([texts])` sends one API call per text internally, so embedding 272 texts blew through the quota instantly |
| **Fix** | Added **batched embedding** with rate limiting in `src/ingestion/enricher.py`: batch size = 20 texts, 15s pause between batches, plus retry-on-429 with exponential backoff. Total ingestion time: ~4 minutes (acceptable for a one-time operation) |
| **Lesson** | Free-tier APIs always have rate limits. Never send all items in a single batch — always chunk and add delay. Also, `langchain`'s `aembed_documents()` does NOT batch internally; each text = 1 API call |

---

## 8. Neo4j Deprecated Config Properties (5.21)

| Field | Detail |
|:------|:-------|
| **Symptom** | `WARN: Use of deprecated setting 'dbms.memory.heap.max_size'. It is replaced by 'server.memory.heap.max_size'` |
| **Root Cause** | Neo4j 5.x renamed `dbms.memory.*` to `server.memory.*`. The docker-compose env vars used the old naming |
| **Fix** | Changed `NEO4J_dbms_memory_heap_*` → `NEO4J_server_memory_heap_*` in `docker-compose.yml` |
| **Lesson** | Check release notes when pinning a specific Neo4j version. The `dbms.*` namespace was deprecated in Neo4j 5.0 |

---

## 9. Test Case Difficulty Misclassification

| Field | Detail |
|:------|:-------|
| **Symptom** | `test_hard_cases_have_joins_or_ctes` assertion failed for `hard_04`, `hard_06`, `hard_07` — these "hard" test cases had no JOINs, CTEs, or subqueries |
| **Root Cause** | Test case difficulty was assigned based on **business complexity** (e.g., "conversion rate calculation", "user journey analysis") rather than **SQL structural complexity**. A query can be analytically insightful but syntactically simple (single-table GROUP BY) |
| **Fix** | 1. Reclassified `hard_06` and `hard_07` to "medium" since they're single-table GROUP BY queries. 2. Added `HAVING`, `NULLIF`, `CASE WHEN`, and multi-table markers as valid "hard" complexity indicators (for `hard_04` which uses `NULLIF` + `HAVING`) |
| **Lesson** | When classifying SQL difficulty, use SQL structural complexity (JOINs, CTEs, window functions, subqueries), NOT business domain complexity. A simple `GROUP BY` is medium even if the business question sounds hard |

---

## 10. Asyncio SSL Transport Exception on Windows

| Field | Detail |
|:------|:-------|
| **Symptom** | Python exits with `Fatal error on SSL transport` and `RuntimeError: Event loop is closed`, specifically tracing to `_ProactorSocketTransport` when making HTTPS calls to LangChain/Google APIs. |
| **Root Cause** | On Windows, `asyncio` uses `ProactorEventLoop` by default. When the event loop is closed quickly after network calls (like SSL), it doesn't gracefully clean up pending SSL writes. This is a known Python issue on Windows rather than an application-level bug. |
| **Fix** | Safely ignored as it only occurs on exit. No functional impact. A potential fix is properly calling `await asyncio.sleep(0.1)` before `sys.exit()` or silencing `asyncio` internals. |
| **Lesson** | Distinguish between application business logic crashes and Python event loop tearing down warnings. |

---

## 11. Google API Free Tier Daily Quota Run-out

| Field | Detail |
|:------|:-------|
| **Symptom** | `429 RESOURCE_EXHAUSTED` with message `Quota exceeded for metric: generativelanguage.googleapis.com... limit: 0` despite being well under the per-minute limit. |
| **Root Cause** | The free tier for `gemini-2.0-flash` has a remarkably low *daily* request limit. If you use it heavily for a project, you'll hit a hard stop (the metric shows limit "0" which typically points to daily quota instead of RPM). |
| **Fix** | Temporarily switched the model inside `.env` to `gemini-2.5-flash` or `gemini-1.5-flash`, which had remaining quota and is highly capable for this task. |
| **Lesson** | Google Gemini’s free tier quotas differ wildly across model names and sizes. When one hits a daily cap, fallback to another model version if you don't want to add a billing account. |

---

## Template for Future Issues

```markdown
## N. Issue Title

| Field | Detail |
|:------|:-------|
| **Symptom** | What you saw |
| **Root Cause** | Why it happened |
| **Fix** | What fixed it |
| **Lesson** | What to remember next time |
```
