# Windows Sender Run Guide

> Legacy fallback / compatibility path
>
> This guide is **not** part of the default backend deployment path. The repository’s default deployment already focuses on backend services and the future primary sending direction is backend -> WeCom app messaging.
>
> Use this guide only when you need one of the following:
> - fallback / rollback drills
> - compatibility with the existing sender-oriented API flow
> - local WeChat automation validation on a Windows machine
>
> Current status note: the `sender-agent` code path below is still runnable and supported as a fallback path. It has not been removed. This document only changes its positioning, not its runtime behavior.

## 1. Current status

The current `sender-agent` implementation is runnable in code and has verified unit/integration coverage for:

- heartbeat request/response flow
- pending task polling against the backend API contract
- task result callback
- pending result replay after callback failure
- degraded behavior for `logged_out` and window-not-found states
- Windows UI Automation adapter fallback behavior when `uiautomation` is unavailable

Validated by test suite:

```bash
pytest tests/unit/sender_agent tests/integration/test_collection_pipeline.py
```

## 2. Environment requirements

### OS
- Windows 10/11
- interactive desktop session required
- WeChat desktop must run in the same logged-in user session as `sender-agent`

### Python
- Python 3.12+

### Project dependencies
Install from repository root:

```bash
pip install -e .[dev]
```

On Windows this pulls in `uiautomation` from [pyproject.toml](pyproject.toml).

### Network
The sender machine must be able to reach the backend API base URL configured by `SENDER_API_BASE_URL`.

## 3. Required configuration

Copy values from [.env.example](.env.example) into a local `.env` file and set at least:

- `SENDER_API_BASE_URL`
- `SENDER_TOKEN`
- `SENDER_ID`

Common sender settings:

- `SENDER_HEARTBEAT_INTERVAL_SEC`
- `SENDER_POLL_INTERVAL_SEC`
- `SENDER_REQUEST_TIMEOUT_SEC`
- `SENDER_TASK_LIMIT`
- `WECHAT_WINDOW_TITLE_HINT`
- `WECHAT_SEND_DELAY_MS`
- `WECHAT_CHAT_SEARCH_TIMEOUT_SEC`

Optional local-state overrides:

- `SENDER_LOCAL_STATE_DIR`
- `SENDER_LOG_FILE`
- `SENDER_JOURNAL_PATH`

If omitted, local artifacts default under:

- `~/.finance-news-bot-sender/`

Important contract note:

- `SENDER_API_BASE_URL` points to the backend API base URL.
- It is part of the legacy sender-agent fallback contract, **not** a WeCom endpoint.

## 4. WeChat client preparation

Before startup:

1. Install and open WeChat desktop on Windows.
2. Log in manually.
3. Keep the desktop session unlocked.
4. Ensure the target contact exists with the expected **remark name**.
5. Prefer a dedicated test contact or 文件传输助手 for first validation.

Important boundaries:

- `sender-agent` does **not** require your account password.
- It reuses the already logged-in local WeChat session.
- It does **not** perform automatic login, password entry, or QR bypass.
- If WeChat logs out, recovery is manual.

## 5. Start command

From repository root:

```bash
sender-agent
```

Or equivalently:

```bash
python -m sender_agent
```

Entrypoint is [src/sender_agent/__main__.py](src/sender_agent/__main__.py).

## 6. Expected runtime behavior

Main loop in [src/sender_agent/agent.py](src/sender_agent/agent.py):

1. Start heartbeat thread.
2. Replay any locally recorded `result_pending` task results.
3. Check WeChat login/window status.
4. If WeChat is ready, poll `/api/sender/tasks/pending`.
5. Execute one task at a time.
6. Record result locally.
7. Callback `/api/sender/tasks/{task_id}/result`.

This remains useful when validating the fallback path or when temporarily rolling back from the future WeCom primary path.

## 7. Real-machine validation checklist

### A. Heartbeat
- Start backend
- Start `sender-agent`
- Confirm `/api/sender/heartbeat` is called successfully
- Confirm sender status becomes `online` or `degraded`

### B. Pending task fetch
- Insert or create one dispatch task through backend flow
- Confirm sender fetches `/api/sender/tasks/pending`
- Confirm only one task is processed at a time

### C. Real WeChat send
- Use a test contact remark name
- Send a task with 2-3 chunks
- Confirm:
  - contact search succeeds
  - chat opens
  - chunks are sent in order
  - backend receives `sent` result

### D. Replay verification
- Simulate backend callback failure after local send success
- Restart sender or let next loop continue
- Confirm sender replays `/result` without re-sending WeChat content

### E. Degraded-state verification
- Close WeChat window or log out
- Confirm sender reports degraded status/events
- Confirm task polling pauses
- Manually restore WeChat
- Confirm sender resumes automatically

## 8. Common errors and recovery

### `uiautomation dependency is not installed`
Cause:
- Windows UIA dependency missing

Recovery:
```bash
pip install -e .[dev]
```
Or install `uiautomation` directly.

### `WeChat desktop window was not found`
Cause:
- WeChat not open
- title hint mismatch
- running in non-interactive session

Recovery:
- open WeChat desktop
- keep session unlocked
- verify `WECHAT_WINDOW_TITLE_HINT`

### `WeChat is not logged in; please re-login manually`
Cause:
- local session expired or signed out

Recovery:
- log in manually in WeChat
- keep sender process running; it should recover on next loop

### `WeChat chat with remark name '...' was not found`
Cause:
- backend `target_user` does not match WeChat remark name

Recovery:
- correct the contact remark
- correct backend target value

### result callback failure / network failure
Cause:
- backend unavailable or network issue

Recovery:
- sender keeps the result in local journal
- after network recovery it replays callback without re-sending the message

## 9. What is validated vs not yet validated

### Validated in code/tests
- sender startup path
- heartbeat payload flow
- pending-task fetch flow
- result callback flow
- replay on callback failure
- logged-out / window-not-found branch handling
- duplicate unavailable-event suppression
- UIA unavailable fallback
- basic UIA window/search/editor/send control logic via test doubles

### Still needs real Windows + real WeChat confirmation
- exact control tree compatibility with installed WeChat version
- actual chat search stability by remark name
- actual multi-chunk sending reliability
- clipboard/paste behavior under real desktop focus contention
- recovery behavior after real login expiration

## 10. Suggested evidence to capture during real validation

- sender log file
- backend API logs for heartbeat/fetch/result/events
- screenshot or screen recording of one successful send cycle
- one failure/recovery example for logged-out or window-missing state
