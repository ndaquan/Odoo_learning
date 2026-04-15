import uuid
import re
from html import unescape
from urllib.parse import urlparse, parse_qs

from odoo import api, models


def _strip_html(html):      # Làm sạch dữ liệu sau khi scrap web
    if not html:
        return ""
    text = unescape(html)       # Dùng để giải mã (decode) các ký tự HTML entities (amp;, &lt;, &quot;, &#65;, &copy;, ...) về ký tự thật.) Rất quan trọng khi scrape web (tự động lấy thông tin từ trang web trên Internet) vì hấu hết đều được escape
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)       # Xóa hoàn toàn phần code js
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)         # Xóa hoàn tonaf phần CSS
    text = re.sub(r"<[^>]+>", " ", text)        # Xóa hết tất cả file HTML còn lại
    return re.sub(r"\s+", " ", text).strip()    # Tìm tất cả khoảng trắng và thay thế bằng 1 khoảng trắng duy nhất. 


def _get_next_page_info(link_header):       # Đọc Header Link và trích xuất giá trị page_info của trang tiếp theo
    """
    Shopify REST pagination: Link: <...page_info=XYZ...>; rel="next", <...>; rel="previous"
    """
    if not link_header:
        return None
    for part in link_header.split(","):     # Lấy chuỗi link_header và cắt thành nhiều phần, mỗi lần gặp dấu phẩy thì cắt ra một phần và có được list
        if 'rel="next"' not in part:
            continue        # bỏ qua phần còn lại và chạy vòng lặp tiếp theo
        m = re.search(r"<([^>]+)>", part)   # Dùng regex(re) để tìm đoạn nằm giữa < và > trong phần đó
        if not m:
            continue
        url = m.group(1)        # Lấy nhóm đầu tiên bên trong ngoặc tròn chính là URL sạch. Lí do không lấy group(0) là vì nó sẽ lấy toàn bộ phần khớp (bao gồm cả < và >)
        qs = parse_qs(urlparse(url).query)      # Lấy phần query string (phần tham số bắt đầu bằng dấu ?) và chuyển nó thành dictionary 
        page_info = (qs.get("page_info") or [None])[0]      # Lấy giá trị của tham số page_info (nếu có)
        return page_info
    return None


class ShopifyIntegrationConfig(models.Model):
    _inherit = "shopify.integration.config"

    def sync_products(self):
        self.ensure_one()
        Log = self.env["shopify.sync.log"]          # Trỏ tới model ghi log đồng bộ
        Category = self.env["product.category"]     # Model danh mục
        ProductTmpl = self.env["product.template"]  # Model Sản phẩm chính
        ProductVar = self.env["product.product"]    # Model Variant

        op = str(uuid.uuid4())      # Tạo 1 ID ngẫu nhiên đặc biệt      
        created = updated = 0       # Khởi tạo biến đếm số sản phẩm mới được tạo và số sản phẩm đã tồn tại và được cập nhật trong lần sync này
        errors = 0                  # Đếm số lỗi xảy ra trong quá trình sync

        Log.create_log(self, "product", "success", "Product sync started.", operation_ref=op)   # Gọi hàm create log của model Log | Gắn mã phiên (op) vào log này để sau này nhóm tất cả log của lần sync này lại với nhau

        params = {"limit": 250}     # Mỗi lần gọi API, Shopify chỉ trả về tối đa 250 sản phẩm
        page_info = None            # Cơ chế phân trang của Shopify. Đây là lần gọi đầu tiên chưa có trang tiếp theo

        while True:     
            if page_info:   # Kiếm tra nếu có page_info không (có trang tiếp theo)
                params = {"limit": 250, "page_info": page_info}     # Nếu có thì gán litmit và page_info = trang tiếp theo để sau này dùng GET có thể qua được trang tiếp theo

            try:
                data, resp = self._shopify_request("GET", "products.json", params=params, return_response=True)     #  Gọi hàm shopify_request để gửi request GET đến endpoint "products.json" và truyền params vào, return_resp=True nên có cả (data, resp)    |   (data, resp) ở đây có cùng giá trị với (data, resp) được trả về ở bên hàm _shopify_request
            except Exception as e:      
                errors += 1
                Log.create_log(self, "product", "failed", f"API call failed: {e}", operation_ref=op)
                break

            products = (data or {}).get("products") or []       # Lấy giá trị data của key "products"      
            for p in products:      # Duyệt từng sản phẩm một
                try:
                    shopify_product_id = str(p.get("id") or "")     # Lấy trường id của sản phẩm và chuyển thành chuỗi (vì trường id trong Odoo là kiểu Char nên khi truyền số nguyên vào sẽ dễ lỗi nên mới phải chuyển qua string)
                    name = (p.get("title") or "").strip() or "Shopify Product"  # Lấy tên sản phẩm và xóa khoảng trắng thừa ở đầu và cuối
                    desc = _strip_html(p.get("body_html"))          # Gọi hàm strip_html thành text sạch và lấy mô tả chi tiết của sản phẩm 
                    ptype = (p.get("product_type") or "").strip() or "Shopify"  # Lấy loại sản phẩm

                    categ = Category.search([("name", "=ilike", ptype)], limit=1)       # ilike là kiếm tên gần giống không cần phân biệt chữ hoa thường và chỉ lấy nhiều nhất là 1 danh mục
                    if not categ:       # Dùng search để tìm kiếm thử ptype đó đã có categ tương ứng chưa (nghĩa là có categ.id và name)
                        categ = Category.create({"name": ptype})        # Model category yêu cầu phải có ID, Tên,... nên phải gán tên lấy được từ product_type ở trên và tạo một id mới cho nó. Vì ptype chỉ trả về 1 giá trị text không có id nhưng model thì yêu cầu id và các thông tin khác nữa
                    # Sau khi tạo xong biến categ lúc này sẽ chứa bản ghi mới và có categ.id

                    tmpl = ProductTmpl.search([("x_shopify_product_id", "=", shopify_product_id)], limit=1)     # Tìm sản phẩm theo field đã thêm vào model
                    tmpl_vals = {
                        "name": name,                                   # Tên sản phẩm
                        "description_sale": desc,                       # Mô tả sạch (text thuần)
                        "categ_id": categ.id,                           # ID của danh mục (ở trên)
                        "x_shopify_product_id": shopify_product_id,     # Lưu ID gốc của Shopify
                        "type": "consu",
                        "is_storable": True,
                    }
                    if tmpl:
                        tmpl.write(tmpl_vals)   # Cập nhật lại thông tin và tăng biến updated
                        updated += 1
                    else:
                        tmpl = ProductTmpl.create(tmpl_vals)    # Tạo mới sản phẩm và tăng biến created
                        created += 1

                    for v in (p.get("variants") or []):         # Lấy danh sách biến thể và duyệt từng biến thể một
                        shopify_variant_id = str(v.get("id") or "")             # Lấy Id của biến thể và chuyển thành chuỗi
                        sku = (v.get("sku") or "").strip() or False             # Lấy mã SKU
                        barcode = (v.get("barcode") or "").strip() or False     # Lấy mã vạch   
                        inventory_item_id = str(v.get("inventory_item_id") or "")   # Lấy Id của inventory item
                        try:
                            price = float(v.get("price") or 0.0)                # Lấy giá tiền và chuyển thành số
                        except Exception:
                            price = 0.0

                        var = ProductVar.search([("x_shopify_variant_id", "=", shopify_variant_id)], limit=1)   # Tìm biến thể theo field đã thêm vào model

                        if not var:
                            var = tmpl.product_variant_id

                        var_vals = {
                            "x_shopify_variant_id": shopify_variant_id,     # ID biến thể
                            "x_shopify_inventory_item_id": inventory_item_id or False,  # ID inventory item
                            "default_code": sku,                            # Mã SKU
                            "barcode": barcode,                             # Mã vạch
                            "x_shopify_price": price,                       # Giá tiền
                            "active": True
                        }
                        if var:
                            var.write(var_vals)
                            updated += 1

                except Exception as e:
                    errors += 1
                    Log.create_log(
                        self,
                        "product",
                        "partial",
                        f"Product failed but sync continues: {e}",
                        shopify_id=str((p or {}).get("id") or ""),      # Ghi lại ID của sản phẩm bị lỗi
                        operation_ref=op,
                    )

            page_info = _get_next_page_info(resp.headers.get("Link"))  # resp.headers là một dict chứa tất cả HTTP Headers mà Shopify trả về 
            # Gọi hàm để đọc giá trị trong Link và lấy page_info của trang tiếp theo. Nếu còn page_info thì vòng lặp sẽ tiếp tục và gọi API trang tiếp theo      
            if not page_info:
                break

        status = "success" if errors == 0 else "partial"    
        Log.create_log(
            self,
            "product",
            status,
            f"Product sync finished. created={created}, updated={updated}, errors={errors}",
            operation_ref=op,
        )
        return {"created": created, "updated": updated, "errors": errors}       # Trả về giá trị cho wizard dùng

    @api.model      # Method ở mức model (không cần record cụ thể)
    def cron_sync_products(self):
        configs = self.env["shopify.integration.config"].search([("active", "=", True)])    # Tìm trong bảng tất cả các bản ghi mà trường "Active" trong các cửa hàng Shopify đang được bật
        for cfg in configs:
            cfg.sync_products()
        return True