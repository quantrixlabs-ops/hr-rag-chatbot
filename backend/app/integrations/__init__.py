"""HRMS Integration Framework — Phase 4.

Adapter pattern isolates per-HRMS API complexity.
Each adapter implements HRMSAdapter interface.
HRMSRouter selects the correct adapter per tenant.
"""
