# -*- coding: utf-8 -*-
{
    'name': 'Carabineros: inscripción y vigencia en el POS',
    'version': '17.0.1.1.0',
    'category': 'Sales/Point of Sale',
    'summary': 'Solo se vende a clientes Carabineros activos. El ingreso lo aprueba un encargado y vence a los 12 meses.',
    'description': """
Flujo de inscripción de clientes Carabineros para el punto de venta de Odoo 17 Community.

* El vendedor registra al cliente (desde la caja o desde Odoo) y solicita su inscripción.
* Solo un usuario con el grupo "Aprobador de Carabineros" puede aprobarla o rechazarla.
* Al aprobar, el cliente queda activo por 12 meses. Al vencer, queda inactivo y hay que volver a activarlo.
* Cada producto se marca como apto para público general o no. Los no aptos solo se venden a Carabineros activos.
* El POS muestra el estado de cada cliente y no deja cobrar si falta un Carabinero activo. El servidor también lo revisa al sincronizar cada venta.
""",
    'author': 'DROS',
    'license': 'LGPL-3',
    'depends': ['point_of_sale', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/mail_activity_data.xml',
        'data/ir_cron.xml',
        'wizard/reject_wizard_views.xml',
        'views/res_partner_views.xml',
        'views/pos_config_views.xml',
        'views/product_views.xml',
        'data/product_actions.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'dros_carabineros/static/src/app/**/*',
        ],
    },
    'installable': True,
    'application': False,
}
