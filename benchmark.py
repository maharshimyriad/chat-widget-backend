import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx

ENVIRONMENTS = ("dam", "eponymos", "media_center")
METRICS = ("time_to_first_event_ms", "time_to_first_text_ms", "total_time_ms")


def percentile(values: list[float], percentage: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentage / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction, 1)


def consume_sse_block(
    event_name: str,
    data_lines: list[str],
    started: float,
    result: dict[str, Any],
) -> None:
    if not data_lines:
        return

    now = perf_counter()
    result["event_count"] += 1
    if result["time_to_first_event_ms"] is None:
        result["time_to_first_event_ms"] = round((now - started) * 1000, 1)

    raw_data = "\n".join(data_lines)
    try:
        payload = json.loads(raw_data)
    except json.JSONDecodeError:
        payload = raw_data

    if event_name == "session" and isinstance(payload, dict):
        result["session_id"] = payload.get("session_id")
        result["event_types"].add("session")
    elif event_name == "error":
        result["error"] = payload.get("message", "Stream returned an error") if isinstance(payload, dict) else str(payload)
        result["event_types"].add("error")
    elif event_name == "message" and isinstance(payload, dict) and payload.get("text"):
        result["event_types"].add("text")
        if result["time_to_first_text_ms"] is None:
            result["time_to_first_text_ms"] = round((now - started) * 1000, 1)
    elif event_name == "done":
        result["event_types"].add("done")


async def measure_prompt(
    client: httpx.AsyncClient,
    base_url: str,
    user_id: str,
    environment: str,
    prompt_index: int,
    prompt: str,
    session_id: str | None,
) -> dict[str, Any]:
    started = perf_counter()
    result: dict[str, Any] = {
        "environment": environment,
        "prompt_index": prompt_index,
        "prompt": prompt,
        "request_id": None,
        "session_id": session_id,
        "status_code": None,
        "time_to_first_event_ms": None,
        "time_to_first_text_ms": None,
        "total_time_ms": None,
        "event_count": 0,
        "event_types": set(),
        "error": None,
    }

    try:
        async with client.stream(
            "POST",
            f"{base_url}/chat",
            json={
                "user_id": user_id,
                "environment_id": environment,
                "message": prompt,
                "session_id": session_id,
            },
            headers={"Accept": "text/event-stream"},
        ) as response:
            result["request_id"] = response.headers.get("x-request-id")
            result["status_code"] = response.status_code
            if response.status_code >= 400:
                result["error"] = (await response.aread()).decode("utf-8", errors="replace")
            else:
                event_name = "message"
                data_lines: list[str] = []
                async for line in response.aiter_lines():
                    if line.startswith("event:"):
                        event_name = line[6:].strip()
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].lstrip())
                    elif not line:
                        consume_sse_block(event_name, data_lines, started, result)
                        event_name = "message"
                        data_lines = []
                consume_sse_block(event_name, data_lines, started, result)
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
    finally:
        result["total_time_ms"] = round((perf_counter() - started) * 1000, 1)
        result["event_types"] = sorted(result["event_types"])

    return result


def make_summary(results: list[dict[str, Any]], run_id: str) -> dict[str, Any]:
    environments = {}
    for environment in ENVIRONMENTS:
        rows = [
            row for row in results
            if row["environment"] == environment and not row["error"]
        ]
        metrics = {}
        for metric in METRICS:
            values = [row[metric] for row in rows if row[metric] is not None]
            metrics[metric] = {
                "p50": percentile(values, 50),
                "p95": percentile(values, 95),
            }
        environments[environment] = {
            "successful_requests": len(rows),
            "total_requests": sum(row["environment"] == environment for row in results),
            "metrics_ms": metrics,
        }
    return {"record_type": "summary", "run_id": run_id, "environments": environments}


async def run_benchmark(args: argparse.Namespace) -> None:
    prompt_path = Path(args.prompts_file)
    if not prompt_path.is_absolute():
        prompt_path = Path(__file__).resolve().parent / prompt_path
    prompt_data = json.loads(prompt_path.read_text(encoding="utf-8"))
    prompts = prompt_data.get("prompts")
    if not isinstance(prompts, list) or not 20 <= len(prompts) <= 30:
        raise ValueError("The prompt file must contain between 20 and 30 prompts.")
    if any(not isinstance(prompt, str) or not prompt.strip() for prompt in prompts):
        raise ValueError("Every benchmark prompt must be a non-empty string.")

    run_id = args.run_id or uuid.uuid4().hex[:12]
    base_url = args.base_url.rstrip("/")
    results: list[dict[str, Any]] = []
    output = open(args.output, "w", encoding="utf-8") if args.output else None

    def emit(record: dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False)
        print(line, flush=True)
        if output:
            output.write(line + "\n")
            output.flush()

    timeout = httpx.Timeout(args.timeout_seconds)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            for environment in ENVIRONMENTS:
                user_id = f"{args.user_id}-{run_id}-{environment}"
                session_id = None
                for index, prompt in enumerate(prompts, start=1):
                    result = await measure_prompt(
                        client,
                        base_url,
                        user_id,
                        environment,
                        index,
                        prompt,
                        session_id,
                    )
                    session_id = result.get("session_id") or session_id
                    result["run_id"] = run_id
                    results.append(result)
                    emit({"record_type": "request", **result})
    finally:
        if output:
            output.close()

    summary = make_summary(results, run_id)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    if args.output:
        with open(args.output, "a", encoding="utf-8") as output_file:
            output_file.write(json.dumps(summary, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the same 20-30 SSE latency prompts in each environment."
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("CHAT_API_URL", "http://127.0.0.1:8000"),
        help="Chat API base URL.",
    )
    parser.add_argument("--user-id", default="latency-benchmark")
    parser.add_argument(
        "--prompts-file",
        default="benchmark_prompts.json",
        help="JSON file containing a prompts array with 20-30 entries.",
    )
    parser.add_argument("--run-id", help="Optional label; use a fresh value for each run.")
    parser.add_argument("--output", help="Optional JSONL output file for request rows and summary.")
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    return parser.parse_args()


if __name__ == "__main__":
    try:
        asyncio.run(run_benchmark(parse_args()))
    except (OSError, ValueError, httpx.HTTPError) as error:
        print(f"Benchmark failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
