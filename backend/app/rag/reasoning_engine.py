"""Reasoning Engine — enforces structured thinking before response generation.

Sits between context building (Stage 2) and LLM generation (Stage 3).
Does NOT modify any existing pipeline stages — only restructures the prompt
to enforce chain-of-thought reasoning and post-processes the output.

Pipeline position:
  ... → Context Build → **Reasoning Engine** → LLM Generate → Verify → ...

The engine:
1. Injects chain-of-thought reasoning instructions into the prompt
2. Parses the LLM's structured output into reasoning trace + final answer
3. Detects knowledge gaps, calculation steps, and assumption flags
4. Adapts response depth by user role
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger()


@dataclass
class ReasoningResult:
    """Output of the reasoning engine — structured thinking + final answer."""
    answer: str                          # Clean answer for the employee
    reasoning_steps: list[str] = field(default_factory=list)  # Internal thinking steps
    knowledge_gaps: list[str] = field(default_factory=list)   # What's missing from documents
    assumptions: list[str] = field(default_factory=list)      # Assumptions made
    confidence_label: str = "High"       # High / Medium / Low
    is_complete: bool = True             # Whether the answer fully addresses the query
    needs_clarification: bool = False    # Whether follow-up question was generated
    calculation_shown: bool = False      # Whether calculation steps were shown


# ── Reasoning prompt injection ────────────────────────────────────────────────

# Role-specific depth instructions
_ROLE_DEPTH = {
    "employee": (
        "RESPONSE STYLE: Simple and clear. Use bullet points. "
        "Avoid HR jargon — explain terms if used."
    ),
    "manager": (
        "RESPONSE STYLE: Include operational details a manager needs. "
        "Reference specific policy sections. Include team-level implications."
    ),
    "hr_admin": (
        "RESPONSE STYLE: Provide detailed policy references with section numbers. "
        "Include edge cases, exceptions, and cross-references between policies."
    ),
    "hr_head": (
        "RESPONSE STYLE: Provide comprehensive analysis with full policy references. "
        "Include compliance implications and historical context if available."
    ),
}


def build_reasoning_prompt(
    base_prompt: str,
    query: str,
    analysis_intent: str = "policy_lookup",
    is_calculation: bool = False,
    is_sensitive: bool = False,
    has_contradictions: bool = False,
    user_role: str = "employee",
    complexity: str = "simple",
) -> str:
    """Inject chain-of-thought reasoning into the LLM prompt.

    Keeps the injection compact to avoid overwhelming llama3:8b's context.
    Uses a lightweight think-then-answer pattern.
    """

    # Role-specific depth
    role_instruction = _ROLE_DEPTH.get(user_role, _ROLE_DEPTH["employee"])

    # Build concise thinking instructions based on query type
    think_steps = "Think step by step: (1) Which excerpts are relevant? (2) Do they fully answer the question? (3) Are there any conflicts between sources?"

    if is_calculation:
        think_steps += " (4) Show the exact numbers from documents. If personal data is needed, say what's needed — do NOT guess."
    if has_contradictions:
        think_steps += " (4) Documents contain conflicting info — show BOTH versions and advise contacting HR."
    if is_sensitive:
        think_steps += " (4) This is sensitive — be factual but redirect to HR for personal guidance."

    enhanced = base_prompt + f"""

{role_instruction}

{think_steps}

RESPOND IN THIS FORMAT:

REASONING:
[1-3 sentences: which documents you used, whether info is sufficient]

ANSWER:
[Your full answer with [Source: document, Page X] citations for every fact]

CONFIDENCE: [High / Medium / Low]
"""
    return enhanced


def _build_reasoning_block(
    query: str,
    intent: str,
    is_calculation: bool,
    is_sensitive: bool,
    has_contradictions: bool,
    complexity: str,
) -> str:
    """Build intent-specific reasoning steps."""

    # Base reasoning steps (always required)
    steps = [
        "1. UNDERSTAND: What exactly is the employee asking? Identify the specific policy/topic.",
        "2. LOCATE: Which document excerpts above contain relevant information? List them.",
        "3. SUFFICIENCY: Do the excerpts contain enough information to fully answer? If not, what's missing?",
    ]

    # Intent-specific steps
    if is_calculation:
        steps.append(
            "4. CALCULATE: Extract the exact numbers/formulas from the documents. "
            "Show each calculation step. If personal data is needed (hire date, salary, etc.), "
            "state what data is required — do NOT invent values."
        )
    elif intent == "comparative":
        steps.append(
            "4. COMPARE: Identify each item being compared. "
            "Extract the relevant attributes for each from the documents. "
            "Present a clear comparison."
        )
    elif intent == "procedural":
        steps.append(
            "4. SEQUENCE: Extract the step-by-step process from the documents. "
            "Number each step. Note any prerequisites or deadlines."
        )
    else:
        steps.append(
            "4. EXTRACT: Pull the specific facts that answer the question. "
            "For each fact, note which document excerpt it comes from."
        )

    # Conflict handling
    if has_contradictions:
        steps.append(
            "5. CONFLICTS: The documents contain potentially conflicting information. "
            "DO NOT silently pick one version. Instead: "
            "(a) State what each source says, "
            "(b) Note the conflict clearly, "
            "(c) Recommend the employee contact HR for clarification."
        )
    else:
        steps.append(
            "5. VERIFY: Cross-check your answer against the excerpts. "
            "Does every fact you state appear in a document? Remove anything unsupported."
        )

    # Sensitivity
    if is_sensitive:
        steps.append(
            "6. SENSITIVITY: This is a sensitive topic. Be factual but empathetic. "
            "Provide policy information but always redirect to HR for personal guidance."
        )

    # Complexity
    if complexity == "complex":
        steps.append(
            "7. STRUCTURE: This is a complex query. Break your answer into clearly "
            "labeled sections. Use headings and bullet points."
        )

    return "\n".join(steps)


# ── Response parsing ──────────────────────────────────────────────────────────

def parse_reasoning_response(raw_response: str) -> ReasoningResult:
    """Parse the LLM's structured response into reasoning components.

    Handles both structured (with REASONING/ANSWER/etc. blocks) and
    unstructured responses (fallback — treat entire response as answer).
    """

    # Try to extract structured sections
    reasoning = _extract_section(raw_response, "REASONING")
    answer = _extract_section(raw_response, "ANSWER")
    confidence = _extract_section(raw_response, "CONFIDENCE")
    gaps = _extract_section(raw_response, "GAPS")
    assumptions = _extract_section(raw_response, "ASSUMPTIONS")

    # If the LLM didn't follow the structure, treat entire response as answer
    if not answer:
        answer = raw_response.strip()
        reasoning = ""

    # Parse reasoning into steps
    reasoning_steps = []
    if reasoning:
        for line in reasoning.strip().split("\n"):
            line = line.strip()
            if line and not line.startswith("REASONING"):
                reasoning_steps.append(line)

    # Parse confidence
    confidence_label = "Medium"  # default
    if confidence:
        cl = confidence.strip().lower()
        if "high" in cl:
            confidence_label = "High"
        elif "low" in cl:
            confidence_label = "Low"
        else:
            confidence_label = "Medium"

    # Parse gaps
    knowledge_gaps = []
    if gaps and gaps.strip().lower() not in ("none", "none.", "n/a", ""):
        for line in gaps.strip().split("\n"):
            line = line.strip().lstrip("- ").strip()
            if line and line.lower() not in ("none", "none.", "n/a"):
                knowledge_gaps.append(line)

    # Parse assumptions
    assumption_list = []
    if assumptions and assumptions.strip().lower() not in ("none", "none.", "n/a", ""):
        for line in assumptions.strip().split("\n"):
            line = line.strip().lstrip("- ").strip()
            if line and line.lower() not in ("none", "none.", "n/a"):
                assumption_list.append(line)

    # Detect if answer is a refusal / incomplete
    is_complete = True
    refusal_indicators = [
        "don't have information", "not available in", "don't have enough",
        "please contact", "not covered in", "cannot answer",
    ]
    if any(ind in answer.lower() for ind in refusal_indicators):
        is_complete = False
        confidence_label = "Low"

    # Detect if calculation steps are shown
    calculation_shown = bool(re.search(r"\d+\s*[×x*+\-/÷=]\s*\d+", answer))

    return ReasoningResult(
        answer=answer.strip(),
        reasoning_steps=reasoning_steps,
        knowledge_gaps=knowledge_gaps,
        assumptions=assumption_list,
        confidence_label=confidence_label,
        is_complete=is_complete,
        calculation_shown=calculation_shown,
    )


def _extract_section(text: str, section_name: str) -> str:
    """Extract content between a section header and the next section header."""
    # Try patterns: "SECTION:" or "**SECTION:**" or "## SECTION"
    patterns = [
        rf"(?:^|\n)\s*\**{section_name}\**\s*:\s*\n?(.*?)(?=\n\s*\**(?:REASONING|ANSWER|CONFIDENCE|GAPS|ASSUMPTIONS)\**\s*:|$)",
        rf"(?:^|\n)\s*#{1,3}\s*{section_name}\s*\n(.*?)(?=\n\s*#{1,3}\s*(?:REASONING|ANSWER|CONFIDENCE|GAPS|ASSUMPTIONS)|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


# ── Post-processing: clean up for employee consumption ────────────────────────

def clean_answer_for_user(result: ReasoningResult, user_role: str = "employee") -> str:
    """Prepare the final answer for the employee.

    Strips internal reasoning artifacts and formats for the target audience.
    HR roles get additional metadata; employees get clean answers only.
    """
    answer = result.answer

    # Remove any remaining reasoning artifacts that leaked into the answer
    answer = re.sub(r"^\s*ANSWER\s*:\s*", "", answer, flags=re.IGNORECASE)
    answer = re.sub(r"^\s*REASONING\s*:\s*", "", answer, flags=re.IGNORECASE)

    # Strip any "Step 1:", "Step 2:" prefixes from internal reasoning
    answer = re.sub(r"^Step \d+:\s*", "", answer, flags=re.MULTILINE)

    # For HR roles: append assumptions and gaps as subtle metadata
    if user_role in ("hr_admin", "hr_head") and (result.assumptions or result.knowledge_gaps):
        addendum = ""
        if result.knowledge_gaps:
            addendum += "\n\n---\n**Note for HR:** The following aspects are not covered in the current documents:\n"
            for gap in result.knowledge_gaps[:3]:
                addendum += f"- {gap}\n"
        if result.assumptions:
            addendum += "\n**Assumptions made:**\n"
            for a in result.assumptions[:3]:
                addendum += f"- {a}\n"
        answer += addendum

    return answer.strip()
