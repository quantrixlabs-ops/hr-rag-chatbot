"""HRMS Adapter base interface — Phase 4 (F-36).

All HRMS adapters (BambooHR, SAP, Workday, Darwinbox) implement this interface.
The adapter pattern isolates per-HRMS API differences from the chat pipeline.

Flow:
  QueryAnalyzer detects intent=live_hr_data
      → HRMSRouter.get_adapter(tenant_id)
      → adapter.get_leave_balance(employee_id)
      → data injected into LLM context alongside RAG chunks
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class HRMSAdapter(ABC):
    """Abstract interface every HRMS adapter must implement.

    Subclasses raise HRMSAdapterError on API failures.
    The router catches these and falls back to RAG-only mode.
    """

    @abstractmethod
    def get_employee(self, employee_id: str) -> dict:
        """Return basic employee profile.

        Returns dict with keys: id, name, email, department, manager_id,
        job_title, hire_date, employment_type, status.
        """

    @abstractmethod
    def get_leave_balance(self, employee_id: str) -> dict:
        """Return current leave balances.

        Returns dict with keys: annual_leave, sick_leave, carry_forward,
        used_this_year, pending_requests.
        """

    @abstractmethod
    def get_org_chart(self, manager_id: str) -> dict:
        """Return direct reports for a manager.

        Returns dict with keys: manager, direct_reports (list of employee dicts).
        """

    @abstractmethod
    def get_payroll_info(self, employee_id: str) -> dict:
        """Return payslip/payroll summary (current period only).

        Returns dict with keys: gross_salary, net_salary, currency,
        pay_period, deductions (list).
        IMPORTANT: Only return summary — never raw payroll numbers
        unless tenant has payroll_disclosure feature enabled.
        """

    @abstractmethod
    def health(self) -> dict:
        """Return adapter health status.

        Returns dict with keys: status ("ok"|"degraded"|"down"),
        latency_ms, last_synced_at.
        """


class HRMSAdapterError(Exception):
    """Raised when an HRMS adapter call fails."""

    def __init__(self, adapter: str, operation: str, message: str):
        self.adapter = adapter
        self.operation = operation
        self.message = message
        super().__init__(f"[{adapter}] {operation} failed: {message}")


class HRMSDataIntent:
    """Query intent constants — used by QueryAnalyzer to trigger HRMS calls."""

    LEAVE_BALANCE = "leave_balance"
    EMPLOYEE_PROFILE = "employee_profile"
    ORG_CHART = "org_chart"
    PAYROLL_INFO = "payroll_info"
    NONE = "none"  # RAG-only, no live HRMS call needed

    # Keyword patterns that indicate live HRMS data is needed
    INTENT_PATTERNS: dict[str, list[str]] = {
        LEAVE_BALANCE: [
            "leave balance", "annual leave", "sick leave", "days off",
            "vacation days", "how many leaves", "remaining leave",
            "carry forward", "leave remaining",
        ],
        EMPLOYEE_PROFILE: [
            "my department", "my manager", "who is my manager",
            "my job title", "my hire date", "my employment",
        ],
        ORG_CHART: [
            "direct reports", "who reports to", "team members",
            "my team", "org chart", "reporting structure",
        ],
        PAYROLL_INFO: [
            "my salary", "my payslip", "net pay", "gross salary",
            "pay period", "my payroll",
        ],
    }

    @classmethod
    def detect(cls, query: str) -> str:
        """Detect if a query requires live HRMS data.

        Returns the intent constant or NONE if RAG-only.
        """
        query_lower = query.lower()
        for intent, patterns in cls.INTENT_PATTERNS.items():
            for pattern in patterns:
                if pattern in query_lower:
                    return intent
        return cls.NONE
