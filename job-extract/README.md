# job-extract

A work sample for the job that carries a premium right now: **scraping + an LLM,
done so the output is trustworthy.** Messy job-posting HTML in, a *validated*
typed record out.

Anyone can pipe a page into a model and hope. The value is the parts that make it
reliable:

| Concern | Where | Tested |
|---|---|---|
| Strict schema — unknown fields rejected, salaries non-negative, skills deduped, currency normalised | `models.py` (`JobPosting`) | `test_extract_happy_path`, `test_extract_rejects_unknown_fields` |
| Tolerant JSON parsing — strips ` ```json `, pulls the object out of prose | `parse_llm_json` | 5 `test_parse_*` |
| Re-prompt loop — the exact parse / validation error is fed back to the model, up to a retry budget | `extract` | `test_extract_retries_then_succeeds`, `test_extract_feeds_validation_error_back` |
| Fail loud when the budget runs out | `ExtractionError` | `test_extract_gives_up_after_budget` |
| The LLM is an injected dependency, so none of this needs a network or a key | `llm.py` (`LLM` protocol, `StubLLM`) | whole suite |
| Boilerplate stripping before the model sees the page (saves tokens) | `pipeline.clean_text` | `test_clean_text_drops_boilerplate_and_keeps_content` |

## Run the tests

```bash
python -m venv .venv && . .venv/Scripts/activate      # .venv/bin/activate on mac/linux
pip install -r requirements.txt
pytest -q          # 15 tests, no network, no API key
```

## Run it for real

```bash
pip install langchain-google-genai
export GOOGLE_API_KEY=...
python -m job_extract https://example.com/some-job-posting
python -m job_extract tests/fixtures/posting_a.html
```

Output is `JobPosting` as JSON: title, company, location, `remote`, employment
type, seniority, a `{min,max,currency,period}` salary, a deduped skills list,
posted date, apply URL, and a short summary.

## Design

- **`StubLLM`** takes a string, a list (one reply per call, to script a
  retry), or a `prompt -> str` callable. That's the whole reason the retry loop
  is testable without mocks.
- **`GeminiLLM`** is a lazy import — the package installs and imports with no
  `langchain-google-genai` and no key. Swapping in OpenAI/Anthropic/Bedrock is
  one small class.
- **`clean_text`** is pure and runs before the model, so a 200 KB page becomes a
  few KB of prompt.

## Real client version

Same core, plus: your target boards (with their pagination), your fields, output
to your ATS / a database / a sheet, a scheduled crawl, cost + token metrics per
run, and a confidence flag on low-signal postings.
