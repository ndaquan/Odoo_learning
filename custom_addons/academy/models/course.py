from odoo import models, fields

class AcademyCourse(models.Model):  
    _name = 'academy.course'
    _description = 'Khóa học'
    
    name = fields.Char(string = "Tên khóa học", required = True)
    description = fields.Text(string = "Mô tả")
    start_date = fields.Date(string = "Ngày bắt đầu")
    duration = fields.Float(string = "Thời lượng (theo giờ)")
    active = fields.Boolean(string = "Hoạt động", default = True)

    student_ids = fields.One2many(
        comodel_name = 'academy.student',
        inverse_name = 'course_id',
        string = "Danh sách sinh viên"
    )