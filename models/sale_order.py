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
from odoo import api, fields, models
from odoo.tools.safe_eval import datetime


class SaleOrder(models.Model):
    """ This class is used to inherit sale order"""
    _inherit = 'sale.order'

    subscription_count = fields.Integer(string='Subscriptions',
                                        compute='_compute_subscription_count',
                                        help='Subscriptions count')
    is_subscription = fields.Boolean(string='Is Subscription', default=False,
                                     help='Is subscription')
    subscription_id = fields.Many2one('subscription.package',
                                      string='Subscription',
                                      help='Choose the subscription')
    sub_reference = fields.Char(string="Sub Reference Code", store=True,
                                compute="_compute_reference_code",
                                help='Subscription Reference Code')

    @api.model_create_multi
    def create(self, vals_list):
        """ It displays subscription in sale order """
        for vals in vals_list:
            if vals.get('is_subscription'):
                vals.update({
                    'is_subscription': True,
                    'subscription_id': vals.get('subscription_id'),
                })
        return super().create(vals_list)

    @api.depends('subscription_id')
    def _compute_reference_code(self):
        """ It displays subscription reference code """
        for order in self:
            try:
                sub = order.subscription_id
                if sub and sub.exists():
                    order.sub_reference = sub.reference_code
                else:
                    order.sub_reference = False
            except Exception:
                order.sub_reference = False

    def action_confirm(self):
        """ It Changed the stage, to renew, start date for subscription
        package based on sale order confirm """

        res = super().action_confirm()
        for order in self:
            try:
                sub = order.subscription_id
                if sub and sub.exists():
                    sale_order = sub.sale_order_id
                    if sale_order and sale_order.exists() and sale_order.state in ['sale', 'done']:
                        stage = self.env['subscription.package.stage'].search(
                            [('category', '=', 'progress')], limit=1).id
                        values = {'stage_id': stage, 'is_to_renew': False,
                                  'start_date': datetime.datetime.today()}
                        sub.write(values)
            except Exception:
                pass
        return res

    @api.depends('is_subscription')
    def _compute_subscription_count(self):
        """the compute function the count of subscriptions associated with the sale order."""
        for order in self:
            try:
                count = self.env['subscription.package'].sudo().search_count([('sale_order_id', '=', order.id)])
                order.subscription_count = count
            except Exception:
                order.subscription_count = 0

    def button_subscription(self):
        """Open the subscription packages associated with the sale order."""
        self.ensure_one()
        return {
            'name': 'Subscription',
            'sale_order_id': False,
            'domain': [('sale_order_id', '=', self.id)],
            'view_type': 'form',
            'res_model': 'subscription.package',
            'view_mode': 'tree,form',
            'type': 'ir.actions.act_window',
            'context': {
                "create": False
            }
        }

    def _action_confirm(self):
        """the function used to Confrim the sale order and
        create subscriptions for subscription products"""
        for order in self:
            try:
                if order.subscription_count != 1:
                    if order.order_line:
                        for line in order.order_line:
                            if line.product_id.is_subscription:
                                this_products_line = []
                                rec_list = (0, 0, {'product_id': line.product_id.id,
                                                   'product_qty': line.product_uom_qty,
                                                   'unit_price': line.price_unit})
                                this_products_line.append(rec_list)
                                self.env['subscription.package'].create(
                                    {
                                        'sale_order_id': order.id,
                                        'reference_code': self.env[
                                            'ir.sequence'].next_by_code(
                                            'sequence.reference.code'),
                                        'start_date': fields.Date.today(),
                                        'stage_id': self.env.ref(
                                            'subscription_package.draft_stage').id,
                                        'partner_id': order.partner_id.id,
                                        'plan_id': line.product_id.subscription_plan_id.id,
                                        'product_line_ids': this_products_line
                                    })
            except Exception:
                pass
        return super()._action_confirm()
