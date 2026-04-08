{
    'name': 'Academy Management',
    'version': '19.0.1.0.0',
    'category': 'Education',
    'summary': 'Quản lý khóa học và sinh viên',
    'description': 'Module thực hành Odoo - Models & Fields',
    'author': 'Bạn',
    'depends': ['base'],
    'data': [
        'views/academy_menus.xml',
        'views/course_views.xml',
        'views/student_views.xml',
    ],
    'license': 'LGPL-3',          # ← Thêm dòng này
    'installable': True,
    'application': True,
}