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


class AccountMove(models.Model):
    """Inherited sale order model"""
    _inherit = "account.move"

    is_subscription = fields.Boolean(string='Is Subscription', default=False,
                                     help='Is subscription')
    subscription_id = fields.Many2one('subscription.package',
                                      string='Subscription',
                                      help='Choose subscription package')

    def _auto_init(self):
        res = super()._auto_init()
        # Clean up stale legacy Enterprise subscription_id references in PostgreSQL account_move table
        try:
            self.env.cr.execute("""
                UPDATE account_move 
                SET subscription_id = NULL 
                WHERE subscription_id IS NOT NULL 
                  AND subscription_id NOT IN (SELECT id FROM subscription_package);
            """)
        except Exception:
            pass
        return res

    @api.model_create_multi
    def create(self, vals_list):
        """ It displays subscription in account move """
        for rec in vals_list:
            origin = rec.get('invoice_origin')
            if origin:
                so_id = self.env['sale.order'].search([('name', '=', origin)], limit=1)
                if so_id and so_id.exists() and so_id.is_subscription:
                    sub = so_id.subscription_id
                    if sub and sub.exists():
                        if sub.next_invoice_date:
                            sub.start_date = sub.next_invoice_date
                        rec.update({
                            'is_subscription': True,
                            'subscription_id': sub.id
                        })
        return super().create(vals_list)
