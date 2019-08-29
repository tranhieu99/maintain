# -*- coding: utf-8 -*-

{
    'name': 'Equipments',
    'version': '1.0',
    'sequence': 125,
    'category': 'Human Resources',
    'author': "Polyco",
    'description': """
        Chức năng quản lý Bảo trì - Bảo dưỡng Thiết bị, Máy móc tại nhà máy.""",
    'depends': ['mail'],
    'summary': 'Equipments, Assets, Internal Hardware, Allocation Tracking',
    'data': [
        'security/maintenance.xml',
        'security/ir.model.access.csv',
        'data/maintenance_data.xml',
        # 'views/maintenance_views.xml',
        'views/equipment_views.xml',
        'views/maintenance_views.xml',
        'views/maintenance_category_views.xml',
        'views/factory_category_view.xml',
        'views/provider_category_view.xml',
        'views/maintenance_templates.xml',
        'views/work_item_views.xml',
        'data/maintenance_cron.xml',
        'data/maintenance_sequence_data.xml',
    ],
    # 'demo': ['data/maintenance_demo.xml'],
    'installable': True,
    'application': True,
}
