# -*- coding: utf-8 -*-
from odoo import fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    carabinero_required = fields.Boolean(
        'Aplicar regla de Carabineros',
        default=True,
        help="Si está activo, los productos que no son 'aptos para público general' solo se pueden vender "
             "a un Carabinero con inscripción vigente. Los productos aptos para público general se venden a cualquiera. "
             "Las devoluciones no se bloquean.",
    )
