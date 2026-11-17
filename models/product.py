# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    carabinero_public_sale = fields.Boolean(
        'Apto para público general',
        default=False,
        help="Marcado: se puede vender a cualquier cliente, incluso sin cliente. "
             "Sin marcar: solo se vende a un Carabinero con inscripción vigente.",
    )


class ProductProduct(models.Model):
    _inherit = 'product.product'

    carabinero_public_sale = fields.Boolean(related='product_tmpl_id.carabinero_public_sale', readonly=True)
