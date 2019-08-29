# -*- coding: utf-8 -*-


from odoo import fields, models


# Model: maintenance.work.item
# Danh mục nội dung công việc trong Qui định Bảo trì - Bảo dưỡng
class WorkItem(models.Model):
    _name = 'maintenance.work.item'

    name = fields.Text('Work Item')
    work_type = fields.Selection([(0, 'Cơ khí'), (1, 'Điện')],
                             string='Work Type',
                             default=0)
    time = fields.Integer('Time Minutes')
    description = fields.Text('Description')


# Model: mes.factory
# Danh mục Phân xưởng
class Factory(models.Model):
    _name = "mes.factory"

    name = fields.Char("Factory Name")
    parent_id = fields.Many2one('mes.factory', 'Parent')
    description = fields.Text("Description")


# Model: mes.factorproviderytem
# Danh mục nhà cung cấp Thiết bị/ máy móc
class Provider(models.Model):
    _name = "mes.provider"

    name = fields.Char("Nhà cung cấp")
    country = fields.Many2one(comodel_name="res.country", string="Quốc gia")
    description = fields.Text("Ghi chú")
