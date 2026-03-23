"""HRMS Router — per-tenant adapter selection and live data retrieval (Phase 4, F-36/F-37).

Responsibilities:
1. Map tenant_id → HRMS adapter type (from tenant config)
2. Instantiate and cache adapters (one per tenant, refreshed on config change)
3. Detect live HR data intent in chat queries
4. Fetch live data and inject into LLM context
5. Graceful fallback: if HRMS unavailable, answer from RAG docs only

Tenant config shape (tenants.config.hrms):
  {
    "provider": "bamboohr" | "sap" | null,
    "bamboohr": { "subdomain": "...", "api_key": "..." },
    "sap": { "api_url": "...", "company_id": "...", "client_id": "...", "client_secret": "..." }
  }
"""

from __future__ import annotations

import structlog
from typing import Optional

from backend.app.integrations.hrms_base import HRMSAdapter, HRMSAdapterError, HRMSDataIntent
from backend.app.integrations.bamboohr import BambooHRAdapter
from backend.app.integrations.sap_successfactors import SAPSuccessFactorsAdapter

logger = structlog.get_logger()

# Adapter cache: tenant_id → HRMSAdapter instance
# Cleared on tenant config update via invalidate_adapter()
_adapter_cache: dict[str, HRMSAdapter] = {}


def get_adapter(tenant_id: str, tenant_config: dict) -> Optional[HRMSAdapter]:
    """Return the HRMS adapter for this tenant, or None if not configured.

    Caches adapter instances (instantiation is cheap, HTTP connections are lazy).
    Rebuilds if not in cache — call invalidate_adapter() on config change.
    """
    if tenant_id in _adapter_cache:
        return _adapter_cache[tenant_id]

    hrms_config = tenant_config.get("hrms", {})
    provider = hrms_config.get("provider")

    if not provider:
        return None

    adapter: Optional[HRMSAdapter] = None

    if provider == "bamboohr":
        bhr = hrms_config.get("bamboohr", {})
        subdomain = bhr.get("subdomain")
        api_key = bhr.get("api_key")
        if subdomain and api_key:
            adapter = BambooHRAdapter(
                subdomain=subdomain,
                api_key=api_key,
                timeout=bhr.get("timeout_seconds", 10),
            )

    elif provider == "sap":
        sap = hrms_config.get("sap", {})
        if all(k in sap for k in ("api_url", "company_id", "client_id", "client_secret")):
            adapter = SAPSuccessFactorsAdapter(
                api_url=sap["api_url"],
                company_id=sap["company_id"],
                client_id=sap["client_id"],
                client_secret=sap["client_secret"],
                timeout=sap.get("timeout_seconds", 15),
            )

    if adapter:
        _adapter_cache[tenant_id] = adapter
        logger.info("hrms_adapter_created", tenant_id=tenant_id, provider=provider)

    return adapter


def invalidate_adapter(tenant_id: str) -> None:
    """Remove cached adapter for tenant — call after tenant config update."""
    _adapter_cache.pop(tenant_id, None)
    logger.info("hrms_adapter_invalidated", tenant_id=tenant_id)


def fetch_live_hr_data(
    query: str,
    employee_id: str,
    tenant_id: str,
    tenant_config: dict,
) -> Optional[dict]:
    """Detect HRMS data intent and fetch live data if needed.

    Returns a dict with live data to inject into LLM context,
    or None if no live data intent detected or HRMS unavailable.

    The returned dict is formatted for LLM context injection:
    {
        "intent": "leave_balance",
        "data": { ... },
        "context_text": "Live data from HRMS: ..."
    }
    """
    intent = HRMSDataIntent.detect(query)
    if intent == HRMSDataIntent.NONE:
        return None

    adapter = get_adapter(tenant_id, tenant_config)
    if not adapter:
        logger.debug("hrms_not_configured", tenant_id=tenant_id, intent=intent)
        return None

    try:
        data: dict = {}

        if intent == HRMSDataIntent.LEAVE_BALANCE:
            data = adapter.get_leave_balance(employee_id)
            context_text = _format_leave_balance(data)

        elif intent == HRMSDataIntent.EMPLOYEE_PROFILE:
            data = adapter.get_employee(employee_id)
            context_text = _format_employee_profile(data)

        elif intent == HRMSDataIntent.ORG_CHART:
            data = adapter.get_org_chart(employee_id)
            context_text = _format_org_chart(data)

        elif intent == HRMSDataIntent.PAYROLL_INFO:
            data = adapter.get_payroll_info(employee_id)
            context_text = _format_payroll(data)

        else:
            return None

        logger.info(
            "hrms_data_fetched",
            intent=intent,
            employee_id=employee_id,
            tenant_id=tenant_id,
        )
        return {"intent": intent, "data": data, "context_text": context_text}

    except HRMSAdapterError as e:
        logger.warning(
            "hrms_fetch_failed",
            intent=intent,
            employee_id=employee_id,
            error=str(e),
        )
        # Graceful degradation — return None so RAG pipeline continues without live data
        return None


# ── Context formatters — convert raw HRMS data to LLM-readable text ──────────

def _format_leave_balance(data: dict) -> str:
    lines = ["[LIVE HRMS DATA — Leave Balance as of today]"]
    if data.get("annual_leave") is not None:
        lines.append(f"Annual Leave remaining: {data['annual_leave']} days")
    if data.get("sick_leave") is not None:
        lines.append(f"Sick Leave remaining: {data['sick_leave']} days")
    if data.get("carry_forward") is not None:
        lines.append(f"Carry Forward: {data['carry_forward']} days")
    if data.get("used_this_year") is not None:
        lines.append(f"Used this year: {data['used_this_year']} days")
    return "\n".join(lines)


def _format_employee_profile(data: dict) -> str:
    lines = ["[LIVE HRMS DATA — Employee Profile]"]
    if data.get("name"):
        lines.append(f"Name: {data['name']}")
    if data.get("department"):
        lines.append(f"Department: {data['department']}")
    if data.get("job_title"):
        lines.append(f"Job Title: {data['job_title']}")
    if data.get("hire_date"):
        lines.append(f"Hire Date: {data['hire_date']}")
    if data.get("employment_type"):
        lines.append(f"Employment Type: {data['employment_type']}")
    return "\n".join(lines)


def _format_org_chart(data: dict) -> str:
    lines = ["[LIVE HRMS DATA — Org Chart]"]
    reports = data.get("direct_reports", [])
    lines.append(f"Direct Reports: {data.get('count', len(reports))}")
    for r in reports[:10]:  # Cap at 10 to avoid context overflow
        lines.append(f"  - {r.get('name', 'Unknown')} ({r.get('job_title', '')})")
    return "\n".join(lines)


def _format_payroll(data: dict) -> str:
    if not data.get("available"):
        return f"[LIVE HRMS DATA — Payroll]\n{data.get('message', 'Not available')}"
    lines = ["[LIVE HRMS DATA — Payroll Summary]"]
    if data.get("currency"):
        lines.append(f"Currency: {data['currency']}")
    if data.get("pay_period"):
        lines.append(f"Pay Period: {data['pay_period']}")
    if data.get("message"):
        lines.append(data["message"])
    return "\n".join(lines)
