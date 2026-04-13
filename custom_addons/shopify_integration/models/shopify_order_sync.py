from odoo import models


class ShopifyIntegrationConfig(models.Model):
    _inherit = "shopify.integration.config"

    def import_orders(self, date_from=None, date_to=None, use_last_sync=True):
        for cfg in self:
            cfg.env["shopify.sync.log"].create_log(
                cfg,
                "order",
                "success",
                f"TODO: order import stub. use_last_sync={use_last_sync}, date_from={date_from}, date_to={date_to}",
            )
        return True

    def cron_import_orders(self):
        configs = self.env["shopify.integration.config"].search([("active", "=", True)])
        return configs.import_orders()