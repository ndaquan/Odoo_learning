import uuid
from urllib.parse import urlparse, parse_qs

from odoo import api, fields, models


def _get_next_page_info(link_header):
    if not link_header:
        return None
    for part in link_header.split(","):
        if 'rel="next"' not in part:
            continue
        start = part.find("<")
        end = part.find(">")
        if start == -1 or end == -1:
            continue
        url = part[start + 1 : end]
        qs = parse_qs(urlparse(url).query)
        return (qs.get("page_info") or [None])[0]
    return None


class ShopifyIntegrationConfig(models.Model):
    _inherit = "shopify.integration.config"

    def _inv_log(self, status, message, shopify_id=None, op=None):
        return self.env["shopify.sync.log"].create_log(
            self, "inventory", status, message, shopify_id=shopify_id, operation_ref=op
        )

    def _ensure_shopify_location_id(self, op):
        self.ensure_one()
        if self.shopify_location_id:
            return self.shopify_location_id

        data = self._shopify_request("GET", "locations.json")
        locations = (data or {}).get("locations") or []
        active = [l for l in locations if l.get("active")]
        pick = (active[0] if active else (locations[0] if locations else None))
        if not pick:
            raise Exception("No Shopify locations found.")

        loc_id = str(pick.get("id") or "")
        self.shopify_location_id = loc_id
        self._inv_log("success", f"Using Shopify location_id={loc_id}", op=op)
        return loc_id

    def _set_onhand_via_quant(self, product, location, qty):
        """
        Update stock using ORM inventory adjustment (no SQL).
        """
        Quant = self.env["stock.quant"].sudo()
        current = Quant._get_available_quantity(product, location)
        delta = float(qty) - float(current)
        if abs(delta) < 1e-9:
            return
        Quant._update_available_quantity(product, location, delta)


    def sync_inventory(self):
        self.ensure_one()
        op = str(uuid.uuid4())
        updated = 0
        errors = 0

        self._inv_log("partial", "Inventory sync started.", op=op)

        try:
            shopify_location_id = self._ensure_shopify_location_id(op)
        except Exception as e:
            errors += 1
            self._inv_log("failed", f"Failed to determine Shopify location: {e}", op=op)
            return {"created": 0, "updated": updated, "errors": errors}

        odoo_location = self.warehouse_id.lot_stock_id
        if not odoo_location:
            errors += 1
            self._inv_log("failed", "Warehouse has no lot_stock_id location.", op=op)
            return {"created": 0, "updated": updated, "errors": errors}

        Product = self.env["product.product"].sudo()

        page_info = None
        while True:
            params = {"limit": 250, "location_ids": shopify_location_id}
            if page_info:
                params = {"limit": 250, "page_info": page_info}

            try:
                data, resp = self._shopify_request(
                    "GET", "inventory_levels.json", params=params, return_response=True
                )
            except Exception as e:
                errors += 1
                self._inv_log("failed", f"Inventory API call failed: {e}", op=op)
                break

            levels = (data or {}).get("inventory_levels") or []
            for lvl in levels:
                try:
                    inv_item_id = str(lvl.get("inventory_item_id") or "")
                    available = lvl.get("available")
                    qty = float(available or 0.0)

                    product = Product.search([("x_shopify_inventory_item_id", "=", inv_item_id)], limit=1)
                    if not product:
                        errors += 1
                        self._inv_log(
                            "partial",
                            f"Inventory item not mapped to product (missing x_shopify_inventory_item_id={inv_item_id}).",
                            shopify_id=inv_item_id,
                            op=op,
                        )
                        continue

                    self._set_onhand_via_quant(product, odoo_location, qty)
                    updated += 1

                except Exception as e:
                    errors += 1
                    self._inv_log("partial", f"Failed inventory line: {e}", shopify_id=str(lvl.get("inventory_item_id") or ""), op=op)

            page_info = _get_next_page_info(resp.headers.get("Link"))
            if not page_info:
                break

        status = "success" if errors == 0 else "partial"
        self._inv_log(status, f"Inventory sync finished. updated={updated}, errors={errors}", op=op)
        return {"created": 0, "updated": updated, "errors": errors}

    @api.model
    def cron_sync_inventory(self):
        configs = self.env["shopify.integration.config"].search([("active", "=", True)])
        for cfg in configs:
            cfg.sync_inventory()
        return True