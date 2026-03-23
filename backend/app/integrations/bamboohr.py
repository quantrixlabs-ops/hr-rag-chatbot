"""BambooHR HRMS Adapter — Phase 4 (F-36).

API: BambooHR REST API v1
Docs: https://documentation.bamboohr.com/reference

Authentication: HTTP Basic Auth with API key (password = 'x')
Base URL: https://{subdomain}.bamboohr.com/api/gateway.php/{subdomain}/v1/

Tenant config keys (stored in tenants.config.hrms.bamboohr):
  subdomain: str       — e.g. "acmecorp"
  api_key: str         — BambooHR API key (stored encrypted in Phase 5)
  timeout_seconds: int — default 10
"""

from __future__ import annotations

import time
from typing import Any, Optional

import structlog

from backend.app.integrations.hrms_base import HRMSAdapter, HRMSAdapterError

logger = structlog.get_logger()


class BambooHRAdapter(HRMSAdapter):
    """BambooHR REST API adapter."""

    def __init__(self, subdomain: str, api_key: str, timeout: int = 10):
        self.subdomain = subdomain
        self.api_key = api_key
        self.timeout = timeout
        self._base_url = f"https://api.bamboohr.com/api/gateway.php/{subdomain}/v1"

    def _request(self, method: str, path: str, **kwargs: Any) -> dict:
        """Make an authenticated request to BambooHR API.

        Raises HRMSAdapterError on HTTP errors or timeouts.
        """
        try:
            import httpx
        except ImportError:
            raise HRMSAdapterError(
                "BambooHR", "import", "httpx not installed — add to requirements.txt"
            )

        url = f"{self._base_url}/{path.lstrip('/')}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.request(
                    method,
                    url,
                    auth=(self.api_key, "x"),
                    headers={"Accept": "application/json"},
                    **kwargs,
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            raise HRMSAdapterError(
                "BambooHR", path,
                f"HTTP {e.response.status_code}: {e.response.text[:200]}"
            )
        except httpx.TimeoutException:
            raise HRMSAdapterError("BambooHR", path, "Request timed out")
        except Exception as e:
            raise HRMSAdapterError("BambooHR", path, str(e))

    def get_employee(self, employee_id: str) -> dict:
        """Fetch employee profile from BambooHR.

        BambooHR endpoint: GET /employees/{id}
        """
        data = self._request(
            "GET",
            f"employees/{employee_id}",
            params={
                "fields": "id,firstName,lastName,workEmail,department,division,"
                          "jobTitle,hireDate,employmentHistoryStatus,supervisorId"
            },
        )
        return {
            "id": employee_id,
            "name": f"{data.get('firstName', '')} {data.get('lastName', '')}".strip(),
            "email": data.get("workEmail", ""),
            "department": data.get("department", ""),
            "division": data.get("division", ""),
            "job_title": data.get("jobTitle", ""),
            "hire_date": data.get("hireDate", ""),
            "employment_type": data.get("employmentHistoryStatus", ""),
            "manager_id": data.get("supervisorId", ""),
            "status": "active" if data.get("employmentHistoryStatus") == "Active" else "inactive",
        }

    def get_leave_balance(self, employee_id: str) -> dict:
        """Fetch leave balances from BambooHR.

        BambooHR endpoint: GET /employees/{id}/time_off/calculator
        """
        data = self._request(
            "GET",
            f"employees/{employee_id}/time_off/calculator",
        )

        # BambooHR returns a list of leave policies
        balances: dict[str, Any] = {
            "annual_leave": 0,
            "sick_leave": 0,
            "carry_forward": 0,
            "used_this_year": 0,
            "pending_requests": 0,
        }

        for policy in data if isinstance(data, list) else []:
            name = policy.get("name", "").lower()
            available = float(policy.get("balance", 0))
            used = float(policy.get("usedYtd", 0))

            if "annual" in name or "vacation" in name or "pto" in name:
                balances["annual_leave"] = available
                balances["used_this_year"] = used
            elif "sick" in name:
                balances["sick_leave"] = available
            elif "carry" in name:
                balances["carry_forward"] = available

        logger.info("bamboohr_leave_fetched", employee_id=employee_id)
        return balances

    def get_org_chart(self, manager_id: str) -> dict:
        """Fetch direct reports for a manager.

        BambooHR endpoint: GET /employees/directory (filtered)
        """
        data = self._request("GET", "employees/directory")
        employees = data.get("employees", [])

        manager_info: dict = {}
        direct_reports: list[dict] = []

        for emp in employees:
            if str(emp.get("id")) == str(manager_id):
                manager_info = {
                    "id": emp.get("id"),
                    "name": emp.get("displayName", ""),
                    "job_title": emp.get("jobTitle", ""),
                }
            elif str(emp.get("supervisorId")) == str(manager_id):
                direct_reports.append({
                    "id": emp.get("id"),
                    "name": emp.get("displayName", ""),
                    "job_title": emp.get("jobTitle", ""),
                    "department": emp.get("department", ""),
                })

        return {
            "manager": manager_info,
            "direct_reports": direct_reports,
            "count": len(direct_reports),
        }

    def get_payroll_info(self, employee_id: str) -> dict:
        """Fetch payroll summary.

        NOTE: BambooHR standard plan does not expose payroll via API.
        This returns a placeholder — enable via BambooHR Payroll add-on.
        """
        # BambooHR payroll requires enterprise add-on
        # Return graceful degradation
        logger.warning("bamboohr_payroll_unavailable", employee_id=employee_id)
        return {
            "available": False,
            "message": "Payroll data requires BambooHR Payroll module. "
                       "Contact HR for your latest payslip.",
        }

    def health(self) -> dict:
        """Check BambooHR API connectivity."""
        start = time.time()
        try:
            self._request("GET", "employees/directory", params={"limit": "1"})
            latency = int((time.time() - start) * 1000)
            return {"status": "ok", "latency_ms": latency, "adapter": "bamboohr"}
        except HRMSAdapterError as e:
            return {"status": "down", "error": str(e), "adapter": "bamboohr"}
