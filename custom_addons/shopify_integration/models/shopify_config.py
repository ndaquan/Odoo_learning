import uuid

import request

from odoo import fields, models, _
from odoo.exceptions import UserError

from .shopify_mixin import ShopifyApiMixin


class ShopifyIntegrationConfig(models.Model):
    _name = "shopify.integration.config"
    _description = "Shopify Integration Config"

    name = fields.Char(required=True, default="Shopify Store")
    active = fields.Boolean(default=True)

    shop_url = fields.Char(required=True)

    # OAuth client credentials (chỉ nằm trong config model)
    client_id = fields.Char(required=True)
    client_secret = fields.Char(required=True)

    # Access token dùng để call Admin API (hết hạn 24h với client_credentials grant)
    access_token = fields.Char()
    access_token_expires_at = fields.Datetime()

    api_version = fields.Char(required=True, default="2026-04")
    warehouse_id = fields.Many2one("stock.warehouse", require=True)
    last_sync = fields.Datetime()

    def _refresh_access_token(self):
        """Xin token mới bằng client credentials grant và lưu vào config."""
        self.ensure_one()

        url = (self.shop_url or "").rstrip("/") + "/admin/oauth/access_token"
        try:
            resp = requests.post(       # Gửi request POST đến Shopify để xin token mới
                url,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id or "",
                    "client_secret": self.client_secret or "",
                },
                timeout=30,
            )
        except Exception as e:
            raise UserError(_("Token refresh request failed: %s") % e)
        
        if resp.status_code >= 400:
            raise UserError(_("Token refresh failed %s: %s") % (resp.status_code, resp.text[:500]))
        
        data = resp.json() if resp.content else {}
        token = data.get("access_token")
        expires_in = int(data.get("expires_in") or 0)  # thường 86399: 24h

        if not token:
            raise UserError(_("Token refresh returned no access_token."))
        
        # trừ hao 2 phút để tránh sát giờ
        expires_at = fields.Datetime.now()
        if expires_in:
            expires_at = fields.Datetime.add(expires_at, seconds=max(expires_in - 120, 0))      # Đẩm bảo kết quả của số giây trừ đi 2 phút là không âm để cộng thêm vào thời gian vào 1 Datetime

        self.write({        # Cập nhật token mới và thời gian hết hạn vào db
            "access_token": token,
            "access_token_expires_at": expires_at,
        })
        return token
    
    def _ensure_access_token(self):
        """Đảm bảo có token và còn hạn; hết hạn thì refresh."""
        self.ensure_one()
        if not self.access_token or not self.access_token_expires_at:
            return self._refresh_access_token()
        
        # nếu đã/ sắp hết hạn -> refresh
        if fields.Datetime.now() >= self.access_token_expires_at:
            return self._refresh_access_token()
        
        return self.access_token


    def action_test_connection(self):
        self.ensure_one()
        operation_ref = str(uuid.uuid4())       # Tạo ID cho mỗi một lần test, để sau này tra cứu dễ dàng hơn
        log = self.env["shopify.sync.log"]      # Lấy model reference trỏ đến model shopify_sync_log (chỉ lấy đối tượng không lấy dữ liệu)

        try:
            data, resp = self._shopify_request("GET", "shop.json", return_response=True)        # Truyền method và path qua hàm _shopify_request.   |   Dùng return_response=True để có thể lấy về 2 giá trị theo thứ tự data, resp    |    data: dữ liệu JSON còn resp sẽ chứa status hoặc những cái khác (header)
            shop_name = (data.get("shop") or {}).get("name") or "Unknown"       # Lấy key "shop" nếu không có thì thay bằng dict rỗng và lấy tên cửa hàng từ việc GET JSON response ở trên

            used_version = resp.headers.get("X-Shopify-API-Version")        # Lấy header đặc biệt mà Shopify trả về
            if used_version and used_version != self.api_version:       # Nếu có used_version và khác với self.api_version 
                log.create_log(
                    self,
                    "test",
                    "partial",
                    f"Connection OK. Shop: {shop_name}. "
                    f"Warning: Shopify responded with API version {used_version} (fell foward from {self.api_version}).",
                    operation_ref=operation_ref,        # operation_ref : mã định danh duy nhất được tạo ra ở phía trên và truyền qua cho log
                )
            else:
                log.create_log(
                    self,
                    "test",
                    "success",
                    f"Connection OK. Shop: {shop_name}. API version: {used_version or self.api_version}",
                    operation_ref=operation_ref,
                )
            return True 
        except Exception as e:      # Nếu có lỗi bất kì thì nhảy vào đây tạo log
            log.create_log(self, "test", "failed", f"Connection FAILED: {e}", operation_ref=operation_ref)
            raise UserError(_("Test connection failed: %s") % e)        # Hiện popup lỗi màu đỏ cho người dùng với nội dung
        

    # method trung tâm (mọi nơi khác chỉ gọi cái này): Wrapper
    def _shopify_request(       # method giống với bên mixin nhưng chỉ có vai trò là wrapper(lớp bọc) - làm nhiệm vụ chuyển tiếp cho các chỗ khác trong module dễ gọi thôi
        self,
        method,
        path,
        params=None,
        payload=None,
        timeout=30,
        max_retries=3,
        return_response=False,      # Chỉ trả về data còn true khi muốn trả về data và resp
    ):
        return ShopifyApiMixin._shopify_request(        # Phần cốt lõi của wrapper, thay vì tự viết logic nó chuyển tiếp toàn bộ công việc sang hàm thật trong mixin
            self,       # Truyền nguyên self (record config) vào mixin để có thể dùng được self.shop_url hoặc access_token,...
            method,
            path,
            params=params,      # Truyền hết giá trị từ wrapper vào cho mixin
            payload=payload,
            timeout=timeout,
            max_retries=max_retries,
            return_response=return_response,
        )