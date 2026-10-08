"""ai_agents · tools — the accountant: subscription, invoices, commission lines
and the financial summary of the one business the request named.
"""

from dataclasses import asdict
from datetime import date
from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.core.exceptions import NotFoundError

if TYPE_CHECKING:  # pragma: no cover
    from app.modules.ai_agents.service import TenantServices

from app.modules.ai_agents.tools.base import (
    Result,
    ToolkitBase,
    _iso,
    _text,
)


class AccountantTools(ToolkitBase):
    @staticmethod
    def _invoice(invoice: Any) -> Result:
        return {
            "invoice_id": str(invoice.id),
            "period_start": invoice.period.period_start.isoformat(),
            "period_end": invoice.period.period_end.isoformat(),
            "status": str(invoice.status),
            "subscription_amount": str(invoice.subscription_amount),
            "commission_amount": str(invoice.commission_amount),
            "processing_amount": str(invoice.processing_amount),
            "vat_amount": str(invoice.vat_amount),
            "total_amount": str(invoice.total_amount),
            "currency": invoice.currency,
            "due_at": _iso(invoice.due_at),
        }

    async def get_subscription(self) -> Result:
        """The business's plan, what it costs, and its commission rate."""

        async def work(services: "TenantServices") -> Result:
            subscription = await services.billing.subscription_or_default(self._business())
            amount = subscription.subscription_amount()
            return {
                "tier": str(subscription.tier),
                "status": str(subscription.status),
                "monthly_amount": str(amount.amount),
                "currency": amount.currency,
                "seats": subscription.seats,
                "locations": subscription.locations,
                "new_client_commission_pct": str(subscription.plan.new_client_commission_pct),
                "processing_fee_pct": str(subscription.plan.processing_fee_pct),
                "period_end": subscription.current_period_end.isoformat(),
            }

        return await self._call("get_subscription", work)

    async def list_recent_invoices(self, limit: int = 6) -> Result:
        """NOVA's most recent invoices to this business."""

        async def work(services: "TenantServices") -> Result:
            invoices = await services.billing.list_invoices(
                self._business(), limit=max(1, min(limit, 12))
            )
            return {"invoices": [self._invoice(i) for i in invoices]}

        return await self._call("list_recent_invoices", work)

    async def get_invoice(self, invoice_id: UUID) -> Result:
        """One NOVA invoice to this business."""

        async def work(services: "TenantServices") -> Result:
            invoice = await services.billing.get_invoice(invoice_id)
            if invoice.business_id != self._business():
                raise NotFoundError("There is no such invoice for this business.")
            return self._invoice(invoice)

        return await self._call("get_invoice", work)

    async def explain_commission_line(self, line_id: UUID) -> Result:
        """Why one commission line cost what it cost, in BillingService's own words."""

        async def work(services: "TenantServices") -> Result:
            return await services.billing.explain_commission_line(line_id)

        return await self._call("explain_commission_line", work)

    async def get_plan_comparison(self) -> Result:
        """The published price list, docs/11 section 2."""

        async def work(services: "TenantServices") -> Result:
            return {"plans": services.billing.plan_comparison()}

        return await self._call("get_plan_comparison", work)

    async def get_financial_summary(
        self, date_from: date | None = None, date_to: date | None = None
    ) -> Result:
        """Earned, collected, refunded, paid out and invoiced for a period (default: 30 days)."""

        async def work(services: "TenantServices") -> Result:
            report = await services.analytics.financial_summary(
                self._business(), date_from=date_from, date_to=date_to
            )
            self.deps.artifacts.metrics_used |= {"revenue", "collected", "refunded"}
            return {
                "date_from": report.window.date_from.isoformat(),
                "date_to": report.window.date_to.isoformat(),
                **{key: _text(value) for key, value in asdict(report.summary).items()},
            }

        return await self._call("get_financial_summary", work)
