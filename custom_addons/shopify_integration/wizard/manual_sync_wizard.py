from odoo import fields, models


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

    def action_run(self):
        self.ensure_one()
        cfg = self.config_id
        if self.sync_choice in ("products", "all"):
            cfg.sync_products()
        if self.sync_choice in ("inventory", "all"):
            cfg.sync_inventory()
        if self.sync_choice in ("orders", "all"):
            cfg.import_orders(
                date_from=self.order_date_from,
                date_to=self.order_date_to,
                use_last_sync=not self.order_use_date_range,
            )
        return {"type": "ir.actions.act_window_close"}