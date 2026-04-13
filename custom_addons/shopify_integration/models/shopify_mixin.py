import json
import time
from urllib.parse import urljoin

import requests

from odoo import _
from odoo.exceptions import UserError

class ShopifyApiMixin:      # Mixin : Dùng khi muốn trộn 1 chức năng/style vào nhiều class khác nhau khác với inheritance dùng khi có mối quan hệ "is-a"
    """
    Mixin thuần Python (không phải model) để tái sử dụng logic gọi API.
    Chỉ config model sẽ kế thừa và expose method này
    """

    def _shopify_request(self, method, path, params=None, payload=None, timeout=30, max_retries=3, return_response=False,):     # path là đường dẫn API chứa tên endpoint (product.json) của phần sau URL   |   params thường dùng với GET để lấy dữ liệu |   payload thường dùng với những phương thức còn lại để gửi dữ liệu JSON bên trong request
        self.ensure_one()       # Một method có sẵn của Odoo với mục đích là kiểm tra recordset self và buộc phải chỉ có đúng 1 bản ghi. 0 thỏa mãn thì ngay lập tức raise lỗi

        self._ensure_access_token()

        base = (self.shop_url or "").rstrip("/") + "/"      # rstrip("/"): Xóa dấu / thừa ở cuối (nếu có)
        api_version = (self.api_version or "2026-04").strip()       # strip: Xóa khoảng trắng (space, tab, xuống dòng) ở đầu và cuối chuỗi
        api_base = urljoin(base, f"admin/api/{api_version}/")      # urljoin: Hàm an toàn để ghép URL
        url = urljoin(api_base, path.lstrip("/"))       

        headers = {
            "X-Shopify-Access-Token": self.access_token or "",
            "Content-Type": "application/json",
            "Accept": "application/json",       # Chuẩn bắt buộc của Shopify REST Admin API
        }
        
        last_err = None     # Tạo biến để lưu lỗi cuối cùng gặp phải
        for attempt in range(max_retries + 1):
            try:
                resp = requests.request(        # Dùng request là hàm duy nhất hỗ trợ truyền các method (GET, POST, PUT, ...) tự do thay vì dùng request.get hoặc post chỉ được 1 cái
                    method=method.upper(),
                    url=url,
                    headers=headers,
                    params=params,
                    data=json.dumps(payload) if payload is not None else None,
                    timeout=timeout,
                )

                if resp.status_code in (401, 403) and attempt < max_retries:
                    self._refresh_access_token()
                    headers["X-Shopify-Access-Token"] = self.access_token or ""
                    continue

                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    sleep_s = int(retry_after) if (retry_after and retry_after.isdigit()) else 2        # isdigit: kiểm tra xem chuỗi có toàn bộ là chữ số không
                    time.sleep(sleep_s)
                    continue

                if 500 <= resp.status_code < 600 and attempt < max_retries:
                    time.sleep(1 + attempt)
                    continue

                if resp.status_code >= 400:
                    raise UserError(_("Shopify API error %s: %s") % (resp.status_code, resp.text[:500]))
                
                data = resp.json() if resp.content else {}
                return (data, resp) if return_response else data
            
            except Exception as e:
                last_err = e
                if attempt < max_retries:
                    time.sleep(1 + attempt)
                    continue
                raise last_err