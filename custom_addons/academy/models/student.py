from odoo import models, fields  

class AcademyStudent(models.Model):  
    _name = "academy.student"
    _description = "Sinh viên"

    name = fields.Char(string = "Họ và tên", required = True)
    email = fields.Char(string = "Email")
    phone = fields.Char(string = "Số điện thoại")
    birth_date = fields.Date(string = "Ngày sinh")
    active = fields.Boolean(string = "Hoạt động", default = True)

    course_id = fields.Many2one(
        comodel_name = 'academy.course',
        string = "Khóa học",
        ondelete = 'restrict'
    )