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

    def _log(self, status, message, shopify_id=None, op=None):
        Log = self.env["shopify.sync.log"]
        return Log.create_log(self, "order", status, message, shopify_id=shopify_id, operation_ref=op)

    def _find_or_create_partner(self, email, customer, shipping_address):
        Partner = self.env["res.partner"]

        email_norm = (email or "").strip().lower()
        partner = Partner.search([("email", "=ilike", email_norm)], limit=1) if email_norm else None
        if not partner:
            name = (customer or {}).get("first_name") or (customer or {}).get("last_name") or email_norm or "Shopify Customer"
            full = ((customer or {}).get("first_name") or "") + " " + ((customer or {}).get("last_name") or "")
            full = full.strip() or name
            partner = Partner.create({
                "name": full,
                "email": email_norm or False,
                "phone": (customer or {}).get("phone") or False,
            })

        # delivery address child
        ship = shipping_address or {}
        if ship:
            delivery_vals = {
                "type": "delivery",
                "parent_id": partner.id,
                "name": (ship.get("name") or partner.name) or "Delivery",
                "street": ship.get("address1") or False,
                "street2": ship.get("address2") or False,
                "city": ship.get("city") or False,
                "zip": ship.get("zip") or False,
                "phone": ship.get("phone") or partner.phone or False,
                "email": partner.email or False,
                "country_id": self.env["res.country"].search([("code", "=", ship.get("country_code"))], limit=1).id if ship.get("country_code") else False,
                "state_id": self.env["res.country.state"].search([("code", "=", ship.get("province_code"))], limit=1).id if ship.get("province_code") else False,
            }
            key_domain = [
                ("parent_id", "=", partner.id),
                ("type", "=", "delivery"),
                ("street", "=", delivery_vals["street"] or False),
                ("street2", "=", delivery_vals["street2"] or False),
                ("city", "=", delivery_vals["city"] or False),
                ("zip", "=", delivery_vals["zip"] or False),
                ("country_id", "=", delivery_vals["country_id"] or False),
                ("state_id", "=", delivery_vals["state_id"] or False),
            ]
            delivery = Partner.search(key_domain, limit=1)
            if not delivery:
                delivery = Partner.create(delivery_vals)
            return partner, delivery

        return partner, partner

    def import_orders(self, date_from=None, date_to=None, use_last_sync=True):
        self.ensure_one()
        SaleOrder = self.env["sale.order"]
        SaleOrderLine = self.env["sale.order.line"]
        Product = self.env["product.product"]

        op = str(uuid.uuid4())
        created = skipped = warnings = errors = 0

        self._log("success", "Order import started.", op=op)

        # time filter
        created_at_min = None
        if use_last_sync and self.last_sync:
            created_at_min = self.last_sync
        elif date_from:
            created_at_min = date_from

        params = {
            "limit": 250,
            "status": "any",
            "order": "created_at asc",
        }
        if created_at_min:
            params["created_at_min"] = fields.Datetime.to_string(created_at_min)
        if date_to:
            params["created_at_max"] = fields.Datetime.to_string(date_to)

        page_info = None
        newest_created_at_seen = None

        while True:
            page_params = dict(params)
            if page_info:
                page_params = {"limit": 250, "page_info": page_info}

            try:
                data, resp = self._shopify_request("GET", "orders.json", params=page_params, return_response=True)
            except Exception as e:
                errors += 1
                self._log("failed", f"API call failed: {e}", op=op)
                break

            orders = (data or {}).get("orders") or []
            for o in orders:
                shopify_order_id = str(o.get("id") or "")
                try:
                    # dedup
                    if SaleOrder.search([("x_shopify_order_id", "=", shopify_order_id)], limit=1):
                        skipped += 1
                        continue

                    email = o.get("email") or (o.get("customer") or {}).get("email")
                    partner, delivery = self._find_or_create_partner(
                        email=email,
                        customer=o.get("customer") or {},
                        shipping_address=o.get("shipping_address") or {},
                    )

                    order_vals = {
                        "partner_id": partner.id,
                        "partner_shipping_id": delivery.id,
                        "x_shopify_order_id": shopify_order_id,
                        "origin": o.get("name") or f"Shopify {shopify_order_id}",
                    }
                    if "warehouse_id" in SaleOrder._fields:
                        order_vals["warehouse_id"] = self.warehouse_id.id
                        
                    so = SaleOrder.create(order_vals)

                    kept_lines = 0
                    for li in (o.get("line_items") or []):
                        sku = (li.get("sku") or "").strip()
                        if not sku:
                            warnings += 1
                            self._log("partial", "Skipped line: missing SKU.", shopify_id=shopify_order_id, op=op)
                            continue

                        product = Product.search([("default_code", "=", sku)], limit=1)
                        if not product:
                            warnings += 1
                            self._log("partial", f"Skipped line: SKU not found in Odoo: {sku}", shopify_id=shopify_order_id, op=op)
                            continue

                        try:
                            price_unit = float(li.get("price") or 0.0)
                        except Exception:
                            price_unit = 0.0

                        SaleOrderLine.create({
                            "order_id": so.id,
                            "product_id": product.id,
                            "product_uom_qty": float(li.get("quantity") or 0.0),
                            "price_unit": price_unit,
                            "name": li.get("name") or product.display_name,
                        })
                        kept_lines += 1

                    if kept_lines == 0:
                        warnings += 1
                        self._log("partial", "Order created but has no valid lines; cancelling draft.", shopify_id=shopify_order_id, op=op)
                        so.action_cancel()
                        continue

                    so.action_confirm()
                    created += 1

                    # track newest created_at to update last_sync safely
                    created_at_raw = (o.get("created_at") or "").strip()
                    created_at_dt = None
                    if created_at_raw:
                        # normalize ISO8601 -> try parse; handle trailing Z
                        created_at_raw = created_at_raw.replace("Z", "+00:00")
                        try:
                            created_at_dt = fields.Datetime.to_datetime(created_at_raw)
                        except Exception:
                            created_at_dt = None
                    if created_at_dt and (not newest_created_at_seen or created_at_dt > newest_created_at_seen):
                        newest_created_at_seen = created_at_dt


                except Exception as e:
                    errors += 1
                    self._log("partial", f"Order failed but import continues: {e}", shopify_id=shopify_order_id, op=op)

            page_info = _get_next_page_info(resp.headers.get("Link"))
            if not page_info:
                break

        # sau khi xử lý orders xong
        if newest_created_at_seen:
            # newest_created_at_seen nên là datetime (không phải string)
            self.last_sync = newest_created_at_seen


        status = "success" if errors == 0 and warnings == 0 else ("partial" if (errors or warnings) else "success")
        self._log(
            status,
            f"Order import finished. created={created}, skipped={skipped}, warnings={warnings}, errors={errors}",
            op=op,
        )
        return {"created": created, "updated": 0, "errors": errors}     # Trả về giá trị cho wizard dùng đồng bộ order không cần update

    @api.model
    def cron_import_orders(self):
        configs = self.env["shopify.integration.config"].search([("active", "=", True)])
        for cfg in configs:
            cfg.import_orders()
        return True