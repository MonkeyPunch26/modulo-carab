# -*- coding: utf-8 -*-
from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class PosOrder(models.Model):
    _inherit = 'pos.order'

    @api.model
    def _process_order(self, order, draft, existing_order):
        if not draft:
            self._carabinero_check_order_data(order.get('data') or {})
        return super()._process_order(order, draft, existing_order)

    @api.model
    def _carabinero_restricted_product_names(self, data, config):
        """Nombres de los productos de la venta que solo se pueden vender a Carabineros activos.

        Cuentan las líneas de venta (cantidad y precio positivos). Quedan fuera las propinas y las
        líneas de descuento, que no son productos que se le "vende" a nadie.
        """
        names = []
        for command in data.get('lines') or []:
            line = command[2] if isinstance(command, (list, tuple)) and len(command) == 3 else None
            if not line or (line.get('qty') or 0) <= 0 or (line.get('price_unit') or 0) <= 0:
                continue
            product = self.env['product.product'].browse(line.get('product_id') or []).exists()
            if not product or product == config.tip_product_id or product.carabinero_public_sale:
                continue
            names.append(product.display_name)
        return names

    @api.model
    def _carabinero_check_order_data(self, data):
        """Segunda barrera (la primera está en la caja): el servidor rechaza ventas de productos
        restringidos a quien no es un Carabinero activo.

        Se mira la fecha de la venta, no la de hoy: una venta hecha sin conexión cuando el cliente
        estaba vigente se sincroniza bien aunque la vigencia termine antes de que llegue.
        Las devoluciones (total <= 0) no se bloquean.
        """
        session = self.env['pos.session'].browse(data.get('pos_session_id')).exists()
        if not session or not session.config_id.carabinero_required:
            return
        if float_compare(data.get('amount_total') or 0.0, 0.0, precision_digits=2) <= 0:
            return
        restricted = self._carabinero_restricted_product_names(data, session.config_id)
        if not restricted:
            return
        products = ", ".join(restricted[:3]) + ("…" if len(restricted) > 3 else "")
        partner = self.env['res.partner'].browse(data.get('partner_id') or []).exists()
        if not partner:
            raise UserError(_(
                "La venta incluye productos solo para Carabineros (%s). Falta seleccionar un cliente Carabinero activo.",
                products))
        order_date = partner._carabinero_local_date(data.get('date_order') or data.get('creation_date'))
        if not partner._carabinero_valid_on(order_date):
            raise UserError(_(
                "%(partner)s no está activo como Carabinero (estado: %(state)s). No se pueden vender productos solo para Carabineros (%(products)s).",
                partner=partner.display_name,
                state=dict(partner._fields['carabinero_state'].selection).get(partner.carabinero_state),
                products=products))
