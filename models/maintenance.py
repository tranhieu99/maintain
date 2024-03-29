# -*- coding: utf-8 -*-

from datetime import date, datetime, timedelta
import qrcode
from odoo import api, fields, models, SUPERUSER_ID, _
from odoo.exceptions import UserError
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT
import base64
import binascii


class MaintenanceStage(models.Model):
    """ Model for case stages. This models the main stages of a Maintenance Request management flow. """

    _name = 'maintenance.stage'
    _description = 'Maintenance Stage'
    _order = 'sequence, id'

    name = fields.Char('Name', required=True, translate=True)
    sequence = fields.Integer('Sequence', default=20)
    fold = fields.Boolean('Folded in Maintenance Pipe')
    done = fields.Boolean('Request Done')


class MaintenanceEquipmentCategory(models.Model):
    _name = 'maintenance.equipment.category'
    _inherit = ['mail.alias.mixin', 'mail.thread']
    _description = 'Asset Category'

    @api.one
    @api.depends('equipment_ids')
    def _compute_fold(self):
        self.fold = False if self.equipment_count else True

    name = fields.Char('Category Name', required=True, translate=True)
    technician_user_id = fields.Many2one('res.users', 'Responsible', track_visibility='onchange',
                                         default=lambda self: self.env.uid, oldname='user_id')
    color = fields.Integer('Color Index')
    note = fields.Text('Comments', translate=True)
    equipment_ids = fields.One2many('maintenance.equipment', 'category_id', string='Equipments', copy=False)
    equipment_count = fields.Integer(string="Equipment", compute='_compute_equipment_count')
    maintenance_ids = fields.One2many('maintenance.request', 'category_id', copy=False)
    maintenance_count = fields.Integer(string="Maintenance", compute='_compute_maintenance_count')
    alias_id = fields.Many2one(
        'mail.alias', 'Alias', ondelete='restrict', required=True,
        help="Email alias for this equipment category. New emails will automatically "
             "create new maintenance request for this equipment category.")
    fold = fields.Boolean(string='Folded in Maintenance Pipe', compute='_compute_fold', store=True)

    @api.multi
    def _compute_equipment_count(self):
        equipment_data = self.env['maintenance.equipment'].read_group([('category_id', 'in', self.ids)],
                                                                      ['category_id'], ['category_id'])
        mapped_data = dict([(m['category_id'][0], m['category_id_count']) for m in equipment_data])
        for category in self:
            category.equipment_count = mapped_data.get(category.id, 0)

    @api.multi
    def _compute_maintenance_count(self):
        maintenance_data = self.env['maintenance.request'].read_group([('category_id', 'in', self.ids)],
                                                                      ['category_id'], ['category_id'])
        mapped_data = dict([(m['category_id'][0], m['category_id_count']) for m in maintenance_data])
        for category in self:
            category.maintenance_count = mapped_data.get(category.id, 0)

    @api.model
    def create(self, vals):
        self = self.with_context(alias_model_name='maintenance.request', alias_parent_model_name=self._name)
        if not vals.get('alias_name'):
            vals['alias_name'] = vals.get('name')
        category_id = super(MaintenanceEquipmentCategory, self).create(vals)
        category_id.alias_id.write(
            {'alias_parent_thread_id': category_id.id, 'alias_defaults': {'category_id': category_id.id}})
        return category_id

    @api.multi
    def unlink(self):
        MailAlias = self.env['mail.alias']
        for category in self:
            if category.equipment_ids or category.maintenance_ids:
                raise UserError(
                    _("You cannot delete an equipment category containing equipments or maintenance requests."))
            MailAlias += category.alias_id
        res = super(MaintenanceEquipmentCategory, self).unlink()
        MailAlias.unlink()
        return res

    def get_alias_model_name(self, vals):
        return vals.get('alias_model', 'maintenance.equipment')

    def get_alias_values(self):
        values = super(MaintenanceEquipmentCategory, self).get_alias_values()
        values['alias_defaults'] = {'category_id': self.id}
        return values


class MaintenanceEquipmentGroup(models.Model):
    _name = 'maintenance.equipment.group'

    name = fields.Char('Equipment Group')
    description = fields.Text('Description')


class MaintenanceEquipment(models.Model):
    _name = 'maintenance.equipment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Equipment'

    @api.multi
    def _track_subtype(self, init_values):
        self.ensure_one()
        if 'owner_user_id' in init_values and self.owner_user_id:
            return 'maintenance.mt_mat_assign'
        return super(MaintenanceEquipment, self)._track_subtype(init_values)

    @api.multi
    def name_get(self):
        result = []
        for record in self:
            if record.name and record.serial_no:
                result.append((record.id, record.name + '/' + record.serial_no))
            if record.name and not record.serial_no:
                result.append((record.id, record.name))
        return result

    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        args = args or []
        recs = self.browse()
        if name:
            recs = self.search([('name', '=', name)] + args, limit=limit)
        if not recs:
            recs = self.search([('name', operator, name)] + args, limit=limit)
        return recs.name_get()

    # Image/QR code/Data Sheet Attachment
    image = fields.Binary(string="Hình ảnh",  attachment=True)    
    qr_code = fields.Binary(string="Mã QR",  attachment=True)
    data_sheet = fields.Binary(string="Data Sheet",  attachment=True)
    filename = fields.Char(string='File')
    #
    name = fields.Char('Equipment Name', required=True, translate=True)
    # Active=True: Đang hoạt động
    active = fields.Boolean(default=True, string='Hoạt động')
    #
    technician_user_id = fields.Many2one('res.users', string='Technician', track_visibility='onchange',
                                         oldname='user_id')
    owner_user_id = fields.Many2one('res.users', string='Owner', track_visibility='onchange')
    # Nhóm Máy móc/ Thiết bị
    group_id = fields.Many2one('maintenance.equipment.group', string='Equipment Group')
    # Loại Máy móc/ Thiết bị
    category_id = fields.Many2one('maintenance.equipment.category', string='Equipment Category',
                                  track_visibility='onchange', group_expand='_read_group_category_ids')

    partner_id = fields.Many2one('res.partner', string='Vendor', domain="[('supplier', '=', 1)]")
    # Mã Máy móc/Thiết bị
    partner_ref = fields.Char('Vendor Reference')
    location = fields.Char('Location')
    model = fields.Char('Model')
    # Ký hiệu/ Serial Number
    serial_no = fields.Char('Serial Number', copy=False)
    #
    assign_date = fields.Date('Assigned Date', track_visibility='onchange')
    cost = fields.Float('Cost')
    note = fields.Text('Note')
    #
    warranty = fields.Date('Warranty')
    color = fields.Integer('Color Index')
    #
    scrap_date = fields.Date('Scrap Date')
    maintenance_ids = fields.One2many('maintenance.request', 'equipment_id')
    maintenance_count = fields.Integer(compute='_compute_maintenance_count', string="Maintenance", store=True)
    maintenance_open_count = fields.Integer(compute='_compute_maintenance_count', string="Current Maintenance",
                                            store=True)
    period = fields.Integer('Days between each preventive maintenance')
    next_action_date = fields.Date(compute='_compute_next_maintenance',
                                   string='Date of the next preventive maintenance', store=True)
    maintenance_team_id = fields.Many2one('maintenance.team', string='Maintenance Team')
    maintenance_duration = fields.Float(help="Maintenance Duration in hours.")

    # Bổ sung trường dữ liệu quản lý Máy móc/Thiết bị
    time_db = fields.Integer(string='Time DB')
    time_offset = fields.Integer(string='Time Offset')
    alarm_db = fields.Integer(string='Alarm DB')
    alarm_offset = fields.Integer(string='Alarm Offset')

    factory_id = fields.Many2one(comodel_name='mes.factory', string='Factory')
    provider_id = fields.Many2one(comodel_name='mes.provider', string='Provider')

    # Liên kết với Tiêu chí vận hành: mes.energy.criteria
    # energy_criteria_line_ids = fields.One2many('mes.energy.config.line', 'maintenance_equipment_id', 'Energy Criteria')

    # Thiết bị/ Máy móc có nhập thông số Năng lượng, Vận hành
    is_energy_monitor = fields.Selection([(0, 'Không'), (1, 'Có')],
                                         string='Is Energy Monitor',
                                         default=0)
    # Cấu hình Qui định Bảo trì - Bảo dưỡng cho từng máy móc
    maintenance_regulation_ids = fields.One2many('maintenance.work.item.line', 'equipment_id', 'Maintenance Work Items')
    maintenance_request = fields.One2many(comodel_name="MaintenanceRequest", inverse_name="MaintenanceEquipment", string="Yêu cầu bảo trì", required=False, )
    @api.depends('period', 'maintenance_ids.request_date', 'maintenance_ids.close_date')
    def _compute_next_maintenance(self):

        date_now = fields.Date.context_today(self)
        for equipment in self.filtered(lambda x: x.period > 0):
            next_maintenance_todo = self.env['maintenance.request'].search([
                ('equipment_id', '=', equipment.id),
                ('maintenance_type', '=', 'preventive'),
                ('stage_id.done', '!=', True),
                ('close_date', '=', False)], order="request_date asc", limit=1)
            last_maintenance_done = self.env['maintenance.request'].search([
                ('equipment_id', '=', equipment.id),
                ('maintenance_type', '=', 'preventive'),
                ('stage_id.done', '=', True),
                ('close_date', '!=', False)], order="close_date desc", limit=1)
            if next_maintenance_todo and last_maintenance_done:
                next_date = next_maintenance_todo.request_date
                date_gap = fields.Date.from_string(next_maintenance_todo.request_date) - fields.Date.from_string(
                    last_maintenance_done.close_date)
                # If the gap between the last_maintenance_done and the next_maintenance_todo one is bigger than 2 times the period and next request is in the future
                # We use 2 times the period to avoid creation too closed request from a manually one created
                if date_gap > timedelta(0) and date_gap > timedelta(
                        days=equipment.period) * 2 and fields.Date.from_string(
                    next_maintenance_todo.request_date) > fields.Date.from_string(date_now):
                    # If the new date still in the past, we set it for today
                    if fields.Date.from_string(last_maintenance_done.close_date) + timedelta(
                            days=equipment.period) < fields.Date.from_string(date_now):
                        next_date = date_now
                    else:
                        next_date = fields.Date.to_string(
                            fields.Date.from_string(last_maintenance_done.close_date) + timedelta(
                                days=equipment.period))
            elif next_maintenance_todo:
                next_date = next_maintenance_todo.request_date
                date_gap = fields.Date.from_string(next_maintenance_todo.request_date) - fields.Date.from_string(
                    date_now)
                # If next maintenance to do is in the future, and in more than 2 times the period, we insert an new request
                # We use 2 times the period to avoid creation too closed request from a manually one created
                if date_gap > timedelta(0) and date_gap > timedelta(days=equipment.period) * 2:
                    next_date = fields.Date.to_string(
                        fields.Date.from_string(date_now) + timedelta(days=equipment.period))
            elif last_maintenance_done:
                next_date = fields.Date.from_string(last_maintenance_done.close_date) + timedelta(days=equipment.period)
                # If when we add the period to the last maintenance done and we still in past, we plan it for today
                if next_date < fields.Date.from_string(date_now):
                    next_date = date_now
            else:
                next_date = fields.Date.to_string(fields.Date.from_string(date_now) + timedelta(days=equipment.period))

            equipment.next_action_date = next_date

    @api.one
    @api.depends('maintenance_ids.stage_id.done')
    def _compute_maintenance_count(self):
        self.maintenance_count = len(self.maintenance_ids)
        self.maintenance_open_count = len(self.maintenance_ids.filtered(lambda x: not x.stage_id.done))

    @api.onchange('category_id')
    def _onchange_category_id(self):
        self.technician_user_id = self.category_id.technician_user_id

    _sql_constraints = [
        ('serial_no', 'unique(serial_no)', "Another asset already exists with this serial number!"),
    ]

    @api.model
    def create(self, vals):
        equipment = super(MaintenanceEquipment, self).create(vals)
        if equipment.owner_user_id:
            equipment.message_subscribe_users(user_ids=[equipment.owner_user_id.id])
        return equipment

    @api.multi
    def write(self, vals):
        if vals.get('owner_user_id'):
            self.message_subscribe_users(user_ids=[vals['owner_user_id']])
        return super(MaintenanceEquipment, self).write(vals)

    @api.model
    def _message_get_auto_subscribe_fields(self, updated_fields, auto_follow_fields=None):
        """ mail.thread override so user_id which has no special access allowance is not
            automatically subscribed.
        """
        if auto_follow_fields is None:
            auto_follow_fields = []
        return super(MaintenanceEquipment, self)._message_get_auto_subscribe_fields(updated_fields, auto_follow_fields)
    # qr code hieu 05/08/2019
    @api.model
    def create(self,vals):
        def createQrCode(serial):
            qr = qrcode.QRCode(
            version=1,
            box_size=10,
            border=1)
            qr.add_data(serial)
            qr.make(fit=True)
            output = qr.make_image(fill_color="black", back_color="white")
            outputPng = f"/Users/a365/Downloads/odoo-12.0/addons/maintenance/static/qrcode/{serial}.png"
            output.save(outputPng)
            fin = open(outputPng, "rb")
            data = fin.read()
            equipment['qr_code'] = binascii.b2a_base64(data)
            print(equipment['qr_code'])
            fin.close()
        equipment = super(MaintenanceEquipment,self).create(vals)
        if(equipment):
            createQrCode(equipment['serial_no'])
            return equipment

    @api.model
    def _read_group_category_ids(self, categories, domain, order):
        """ Read group customization in order to display all the categories in
            the kanban view, even if they are empty.
        """
        category_ids = categories._search([], order=order, access_rights_uid=SUPERUSER_ID)
        return categories.browse(category_ids)

    def _create_new_request(self, date):
        self.ensure_one()
        self.env['maintenance.request'].create({
            'name': _('Preventive Maintenance - %s') % self.name,
            'request_date': date,
            'schedule_date': date,
            'category_id': self.category_id.id,
            'equipment_id': self.id,
            'maintenance_type': 'preventive',
            'owner_user_id': self.owner_user_id.id,
            'technician_user_id': self.technician_user_id.id,
            'maintenance_team_id': self.maintenance_team_id.id,
            'duration': self.maintenance_duration,
        })

    @api.model
    def _cron_generate_requests(self):
        """
            Generates maintenance request on the next_action_date or today if none exists
        """
        for equipment in self.search([('period', '>', 0)]):
            next_requests = self.env['maintenance.request'].search([('stage_id.done', '=', False),
                                                                    ('equipment_id', '=', equipment.id),
                                                                    ('maintenance_type', '=', 'preventive'),
                                                                    ('request_date', '=', equipment.next_action_date)])
            if not next_requests:
                equipment._create_new_request(equipment.next_action_date)


# Model: maintenance.request
# Phiếu yêu cầu Bảo trì - Bảo dưỡng
class MaintenanceRequest(models.Model):
    _name = 'maintenance.request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Maintenance Requests'
    _order = "id desc"

    @api.returns('self')
    def _default_stage(self):
        return self.env['maintenance.stage'].search([], limit=1)

    @api.multi
    def _track_subtype(self, init_values):
        self.ensure_one()
        if 'stage_id' in init_values and self.stage_id.sequence <= 1:
            return 'maintenance.mt_req_created'
        elif 'stage_id' in init_values and self.stage_id.sequence > 1:
            return 'maintenance.mt_req_status'
        return super(MaintenanceRequest, self)._track_subtype(init_values)

    def _get_default_team_id(self):
        return self.env.ref('maintenance.equipment_team_maintenance', raise_if_not_found=False)

    # name = fields.Char('Subjects', required=True, readonly=True)
    name = fields.Char('Subjects', readonly=True)
    description = fields.Text('Description')
    request_date = fields.Date('Request Date', track_visibility='onchange', default=fields.Date.context_today,
                               help="Date requested for the maintenance to happen")
    owner_user_id = fields.Many2one('res.users', string='Created by', default=lambda s: s.env.uid)
    category_id = fields.Many2one('maintenance.equipment.category', related='equipment_id.category_id',
                                  string='Category', store=True, readonly=True)
    equipment_id = fields.Many2one('maintenance.equipment', string='Equipment', index=True)
    technician_user_id = fields.Many2one('res.users', string='Owner', track_visibility='onchange', oldname='user_id')
    stage_id = fields.Many2one('maintenance.stage', string='Stage', track_visibility='onchange',
                               group_expand='_read_group_stage_ids', default=_default_stage)
    priority = fields.Selection([('0', 'Very Low'), ('1', 'Low'), ('2', 'Normal'), ('3', 'High')], string='Priority')
    color = fields.Integer('Color Index')
    close_date = fields.Date('Close Date', help="Date the maintenance was finished.")
    kanban_state = fields.Selection(
        [('normal', 'In Progress'), ('blocked', 'Blocked'), ('done', 'Ready for next stage')],
        string='Kanban State', required=True, default='normal', track_visibility='onchange')
    # active = fields.Boolean(default=True, help="Set active to false to hide the maintenance request without deleting it.")
    archive = fields.Boolean(default=False,
                             help="Set archive to true to hide the maintenance request without deleting it.")
    # Phân biệt Sự cố & Bảo trì - Bảo dưỡng
    # maintenance_type = fields.Selection([(0, 'Maintenance'), (1, 'Incident')], string='Maintenance Type', default=0)
    request_type = fields.Selection([(0, 'Bảo dưỡng'), (1, 'Sự cố'), (2, 'Sửa chữa')], string='Request Type', default=0)
    maintenance_type = fields.Many2one('maintenance.type', string='Maintenance Type')
    maintenance_group = fields.Char('Maintenance Group', default=None)
    #
    schedule_date = fields.Date('Scheduled Date',
                                help="Date the maintenance team plans the maintenance. It should not differ much from the Request Date.",
                                required=True)
    maintenance_team_id = fields.Many2one('maintenance.team', string='Team', required=True,
                                          default=_get_default_team_id)
    duration = fields.Float(help="Duration in minutes and seconds.")

    # Công việc thực hiện theo qui định

    work_item_id = fields.Many2one('maintenance.work.item', string='Maintenance Work Item')
    # Công việc khác
    maintenance_work = fields.Text('Maintenance Other Work')

    # Phân biệt Sự cố & Bảo trì - Bảo dưỡng
    # is_maintenance = fields.Boolean(help='To recognize Issue or Maintenance.')

    @api.onchange('maintenance_type')
    def get_maintenance_group(self):
        # self.maintenance_group = ''
        if self.maintenance_type is not None:
            t = ((0, 'Sự cố'), (1, 'Định kỳ'), (2, 'Không định kỳ'), (3, 'Sửa chữa'), (4, 'Hiệu chuẩn'))
            group_id = self.maintenance_type.group
            for i in t:
                if group_id == i[0]:
                    self.maintenance_group = i[1]

    @api.multi
    def archive_equipment_request(self):
        self.write({'archive': True})

    @api.multi
    def reset_equipment_request(self):
        """ Reinsert the maintenance request into the maintenance pipe in the first stage"""
        first_stage_obj = self.env['maintenance.stage'].search([], order="sequence asc", limit=1)
        # self.write({'active': True, 'stage_id': first_stage_obj.id})
        self.write({'archive': False, 'stage_id': first_stage_obj.id})

    @api.onchange('equipment_id')
    def onchange_equipment_id(self):
        if self.equipment_id:
            self.technician_user_id = self.equipment_id.technician_user_id if self.equipment_id.technician_user_id else self.equipment_id.category_id.technician_user_id
            self.category_id = self.equipment_id.category_id
            if self.equipment_id.maintenance_team_id:
                self.maintenance_team_id = self.equipment_id.maintenance_team_id.id

    @api.onchange('category_id')
    def onchange_category_id(self):
        if not self.technician_user_id or not self.equipment_id or (
                self.technician_user_id and not self.equipment_id.technician_user_id):
            self.technician_user_id = self.category_id.technician_user_id

    @api.model
    def create(self, vals):
        # Thuclt added 2019-05-09: Auto gen Name
        seq = self.env['ir.sequence'].next_by_code('maintenance.request') or 'PBTBD'
        vals['name'] = seq

        # context: no_log, because subtype already handle this
        self = self.with_context(mail_create_nolog=True)
        request = super(MaintenanceRequest, self).create(vals)
        if request.owner_user_id or request.technician_user_id:
            request._add_followers()
        if request.equipment_id and not request.maintenance_team_id:
            request.maintenance_team_id = request.equipment_id.maintenance_team_id

        return request

    @api.multi
    def write(self, vals):
        # Overridden to reset the kanban_state to normal whenever
        # the stage (stage_id) of the Maintenance Request changes.
        if vals and 'kanban_state' not in vals and 'stage_id' in vals:
            vals['kanban_state'] = 'normal'
        res = super(MaintenanceRequest, self).write(vals)
        if vals.get('owner_user_id') or vals.get('technician_user_id'):
            self._add_followers()
        # Add by thuclt on 13-05-2019: Set close_date when change stage to done
        if self.stage_id.done and 'stage_id' in vals:
            self.write({'close_date': fields.Date.today()})
        return res

    def _add_followers(self):
        for request in self:
            user_ids = (request.owner_user_id + request.technician_user_id).ids
            request.message_subscribe_users(user_ids=user_ids)

    @api.model
    def _read_group_stage_ids(self, stages, domain, order):
        """ Read group customization in order to display all the stages in the
            kanban view, even if they are empty
        """
        stage_ids = stages._search([], order=order, access_rights_uid=SUPERUSER_ID)
        return stages.browse(stage_ids)


class MaintenanceTeam(models.Model):
    _name = 'maintenance.team'
    _description = 'Maintenance Teams'

    name = fields.Char(required=True, translate=True)
    member_ids = fields.Many2many('res.users', 'maintenance_team_users_rel', string="Team Members")
    color = fields.Integer("Color Index", default=0)
    request_ids = fields.One2many('maintenance.request', 'maintenance_team_id', copy=False)
    equipment_ids = fields.One2many('maintenance.equipment', 'maintenance_team_id', copy=False)

    # For the dashboard only
    todo_request_ids = fields.One2many('maintenance.request', string="Requests", copy=False,
                                       compute='_compute_todo_requests')
    todo_request_count = fields.Integer(string="Number of Requests", compute='_compute_todo_requests')
    todo_request_count_date = fields.Integer(string="Number of Requests Scheduled", compute='_compute_todo_requests')
    todo_request_count_high_priority = fields.Integer(string="Number of Requests in High Priority",
                                                      compute='_compute_todo_requests')
    todo_request_count_block = fields.Integer(string="Number of Requests Blocked", compute='_compute_todo_requests')
    todo_request_count_unscheduled = fields.Integer(string="Number of Requests Unscheduled",
                                                    compute='_compute_todo_requests')

    @api.one
    @api.depends('request_ids.stage_id.done')
    def _compute_todo_requests(self):
        self.todo_request_ids = self.request_ids.filtered(lambda e: e.stage_id.done == False)
        self.todo_request_count = len(self.todo_request_ids)
        self.todo_request_count_date = len(self.todo_request_ids.filtered(lambda e: e.schedule_date != False))
        self.todo_request_count_high_priority = len(self.todo_request_ids.filtered(lambda e: e.priority == '3'))
        self.todo_request_count_block = len(self.todo_request_ids.filtered(lambda e: e.kanban_state == 'blocked'))
        self.todo_request_count_unscheduled = len(self.todo_request_ids.filtered(lambda e: not e.schedule_date))

    @api.one
    @api.depends('equipment_ids')
    def _compute_equipment(self):
        self.equipment_count = len(self.equipment_ids)


# Model: maintenance.type
# Loại Bảo trì - Bảo dưỡng
class MaintenanceType(models.Model):
    _name = 'maintenance.type'

    name = fields.Char('Name')
    group = fields.Selection([(0, 'Sự cố'), (1, 'Định kỳ'), (2, 'Không định kỳ'), (3, 'Sửa chữa'), (4, 'Hiệu chuẩn')],
                             string='Group',
                             default=0)
    # description = fields.Text('Description')


# Model: maintenance.work.item.line
# Cấu hình Qui định Bảo trì - Bảo dưỡng máy móc
class MaintenanceWorkItemLine(models.Model):
    _name = 'maintenance.work.item.line'

    equipment_id = fields.Many2one('maintenance.equipment')
    work_item_id = fields.Many2one('maintenance.work.item', 'Maintenance Work Items')
    maintenance_type = fields.Many2one('maintenance.type', 'Maintenance Type')
    # Ngày thực hiện công việc bảo trì gần đây nhất
    updated = fields.Date('Updated')
