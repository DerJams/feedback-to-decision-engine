"""LLM-based extraction of structured issues from individual reviews.

The extractor is deliberately neutral: it shows the model only the schema
(theme, severity, sentiment, feature_area, segment_hint) and asks it to record
each distinct concern. No example complaints, no priors about what to look for.
That neutrality is the load-bearing argument of the whole project, so the
prompt below stays short, the schema lives in YAML you can read in one sitting,
and both are hashed into the cache key so any change automatically invalidates
prior extractions.

Backend: Cerebras-hosted gpt-oss-120b via OpenAI-shape function calling. The
schema is enforced at the API boundary, which means we don't need a separate
JSON-validation step on the returned arguments.

Results are cached on disk so downstream scoring iteration doesn't re-spend
API calls. Cache layout:

    data/extraction_cache/{model+prompt+schema sha[:12]}/{review_id}.json
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
from cerebras.cloud.sdk import Cerebras
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_CONFIG_PATH = REPO_ROOT / "config" / "run.yaml"
SCHEMA_PATH = REPO_ROOT / "config" / "extraction_schema.yaml"

# Kept short on purpose. The schema descriptions (loaded from YAML and threaded
# into the tool definition) carry the field-level guidance; this prompt only
# frames the task and the neutrality constraint. If you find yourself wanting
# to add "watch for X" here, add it to evals/ instead.
SYSTEM_PROMPT = """You extract structured user feedback from a single app review.

Use the record_issues tool to record each distinct concern the reviewer raises. Populate every field in each issue. If the review raises no extractable concerns, call the tool with an empty issues list.

Rules:
- Use only the enum values defined in the schema. Do not invent categories.
- The "theme" field is a short noun phrase grounded in the reviewer's framing. Do not add product knowledge the reviewer did not express.
- "segment_hint" is empty unless the review itself implies a user segment.
- Be conservative: only record a separate issue if the reviewer raises a separate concern."""


@dataclass(frozen=True)
class ExtractConfig:
    model: str
    max_completion_tokens: int
    temperature: float
    cache_dir: Path
    input_path: Path
    output_path: Path
    sample_size: int


def load_extract_config(path: Path = RUN_CONFIG_PATH) -> ExtractConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    ex = raw["extract"]
    return ExtractConfig(
        model=ex["model"],
        max_completion_tokens=int(ex["max_completion_tokens"]),
        temperature=float(ex["temperature"]),
        cache_dir=REPO_ROOT / ex["cache_dir"],
        input_path=REPO_ROOT / ex["input_path"],
        output_path=REPO_ROOT / ex["output_path"],
        sample_size=int(ex["sample_size"]),
    )


def build_tool_definition(schema: dict) -> dict:
    """Translate the YAML extraction schema into an OpenAI-shape tool definition.

    Going through tool calling means the API enforces enum constraints for us:
    the model cannot return "kinda-medium" for severity. That removes a whole
    class of validation code we'd otherwise have to write and lets schema
    changes propagate by editing one YAML file.
    """
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
    return {
        "type": "function",
        "function": {
            "name": "record_issues",
            "description": "Record the distinct concerns raised in the review.",
            "parameters": {
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
            },
        },
    }


def compute_cache_key(model: str, system_prompt: str, schema_yaml_text: str) -> str:
    """Short stable hash of the inputs that determine extractor output.

    Changing the model, the prompt, or the schema YAML automatically lands
    extractions in a new cache directory, so the user is never silently served
    stale results from a previous prompt version.
    """
    h = hashlib.sha256()
    h.update(model.encode())
    h.update(b"\x00")
    h.update(system_prompt.encode())
    h.update(b"\x00")
    h.update(schema_yaml_text.encode())
    return h.hexdigest()[:12]


class Extractor:
    def __init__(self, config: ExtractConfig | None = None) -> None:
        load_dotenv(REPO_ROOT / ".env")
        if not os.environ.get("CEREBRAS_API_KEY"):
            raise RuntimeError(
                "CEREBRAS_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        self.config = config or load_extract_config()
        schema_text = SCHEMA_PATH.read_text(encoding="utf-8")
        self.schema = yaml.safe_load(schema_text)
        self.tool = build_tool_definition(self.schema)
        self.cache_key = compute_cache_key(self.config.model, SYSTEM_PROMPT, schema_text)
        self.cache_root = self.config.cache_dir / self.cache_key
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.client = Cerebras()

    def extract(self, review: dict, use_cache: bool = True) -> dict:
        """Return {review_id, model, issues, extracted_at, cached} for one review."""
        review_id = review["review_id"]
        cache_file = self.cache_root / f"{review_id}.json"
        if use_cache and cache_file.exists():
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            data["cached"] = True
            return data

        response = self.client.chat.completions.create(
            model=self.config.model,
            max_completion_tokens=self.config.max_completion_tokens,
            temperature=self.config.temperature,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Review:\n{review['text']}"},
            ],
            tools=[self.tool],
            tool_choice={"type": "function", "function": {"name": "record_issues"}},
        )

        issues = self._tool_output(response)
        record = {
            "review_id": review_id,
            "model": self.config.model,
            "issues": issues,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
        }
        cache_file.write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        record["cached"] = False
        return record

    @staticmethod
    def _tool_output(response: Any) -> list[dict]:
        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None) or []
        for call in tool_calls:
            if call.function.name == "record_issues":
                args = json.loads(call.function.arguments or "{}")
                return list(args.get("issues", []))
        raise RuntimeError("Model returned no record_issues tool call")
