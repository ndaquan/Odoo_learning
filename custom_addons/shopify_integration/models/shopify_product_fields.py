from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template" # Kế thừa model có sẵn của odoo: Đây là sản phẩm chính/Template

    x_shopify_product_id = fields.Char(index=True) # Field bắt đầu bằng x_ là field tùy chỉnh của dev: Thêm trường mới vào model và tạo index trong database


class ProductProduct(models.Model):
    _inherit = "product.product" # Mở rộng model quản lý sản phẩm biến thể/Variant

    x_shopify_variant_id = fields.Char(index=True) # Dùng index khi liên quan tới field hay dùng để tìm kiếm, lọc, so sánh,...
    x_shopify_price = fields.Float(string="Shopify Price")
    x_shopify_inventory_item_id = fields.Char(index=True)

class SaleOrder(models.Model):
    _inherit = "sale.order"
    
    x_shopify_order_id = fields.Char(index=True)