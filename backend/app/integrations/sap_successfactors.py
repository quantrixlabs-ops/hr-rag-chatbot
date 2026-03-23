"""SAP SuccessFactors HRMS Adapter — Phase 4 (F-36).

API: SAP SuccessFactors OData API v2
Docs: https://help.sap.com/docs/SAP_SUCCESSFACTORS_HXM_SUITE

Authentication: OAuth 2.0 SAML Bearer Assertion
Base URL: https://api{dc}.successfactors.com/odata/v2/

Tenant config keys (stored in tenants.config.hrms.sap):
  api_url: str         — e.g. "https://api4.successfactors.com"
  company_id: str      — SAP company ID
  client_id: str       — OAuth client ID
  client_secret: str   — OAuth client secret (encrypted in Phase 5)
  timeout_seconds: int — default 15
"""

from __future__ import annotations

import time
from typing import Any, Optional

import structlog

from backend.app.integrations.hrms_base import HRMSAdapter, HRMSAdapterError

logger = structlog.get_logger()


class SAPSuccessFactorsAdapter(HRMSAdapter):
    """SAP SuccessFactors OData API adapter."""

    def __init__(
        self,
        api_url: str,
        company_id: str,
        client_id: str,
        client_secret: str,
        timeout: int = 15,
    ):
        self.api_url = api_url.rstrip("/")
        self.company_id = company_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0

    def _get_token(self) -> str:
        """Fetch OAuth2 token (cached until expiry)."""
        if self._token and time.time() < self._token_expiry - 60:
            return self._token

        try:
            import httpx
        except ImportError:
            raise HRMSAdapterError(
                "SAP", "auth", "httpx not installed — add to requirements.txt"
            )

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    f"{self.api_url}/oauth/token",
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "company_id": self.company_id,
                    },
                )
                resp.raise_for_status()
                token_data = resp.json()
                self._token = token_data["access_token"]
                self._token_expiry = time.time() + token_data.get("expires_in", 3600)
                return self._token
        except Exception as e:
            raise HRMSAdapterError("SAP", "auth/token", str(e))

    def _request(self, path: str, params: Optional[dict] = None) -> dict:
        """Make an authenticated OData request to SAP SuccessFactors.

        Raises HRMSAdapterError on HTTP errors or timeouts.
        """
        try:
            import httpx
        except ImportError:
            raise HRMSAdapterError(
                "SAP", "import", "httpx not installed — add to requirements.txt"
            )

        url = f"{self.api_url}/odata/v2/{path.lstrip('/')}"
        default_params = {"$format": "json"}
        if params:
            default_params.update(params)

        try:
            token = self._get_token()
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    params=default_params,
                )
                resp.raise_for_status()
                data = resp.json()
                # OData wraps results in d.results or d
                return data.get("d", data)
        except httpx.HTTPStatusError as e:
            raise HRMSAdapterError(
                "SAP", path,
                f"HTTP {e.response.status_code}: {e.response.text[:200]}"
            )
        except httpx.TimeoutException:
            raise HRMSAdapterError("SAP", path, "Request timed out")
        except HRMSAdapterError:
            raise
        except Exception as e:
            raise HRMSAdapterError("SAP", path, str(e))

    def get_employee(self, employee_id: str) -> dict:
        """Fetch employee profile from SAP SuccessFactors.

        OData entity: PerPerson + EmpEmployment
        """
        data = self._request(
            f"User('{employee_id}')",
            params={
                "$select": "userId,firstName,lastName,email,department,"
                           "division,title,hireDate,employmentType,jobCode"
            },
        )

        return {
            "id": employee_id,
            "name": f"{data.get('firstName', '')} {data.get('lastName', '')}".strip(),
            "email": data.get("email", ""),
            "department": data.get("department", ""),
            "division": data.get("division", ""),
            "job_title": data.get("title", ""),
            "hire_date": _parse_sap_date(data.get("hireDate", "")),
            "employment_type": data.get("employmentType", ""),
            "manager_id": data.get("managerId", ""),
            "status": "active",
        }

    def get_leave_balance(self, employee_id: str) -> dict:
        """Fetch time-off balances from SAP SuccessFactors.

        OData entity: TimeAccountBalance
        """
        data = self._request(
            "TimeAccountBalance",
            params={
                "$filter": f"externalCode eq '{employee_id}'",
                "$select": "timeAccountType,balance,usedQuantity",
            },
        )

        results = data.get("results", [])
        balances: dict[str, Any] = {
            "annual_leave": 0,
            "sick_leave": 0,
            "carry_forward": 0,
            "used_this_year": 0,
            "pending_requests": 0,
        }

        for item in results:
            account_type = item.get("timeAccountType", "").lower()
            balance = float(item.get("balance", 0))
            used = float(item.get("usedQuantity", 0))

            if "annual" in account_type or "vacation" in account_type:
                balances["annual_leave"] = balance
                balances["used_this_year"] = used
            elif "sick" in account_type:
                balances["sick_leave"] = balance
            elif "carry" in account_type:
                balances["carry_forward"] = balance

        logger.info("sap_leave_fetched", employee_id=employee_id)
        return balances

    def get_org_chart(self, manager_id: str) -> dict:
        """Fetch direct reports from SAP SuccessFactors.

        OData entity: EmpJob (filter by managerId)
        """
        data = self._request(
            "User",
            params={
                "$filter": f"managerId eq '{manager_id}'",
                "$select": "userId,firstName,lastName,title,department",
            },
        )

        results = data.get("results", [])
        direct_reports = [
            {
                "id": emp.get("userId"),
                "name": f"{emp.get('firstName', '')} {emp.get('lastName', '')}".strip(),
                "job_title": emp.get("title", ""),
                "department": emp.get("department", ""),
            }
            for emp in results
        ]

        return {
            "manager": {"id": manager_id},
            "direct_reports": direct_reports,
            "count": len(direct_reports),
        }

    def get_payroll_info(self, employee_id: str) -> dict:
        """Fetch payroll summary from SAP SuccessFactors EC Payroll.

        Requires SAP EC Payroll module (separate entitlement).
        """
        try:
            data = self._request(
                "PaymentInformationDetailV3",
                params={
                    "$filter": f"workerExternalId eq '{employee_id}'",
                    "$select": "payComponentType,amount,currency,payPeriodFrequency",
                    "$top": "5",
                },
            )
            results = data.get("results", [])
            if not results:
                return {
                    "available": False,
                    "message": "No payroll data found. Contact HR for your payslip.",
                }
            # Return summary only — not individual line items
            first = results[0]
            return {
                "available": True,
                "currency": first.get("currency", ""),
                "pay_period": first.get("payPeriodFrequency", "Monthly"),
                "message": "Payroll summary available. Contact HR for detailed breakdown.",
            }
        except HRMSAdapterError:
            return {
                "available": False,
                "message": "Payroll data requires SAP EC Payroll module.",
            }

    def health(self) -> dict:
        """Check SAP SuccessFactors API connectivity."""
        start = time.time()
        try:
            self._get_token()
            latency = int((time.time() - start) * 1000)
            return {"status": "ok", "latency_ms": latency, "adapter": "sap_successfactors"}
        except HRMSAdapterError as e:
            return {"status": "down", "error": str(e), "adapter": "sap_successfactors"}


def _parse_sap_date(sap_date: str) -> str:
    """Convert SAP OData date format /Date(1234567890000)/ to ISO date string."""
    if not sap_date or not sap_date.startswith("/Date("):
        return sap_date
    try:
        ts_ms = int(sap_date[6:-2])
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        return dt.date().isoformat()
    except (ValueError, IndexError):
        return sap_date
