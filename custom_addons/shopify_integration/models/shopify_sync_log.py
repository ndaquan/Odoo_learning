from odoo import api, fields, models

class ShopifySyncLog(models.Model):
    _name = "shopify.sync.log"          # Têm model chính thức dùng ở nhiều nơi
    _description = "Shopify Sync Log"
    _order = "create_date desc"         # Sắp xếp mặc định theo create_date giảm dần -> log mới nhất sẽ hiện trên cùng

    config_id = fields.Many2one("shopify.integration.config", required=True, ondelete="restrict")       # ondelet="restrict": Nếu xóa 1 config thì không cho phép xóa nếu còn log liên quan
    sync_type = fields.Selection(
        [("test", "Test"), ("production", "Production"), ("inventory", "Inventory"), ("order", "Order")],
        required=True,
    )       # Selection: List các tuple (giá_trị_lưu_DB, nhãn_hiển_thị)
    status = fields.Selection(
        [("success", "Success"), ("partial", "Partial"), ("failed", "Failed")],
        required=True,
    )
    message = fields.Text(required=True)
    shopify_id = fields.Char()
    operation_ref = fields.Char(index=True)

    # Tạo function để sau này truyền dữ liệu vào
    @api.model      # Method thuộc về Model, 0 phụ thuộc vào recordset
    def create_log(self, config, sync_type, status, message, shopify_id=None, operation_ref=None):      # self k phải là bản ghi mà là class Model  |   Truyền None để cho hàm linh hoạt hơn vì không phải lúc nào cũng đều có shopify_id và operation_ref nên nếu không có thì cứ để trống thay vì phải khai báo None
        return self.create({
            "config_id": config.id,     # kiểu Many2one chỉ nhận giá trị là id số nguyên
            "sync_type": sync_type,
            "status": status,
            "message": message,
            "shopify_id": shopify_id,
            "operation_ref": operation_ref,
        })