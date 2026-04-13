from odoo import models


class ShopifyIntegrationConfig(models.Model):
    _inherit = "shopify.integration.config"

    def sync_products(self):
        for cfg in self:
            cfg.env["shopify.sync.log"].create_log(
                cfg, "product", "success", "TODO: product sync not implemented yet (stub)."
            )
        return True

    def cron_sync_products(self):
        configs = self.env["shopify.integration.config"].search([("active", "=", True)])
        return configs.sync_products()