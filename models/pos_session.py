# -*- coding: utf-8 -*-
from odoo import models


class PosSession(models.Model):
    _inherit = 'pos.session'

    def _loader_params_res_partner(self):
        result = super()._loader_params_res_partner()
        result['search_params']['fields'] += [
            'carabinero_state',
            'carabinero_valid_until',
            'carabinero_email',
            'carabinero_rank',
            'carabinero_unit',
        ]
        return result

    def _loader_params_product_product(self):
        result = super()._loader_params_product_product()
        result['search_params']['fields'].append('carabinero_public_sale')
        return result
