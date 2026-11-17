# -*- coding: utf-8 -*-
from odoo import fields, models


class CarabineroRejectWizard(models.TransientModel):
    _name = 'dros.carabinero.reject.wizard'
    _description = 'Rechazar o revocar inscripción de Carabinero'

    partner_ids = fields.Many2many('res.partner', string='Clientes', required=True)
    reason = fields.Char('Motivo', required=True)

    def action_confirm(self):
        self.ensure_one()
        self.partner_ids.action_carabinero_reject(self.reason)
        return {'type': 'ir.actions.act_window_close'}
