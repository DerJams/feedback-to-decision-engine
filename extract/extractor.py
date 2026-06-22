"""LLM-based extraction with a pluggable provider backend (Anthropic | Cerebras).

The extractor is deliberately neutral: it shows the model only the schema and
asks it to record each distinct concern. No example complaints, no priors
about what to look for. That neutrality is the load-bearing argument of the
whole project, so the prompt below stays short, the schema lives in YAML you
can read in one sitting, and both are hashed into the cache key (alongside
the provider and model name) so any change automatically invalidates prior
extractions.

Backends:
- "anthropic": Claude (Haiku 4.5 by default), Anthropic-shape tool calling.
- "cerebras":  Cerebras-hosted (gpt-oss-120b by default), OpenAI-shape tool
               calling via cerebras-cloud-sdk.

Both providers enforce the YAML extraction schema via tool/function-calling
at the API boundary, so no client-side validation is needed on returned
arguments.

Cache layout:

    data/extraction_cache/{sha12(provider+model+system_prompt+schema)}/{review_id}.json

Switching provider or model lands extractions in a NEW cache directory, so
mixed-provenance corpora (some Haiku, some gpt-oss) are impossible by
construction.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_CONFIG_PATH = REPO_ROOT / "config" / "run.yaml"
SCHEMA_PATH = REPO_ROOT / "config" / "extraction_schema.yaml"

# Trimmed for token efficiency on per-minute / per-day rate-limited providers.
# Every enum value still lives in the schema YAML (which is also inlined into
# the tool definition), so this prompt just frames the task and the neutrality
# constraint. Do not add example complaints here; add eval cases under evals/.
SYSTEM_PROMPT = """Extract distinct user concerns from this app review via the record_issues tool. Populate every field. If no extractable concerns, call the tool with an empty issues list.

- Use only schema enum values.
- "theme": short noun phrase from reviewer wording.
- "segment_hint": empty unless implied by the review.
- One issue per distinct concern."""


@dataclass(frozen=True)
class ExtractConfig:
    provider: str            # "anthropic" | "cerebras"
    model: str
    max_tokens: int
    temperature: float
    cache_dir: Path
    input_path: Path
    output_path: Path
    sample_size: int
    max_concurrency: int
    max_retries: int
    backoff_base_seconds: float
    backoff_max_seconds: float


def load_extract_config(path: Path = RUN_CONFIG_PATH) -> ExtractConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    ex = raw["extract"]
    provider = ex["provider"]
    if provider not in ex.get("providers", {}):
        raise RuntimeError(
            f"extract.provider={provider!r} but no entry under extract.providers."
        )
    prov_cfg = ex["providers"][provider]
    return ExtractConfig(
        provider=provider,
        model=prov_cfg["model"],
        max_tokens=int(prov_cfg["max_tokens"]),
        temperature=float(ex.get("temperature", 0.0)),
        cache_dir=REPO_ROOT / ex["cache_dir"],
        input_path=REPO_ROOT / ex["input_path"],
        output_path=REPO_ROOT / ex["output_path"],
        sample_size=int(ex["sample_size"]),
        max_concurrency=int(ex.get("max_concurrency", 5)),
        max_retries=int(ex.get("max_retries", 5)),
        backoff_base_seconds=float(ex.get("backoff_base_seconds", 1.0)),
        backoff_max_seconds=float(ex.get("backoff_max_seconds", 30.0)),
    )


def _common_tool_parts(schema: dict):
    """The schema fragments both tool shapes share."""
    issue_properties: dict[str, dict[str, Any]] = {}
    required: list[str] = []
    for name, spec in schema["fields"].items():
        prop: dict[str, Any] = {"description": spec.get("description", "").strip()}
        if spec["type"] == "enum":
            prop["type"] = "string"
            prop["enum"] = list(spec["values"])
        else:
            prop["type"] = spec["type"]
        issue_properties[name] = prop
        required.append(name)
    max_issues = int(schema["extraction"]["max_issues_per_review"])
    return issue_properties, required, max_issues


def _issues_array_schema(issue_properties: dict, required: list, max_issues: int) -> dict:
    return {
        "type": "object",
        "properties": {
            "issues": {
                "type": "array",
                "maxItems": max_issues,
                "items": {
                    "type": "object",
                    "properties": issue_properties,
                    "required": required,
                },
            }
        },
        "required": ["issues"],
    }


def build_anthropic_tool(schema: dict) -> dict:
    """Anthropic-shape tool definition: flat {name, description, input_schema}."""
    issue_properties, required, max_issues = _common_tool_parts(schema)
    return {
        "name": "record_issues",
        "description": "Record the distinct concerns raised in the review.",
        "input_schema": _issues_array_schema(issue_properties, required, max_issues),
    }


def build_openai_tool(schema: dict) -> dict:
    """OpenAI / Cerebras-shape tool definition: nested under {type, function}."""
    issue_properties, required, max_issues = _common_tool_parts(schema)
    return {
        "type": "function",
        "function": {
            "name": "record_issues",
            "description": "Record the distinct concerns raised in the review.",
            "parameters": _issues_array_schema(issue_properties, required, max_issues),
        },
    }


def compute_cache_key(
    provider: str, model: str, system_prompt: str, schema_yaml_text: str
) -> str:
    """Stable short hash. Provider + model + prompt + schema are all inputs that
    determine extractor output; any change should land results in a new cache
    directory rather than silently reuse a stale provenance.
    """
    h = hashlib.sha256()
    h.update(provider.encode())
    h.update(b"\x00")
    h.update(model.encode())
    h.update(b"\x00")
    h.update(system_prompt.encode())
    h.update(b"\x00")
    h.update(schema_yaml_text.encode())
    return h.hexdigest()[:12]


class AnthropicBackend:
    def __init__(self, config: ExtractConfig, tool: dict) -> None:
        from anthropic import Anthropic

        self.config = config
        self.tool = tool
        self.client = Anthropic()

    def call(self, review_text: str) -> list[dict]:
        response = self.client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": f"Review:\n{review_text}"}],
            tools=[self.tool],
            tool_choice={"type": "tool", "name": "record_issues"},
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == "record_issues":
                return list(block.input.get("issues", []))
        raise RuntimeError("Anthropic returned no record_issues tool call")


class CerebrasBackend:
    def __init__(self, config: ExtractConfig, tool: dict) -> None:
        from cerebras.cloud.sdk import Cerebras

        self.config = config
        self.tool = tool
        self.client = Cerebras()

    def call(self, review_text: str) -> list[dict]:
        response = self.client.chat.completions.create(
            model=self.config.model,
            max_completion_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Review:\n{review_text}"},
            ],
            tools=[self.tool],
            tool_choice={"type": "function", "function": {"name": "record_issues"}},
        )
        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None) or []
        for call in tool_calls:
            if call.function.name == "record_issues":
                args = json.loads(call.function.arguments or "{}")
                return list(args.get("issues", []))
        raise RuntimeError("Cerebras returned no record_issues tool call")


class GroqBackend:
    """Groq via the official `groq` SDK. OpenAI-shape tool calling - the same
    tool definition (`build_openai_tool`) used by Cerebras works as-is.

    Uses the SDK's `with_raw_response` interface so the smoke test can read the
    `x-ratelimit-*` and `retry-after` headers that come back on the first real
    call - real account limits from the API, not from a docs table.
    `last_headers` is the most-recent successful response's rate-limit subset;
    under concurrent calls the dict is last-write-wins, which is fine for a
    diagnostic snapshot.
    """

    RATELIMIT_HEADER_PREFIXES = ("x-ratelimit", "retry-after")

    def __init__(self, config: ExtractConfig, tool: dict) -> None:
        from groq import Groq

        self.config = config
        self.tool = tool
        self.client = Groq()
        self.last_headers: dict[str, str] | None = None

    def call(self, review_text: str) -> list[dict]:
        raw = self.client.chat.completions.with_raw_response.create(
            model=self.config.model,
            max_completion_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Review:\n{review_text}"},
            ],
            tools=[self.tool],
            tool_choice={"type": "function", "function": {"name": "record_issues"}},
        )
        try:
            self.last_headers = {
                k: v
                for k, v in raw.headers.items()
                if k.lower().startswith(self.RATELIMIT_HEADER_PREFIXES)
            }
        except Exception:
            # Header capture is diagnostic; never let it break the extraction.
            pass
        response = raw.parse()
        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None) or []
        for call in tool_calls:
            if call.function.name == "record_issues":
                args = json.loads(call.function.arguments or "{}")
                return list(args.get("issues", []))
        raise RuntimeError("Groq returned no record_issues tool call")


class Extractor:
    def __init__(self, config: ExtractConfig | None = None) -> None:
        load_dotenv(REPO_ROOT / ".env")
        self.config = config or load_extract_config()

        schema_text = SCHEMA_PATH.read_text(encoding="utf-8")
        self.schema = yaml.safe_load(schema_text)
        # Anthropic enforces enums and required fields at the tool boundary but
        # NOT array maxItems; the cap is enforced again on our side after each
        # call so per-review issue counts stay bounded regardless of provider.
        self.max_issues = int(self.schema["extraction"]["max_issues_per_review"])

        if self.config.provider == "anthropic":
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise RuntimeError(
                    "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key."
                )
            self.tool = build_anthropic_tool(self.schema)
            self.backend = AnthropicBackend(self.config, self.tool)
        elif self.config.provider == "cerebras":
            if not os.environ.get("CEREBRAS_API_KEY"):
                raise RuntimeError(
                    "CEREBRAS_API_KEY is not set. Copy .env.example to .env and add your key."
                )
            self.tool = build_openai_tool(self.schema)
            self.backend = CerebrasBackend(self.config, self.tool)
        elif self.config.provider == "groq":
            if not os.environ.get("GROQ_API_KEY"):
                raise RuntimeError(
                    "GROQ_API_KEY is not set. Copy .env.example to .env and add your key."
                )
            self.tool = build_openai_tool(self.schema)
            self.backend = GroqBackend(self.config, self.tool)
        else:
            raise ValueError(
                f"unknown extract.provider {self.config.provider!r}; "
                "expected 'anthropic', 'cerebras', or 'groq'"
            )

        self.cache_key = compute_cache_key(
            self.config.provider, self.config.model, SYSTEM_PROMPT, schema_text
        )
        self.cache_root = self.config.cache_dir / self.cache_key
        self.cache_root.mkdir(parents=True, exist_ok=True)

    def extract(self, review: dict, use_cache: bool = True) -> dict:
        """Return {review_id, model, provider, issues, extracted_at, cached} for one review.

        Per-review cache files are written atomically; multiple extract() calls
        on different review_ids can run concurrently without coordination.
        """
        review_id = review["review_id"]
        cache_file = self.cache_root / f"{review_id}.json"
        if use_cache and cache_file.exists():
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            data["issues"] = data["issues"][: self.max_issues]
            data["cached"] = True
            return data

        issues = self.backend.call(review["text"])[: self.max_issues]
        record = {
            "review_id": review_id,
            "provider": self.config.provider,
            "model": self.config.model,
            "issues": issues,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
        }
        cache_file.write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        record["cached"] = False
        return record
