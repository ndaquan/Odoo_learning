from odoo import fields, models
from odoo.exceptions import UserError

class ShopifyManualSyncWizard(models.TransientModel):
    _name = "shopify.manual.sync.wizard"
    _description = "Shopify Manual Sync Wizard"

    config_id = fields.Many2one("shopify.integration.config", required=True)
    sync_choice = fields.Selection(
        [("products", "Products"), ("inventory", "Inventory"), ("orders", "Orders"), ("all", "All")],
        required=True,
        default="products",
    )

    order_use_date_range = fields.Boolean()
    order_date_from = fields.Datetime()
    order_date_to = fields.Datetime()

    def _add_totals(self, totals, res):
        res = res or {}
        for k in ("created", "updated", "errors"):
            totals[k] += int(res.get(k, 0) or 0)

    def action_run(self):
        self.ensure_one()
        if self.order_use_date_range and self.sync_choice in ("orders", "all"):
            if not self.order_date_from or not self.order_date_to:
                raise UserError("Please set both From and To dates.")
            if self.order_date_from > self.order_date_to:
                raise UserError("From date must be <= To date.")
        cfg = self.config_id

        totals = {"created": 0, "updated": 0, "errors": 0}
        errors_text = []

        if self.sync_choice in ("products", "all"):
            try:
                self._add_totals(totals, cfg.sync_products())
            except Exception as e:
                totals["errors"] += 1
                errors_text.append(f"Products: {e}")

        if self.sync_choice in ("inventory", "all"):
            try:
                self._add_totals(totals, cfg.sync_inventory())
            except Exception as e:
                totals["errors"] += 1
                errors_text.append(f"Inventory: {e}")

        if self.sync_choice in ("orders", "all"):
            try:
                if self.order_use_date_range and self.order_date_from and self.order_date_to:
                    if self.order_date_from > self.order_date_to:
                        raise ValueError("order_date_from must be <= order_date_to")

                self._add_totals(
                    totals,
                    cfg.import_orders(
                        date_from=self.order_date_from,
                        date_to=self.order_date_to,
                        use_last_sync=not self.order_use_date_range,
                    ),
                )
            except Exception as e:
                totals["errors"] += 1
                errors_text.append(f"Orders: {e}")

        msg = (
            f"Manual sync finished.\n"
            f"Created: {totals['created']}\n"
            f"Updated: {totals['updated']}\n"
            f"Errors: {totals['errors']}"
        )
        if errors_text:
            msg += "\n\nDetails:\n- " + "\n- ".join(errors_text)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": "Shopify Sync", "message": msg, "type": "warning" if totals["errors"] else "success"},
        }
