# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2024-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: JANISH BABU (<https://www.cybrosys.com>)
#
#    You can modify it under the terms of the GNU AFFERO
#    GENERAL PUBLIC LICENSE (AGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU AFFERO GENERAL PUBLIC LICENSE (AGPL v3) for more details.
#
#    You should have received a copy of the GNU AFFERO GENERAL PUBLIC LICENSE
#    (AGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################
from dateutil.relativedelta import relativedelta
from odoo import api, fields, models, SUPERUSER_ID, _
from odoo.exceptions import UserError


class SubscriptionPackage(models.Model):
    """Subscription Package Model"""
    _name = 'subscription.package'
    _description = 'Subscription Package'
    _rec_name = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    def init(self):
        res = super().init()
        # Clean up stale legacy Enterprise subscription_id references before check_foreign_keys runs
        with self.env.cr.savepoint():
            try:
                self.env.cr.execute("""
                    UPDATE sale_order 
                    SET subscription_id = NULL 
                    WHERE subscription_id IS NOT NULL 
                      AND subscription_id NOT IN (SELECT id FROM subscription_package);

                    UPDATE account_move 
                    SET subscription_id = NULL 
                    WHERE subscription_id IS NOT NULL 
                      AND subscription_id NOT IN (SELECT id FROM subscription_package);
                """)
            except Exception:
                pass
        return res

    @api.model
    def _read_group_stage_ids(self, categories, domain, order):
        """ Read all the stages and display it in the kanban view,
            even if it is empty."""
        category_ids = categories._search([], order=order,
                                          access_rights_uid=SUPERUSER_ID)
        return categories.browse(category_ids)

    def _default_stage_id(self):
        """Setting default stage"""
        rec = self.env['subscription.package.stage'].search([], limit=1,
                                                            order='sequence ASC')
        return rec.id if rec else None

    name = fields.Char(string='Name', default="New", compute='_compute_name',
                       store=True, required=True,
                       help='Choose the name for the subscription package.')
    partner_id = fields.Many2one('res.partner', string='Customer',
                                 help='Select the customer associated with '
                                      'this record.')
    partner_invoice_id = fields.Many2one('res.partner',
                                         help='Select the invoice address '
                                              'associated with this record.',
                                         string='Invoice Address',
                                         related='partner_id')
    partner_shipping_id = fields.Many2one('res.partner',
                                          help="Add shipping/service address",
                                          string='Shipping/Service Address',
                                          related='partner_id')
    plan_id = fields.Many2one('subscription.package.plan',
                              string='Subscription Plan',
                              help="Choose the subscription package plan")
    start_date = fields.Date(string='Period Start Date',
                             help='Add the period start date',
                             ondelete='restrict')
    date_started = fields.Date(string='Subsciption Start date',
                               help='Add the Subscription package start date',
                               ondelete='restrict', readonly=True)
    next_invoice_date = fields.Date(string='Next Invoice Date',
                                    store=True, help='Add next invoice date',
                                    compute="_compute_next_invoice_date",
                                    inverse="_inverse_next_invoice_date")
    company_id = fields.Many2one('res.company', string='Company',
                                 help='Select the company',
                                 default=lambda self: self.env.company,
                                 required=True)
    user_id = fields.Many2one('res.users', string='Sales Person',
                              help='Add the Sales person',
                              default=lambda self: self.env.user)
    sale_order_id = fields.Many2one('sale.order', string="Sale Order",
                                    help='Select the sale order', copy=False)
    is_to_renew = fields.Boolean(string='To Renew', copy=True,
                                 help='Is subscription package is renew')
    tag_ids = fields.Many2many('account.account.tag', string='Tags',
                               help='Add the tags')
    stage_id = fields.Many2one('subscription.package.stage', string='Stage',
                               default=lambda self: self._default_stage_id(),
                               index=True, tracking=True,
                               group_expand='_read_group_stage_ids',
                               help='Subscription Package stage', copy=False)
    invoice_count = fields.Integer(string='Invoices',
                                   help='Subscription package invoice count',
                                   compute='_compute_invoice_count')
    so_count = fields.Integer(string='Sales',
                              help='subscription package sales count',
                              compute='_compute_sale_count')
    description = fields.Text(string='Description',
                              help='Subscription package description')
    analytic_account_id = fields.Many2one('account.analytic.account',
                                          help='Choose the analytic account',
                                          string='Analytic Account')
    product_line_ids = fields.One2many('subscription.package.product.line',
                                       'subscription_id', ondelete='restrict',
                                       string='Products Line',
                                       help='Subscription package product line')
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  readonly=True, default=lambda
            self: self.env.company.currency_id, help='Add Currency')
    current_stage = fields.Char(string='Current Stage', default='Draft',
                                help='Current stage of the subscription package.',
                                store=True, compute='_compute_current_stage')
    reference_code = fields.Char(string='Reference',
                                 help='This field represents the reference code.')
    is_closed = fields.Boolean(string="Closed", default=False,
                               help='Is Closed')
    close_reason_id = fields.Many2one('subscription.package.stop',
                                      string='Close Reason')
    closed_by = fields.Many2one('res.users', string='Closed By')
    close_date = fields.Date(string='Closed on')
    stage_category = fields.Selection(related='stage_id.category', store=True)
    invoice_mode = fields.Selection(related="plan_id.invoice_mode")
    total_recurring_price = fields.Float(string='Untaxed Amount',
                                         compute='_compute_total_recurring_price',
                                         store=True)
    tax_total = fields.Float("Taxes", readonly=True)
    total_with_tax = fields.Monetary("Total Recurring Price", readonly=True)
    recurrence_period_id = fields.Many2one("recurrence.period",
                                           string="Recurrence Period")
    sale_order_count = fields.Integer(string='Sale Order Count')

    def _valid_field_parameter(self, field, name):
        """Check the validity of a field parameter for a specific field."""
        if name == 'ondelete':
            return True
        return super(SubscriptionPackage,
                     self)._valid_field_parameter(field, name)

    @api.depends('sale_order_id')
    def _compute_invoice_count(self):
        """ Calculate Invoice count based on subscription package """
        for rec in self:
            try:
                if rec.exists():
                    count = self.env['account.move'].search_count([('subscription_id', '=', rec.id)])
                    rec.invoice_count = count
                else:
                    rec.invoice_count = 0
            except Exception:
                rec.invoice_count = 0

    @api.depends('sale_order_id')
    def _compute_sale_count(self):
        """ Calculate sale order count based on subscription package """
        for rec in self:
            try:
                if rec.exists():
                    rec.so_count = self.env['sale.order'].search_count([('subscription_id', '=', rec.id)])
                else:
                    rec.so_count = 0
            except Exception:
                rec.so_count = 0

    @api.depends('stage_id')
    def _compute_current_stage(self):
        """ It displays current stage for subscription package """
        for rec in self:
            rec.current_stage = rec.stage_id.category if rec.stage_id else 'Draft'

    @api.depends('start_date', 'plan_id.renewal_time')
    def _compute_next_invoice_date(self):
        """The compute function for the next invoice date"""
        for sub in self:
            if sub.start_date and sub.plan_id:
                sub.next_invoice_date = sub.start_date + relativedelta(days=sub.plan_id.renewal_time)
            elif not sub.next_invoice_date:
                sub.next_invoice_date = False

    def _inverse_next_invoice_date(self):
        """Inverse function for next invoice date"""
        pass

    def button_invoice_count(self):
        """ It displays invoice based on subscription package """
        self.ensure_one()
        return {
            'name': 'Invoices',
            'domain': [('subscription_id', '=', self.id)],
            'view_type': 'form',
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'type': 'ir.actions.act_window',
            'context': {
                "create": False
            }
        }

    def button_sale_count(self):
        """ It displays sale order based on subscription package """
        self.ensure_one()
        return {
            'name': 'Products',
            'domain': [('subscription_id', '=', self.id)],
            'view_type': 'form',
            'res_model': 'sale.order',
            'view_mode': 'tree,form',
            'type': 'ir.actions.act_window',
            'context': {
                "create": False
            }
        }

    def button_close(self):
        """ Button for subscription close wizard """
        self.ensure_one()
        return {
            'name': "Subscription Close Reason",
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'subscription.close',
            'target': 'new'
        }

    def _create_subscription_invoice(self, invoice_date=None, due_date=None):
        """Create invoice for subscription package based on plan configuration"""
        self.ensure_one()
        if not self.product_line_ids:
            return False

        today_date = invoice_date or fields.Date.today()
        target_company = self.company_id or self.env.company
        partner = self.partner_invoice_id or self.partner_id
        if not partner:
            raise UserError(_("Please configure Customer or Invoice Address for subscription %s") % self.name)

        invoice_lines = []
        for line in self.product_line_ids:
            line_vals = {
                'product_id': line.product_id.id,
                'name': line.product_id.display_name or line.product_id.name or _('Subscription Item'),
                'quantity': line.product_qty or 1.0,
                'price_unit': line.unit_price,
                'discount': line.discount or 0.0,
            }
            if line.tax_ids:
                line_vals['tax_ids'] = [(6, 0, line.tax_ids.ids)]
            invoice_lines.append((0, 0, line_vals))

        journal = self.plan_id.journal_id if self.plan_id and self.plan_id.journal_id else False
        if not journal:
            journal = self.env['account.journal'].search([
                ('type', '=', 'sale'),
                ('company_id', '=', target_company.id)
            ], limit=1)

        move_vals = {
            'move_type': 'out_invoice',
            'company_id': target_company.id,
            'partner_id': partner.id,
            'partner_shipping_id': self.partner_shipping_id.id or partner.id,
            'currency_id': (self.currency_id or target_company.currency_id).id,
            'invoice_date': today_date,
            'invoice_date_due': due_date or today_date,
            'subscription_id': self.id,
            'invoice_line_ids': invoice_lines,
        }
        if journal:
            move_vals['journal_id'] = journal.id

        move = self.env['account.move'].with_company(target_company).with_context(
            default_move_type='out_invoice',
            default_company_id=target_company.id
        ).create(move_vals)

        if self.plan_id and self.plan_id.invoice_mode == 'done':
            move.action_post()

        return move

    def action_create_invoice(self):
        """Action button to create an invoice manually from subscription"""
        self.ensure_one()
        move = self._create_subscription_invoice()
        if not move:
            raise UserError(_("No products found to invoice."))
        return {
            'name': _('Invoices'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': move.id,
            'context': {
                'default_move_type': 'out_invoice',
            }
        }

    def button_start_date(self):
        """Button to start subscription package"""
        stage_id = self.env['subscription.package.stage'].search([
            ('category', '=', 'progress')], limit=1).id
        for rec in self:
            if not rec.product_line_ids:
                raise UserError("Empty order lines !! Please add the subscription product.")
            if rec.sale_order_id:
                rec.sale_order_id.write({'subscription_id': rec.id, 'is_subscription': True})
            rec.write({
                'stage_id': stage_id,
                'date_started': fields.Date.today(),
                'start_date': fields.Date.today()
            })
            # Generate initial invoice if plan specifies draft_invoice or done and no invoice exists yet
            if rec.plan_id and rec.plan_id.invoice_mode in ['draft_invoice', 'done'] and rec.invoice_count == 0:
                rec._create_subscription_invoice(invoice_date=fields.Date.today(), due_date=fields.Date.today())

    def button_sale_order(self):
        """Button to create sale order matching the subscription's company_id"""
        self.ensure_one()
        target_company = self.company_id or self.env.company

        this_products_line = []
        for rec in self.product_line_ids:
            rec_list = (0, 0, {'product_id': rec.product_id.id,
                               'product_uom_qty': rec.product_qty,
                               'discount': rec.discount})
            this_products_line.append(rec_list)
        orders = self.env['sale.order'].search(
            [('subscription_id', '=', self.id),
             ('invoice_status', '=', 'no')])
        if orders:
            for order in orders:
                order.action_confirm()

        so_id = self.env['sale.order'].with_company(target_company).with_context(
            default_company_id=target_company.id,
            company_id=target_company.id
        ).create({
            'company_id': target_company.id,
            'partner_id': self.partner_id.id,
            'partner_invoice_id': self.partner_id.id,
            'partner_shipping_id': self.partner_id.id,
            'is_subscription': True,
            'subscription_id': self.id,
            'order_line': this_products_line
        })
        self.sale_order_id = so_id
        return {
            'name': _('Sales Orders'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'domain': [('id', '=', so_id.id)],
            'view_mode': 'tree,form',
            'context': {
                "create": False,
                "default_company_id": target_company.id
            }
        }

    @api.model_create_multi
    def create(self, vals_list):
        """It displays subscription product in partner and generate sequence"""
        for vals in vals_list:
            if vals.get('partner_id'):
                partner = self.env['res.partner'].browse(vals['partner_id'])
                if partner.exists():
                    partner.is_active_subscription = True
            if not vals.get('reference_code'):
                vals['reference_code'] = self.env['ir.sequence'].next_by_code(
                    'sequence.reference.code') or 'New'
        return super().create(vals_list)

    @api.depends('reference_code', 'plan_id', 'partner_id')
    def _compute_name(self):
        """It displays record name as combination of short code, reference code and partner name"""
        for rec in self:
            code = rec.reference_code or 'New'
            p_name = rec.partner_id.name or '' if rec.partner_id else ''
            short_code = rec.plan_id.short_code if rec.plan_id and rec.plan_id.short_code else 'SUB'
            rec.name = f"{short_code}/{code}-{p_name}"

    def set_close(self):
        """ Button to close subscription package """
        stage = self.env['subscription.package.stage'].search(
            [('category', '=', 'closed')], limit=1).id
        for sub in self:
            values = {'stage_id': stage, 'is_to_renew': False}
            sub.write(values)
        return True

    def send_renew_alert_mail(self, today, renew_date, sub_id):
        """The function is used to send a renewal alert email and mark the subscription for renewal if today is the renewal date."""
        if today == renew_date:
            try:
                template = self.env.ref('subscription_package.mail_template_subscription_renew', raise_if_not_found=False)
                if template:
                    template.send_mail(sub_id, force_send=True)
            except Exception:
                pass
            subscription = self.env['subscription.package'].browse(sub_id)
            if subscription.exists():
                subscription.write({'is_to_renew': True})
            return True
        return False

    def find_renew_date(self, next_invoice, date_started, end):
        """The function is used to calculate the renewal date, end date, and close date based on subscription details."""
        if not next_invoice or not date_started:
            today = fields.Date.today()
            return {'renew_date': today, 'end_date': today, 'close_date': today}
        if end == 0:
            end_date = next_invoice
            difference = (next_invoice - date_started).days / 10
            renew_date = next_invoice - relativedelta(days=difference)
            close_date = next_invoice
        else:
            end_date = fields.Date.add(date_started, days=end)
            close = date_started + relativedelta(days=end)
            difference = (close - date_started).days / 10
            renew_date = close - relativedelta(days=difference)
            close_date = close

        return {'renew_date': renew_date, 'end_date': end_date, 'close_date': close_date}

    def close_limit_cron(self):
        """ It Checks renew date, close date. It will send mail when renew date and also generates invoices based on the plan."""
        pending_subscriptions = self.env['subscription.package'].search(
            [('stage_category', '=', 'progress')])
        today_date = fields.Date.today()
        for pending_subscription in pending_subscriptions:
            if not pending_subscription.exists():
                continue
            get_dates = self.find_renew_date(
                pending_subscription.next_invoice_date,
                pending_subscription.date_started,
                pending_subscription.plan_id.days_to_end if pending_subscription.plan_id else 0)
            renew_date = get_dates['renew_date']
            end_date = get_dates['end_date']
            pending_subscription.close_date = get_dates['close_date']
            if pending_subscription.next_invoice_date and today_date >= pending_subscription.next_invoice_date:
                if pending_subscription.plan_id and pending_subscription.plan_id.invoice_mode in ['draft_invoice', 'done']:
                    pending_subscription._create_subscription_invoice(
                        invoice_date=today_date,
                        due_date=today_date
                    )
                    pending_subscription.write({
                        'is_to_renew': False,
                        'start_date': pending_subscription.next_invoice_date
                    })
                    new_date = self.find_renew_date(
                        pending_subscription.next_invoice_date,
                        pending_subscription.date_started,
                        pending_subscription.plan_id.days_to_end if pending_subscription.plan_id else 0)
                    pending_subscription.write(
                        {'close_date': new_date['close_date']})

                    self.send_renew_alert_mail(today_date,
                                               new_date['renew_date'],
                                               pending_subscription.id)

            if (today_date == end_date) and (
                    pending_subscription.plan_id and pending_subscription.plan_id.limit_choice != 'manual'):
                display_msg = ("<h5><i>The renewal limit has been exceeded "
                               "today for this subscription based on the "
                               "current subscription plan.</i></h5>")
                pending_subscription.message_post(body=display_msg)
                pending_subscription.is_closed = True
                reason = (self.env['subscription.package.stop'].search([
                    ('name', '=', 'Renewal Limit Exceeded')], limit=1).id)
                pending_subscription.close_reason_id = reason
                pending_subscription.closed_by = self.user_id
                pending_subscription.close_date = fields.Date.today()
                stage = (self.env['subscription.package.stage'].search([
                    ('category', '=', 'closed')], limit=1).id)
                values = {'stage_id': stage, 'is_to_renew': False,
                          'next_invoice_date': False}
                pending_subscription.write(values)

            self.send_renew_alert_mail(today_date, renew_date,
                                       pending_subscription.id)

        return True

    @api.depends('product_line_ids.total_amount',
                 'product_line_ids.price_total', 'product_line_ids.tax_ids')
    def _compute_total_recurring_price(self):
        """ The compute function used to calculate recurring price """
        for record in self:
            total_recurring = 0
            total_tax = 0.0
            for line in record.product_line_ids:
                if line.total_amount != line.price_total:
                    line_tax = line.price_total - line.total_amount
                    total_tax += line_tax

                total_recurring += line.total_amount
            record['total_recurring_price'] = total_recurring
            record['tax_total'] = total_tax
            total_with_tax = total_recurring + total_tax
            record['total_with_tax'] = total_with_tax

    def action_renew(self):
        """ The function is used to perform the renewal action for the subscription package."""
        return self.button_sale_order()

    def action_pause(self):
        """ The function is used to perform the pause action for the subscription package."""
        stage = self.env.ref('subscription_package.paused_stage', raise_if_not_found=False)
        if stage:
            self.stage_id = stage.id

    def button_resume(self):
        """ The function is used to perform the resume action for the subscription package."""
        stage = self.env.ref('subscription_package.progress_stage', raise_if_not_found=False)
        if stage:
            self.stage_id = stage.id
