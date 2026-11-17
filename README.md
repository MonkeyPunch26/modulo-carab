# Carabineros: inscripción y vigencia en el POS (Odoo 17 Community)

Los productos **no marcados como aptos para público general** solo se le pueden vender a un cliente Carabinero **activo**. Los marcados se venden a cualquiera, incluso sin cliente. El ingreso lo aprueba el encargado (tu papá) y la inscripción dura **12 meses**; al vencer queda **inactivo** y hay que volver a solicitarla y aprobarla.

## Instalar
1. Copia la carpeta `dros_carabineros` dentro de `odoo/addons/` del repo (queda `odoo/addons/dros_carabineros`).
2. Instala o actualiza:
   - Primera vez: `docker compose exec odoo odoo -i dros_carabineros -d NOMBRE_BD --stop-after-init` y luego `docker compose restart odoo`
   - O desde Odoo: modo desarrollador > Aplicaciones > Actualizar lista de aplicaciones > buscar "Carabineros" > Instalar.
   - Para actualizar después: `-u dros_carabineros` en vez de `-i`.
3. En Ajustes > Usuarios, a tu papá dale el grupo **Aprobador de Carabineros** (sección "Carabineros"). Sin al menos un aprobador, nadie puede solicitar inscripciones y el sistema avisa con un error claro.
4. **Marca los productos aptos para público general.** Al instalar, todos los productos quedan como "solo Carabineros" (lo más seguro). En Punto de Venta > Productos, marca los que sí se venden a todos:
   - Una a una: en la ficha, pestaña Ventas > bloque Point of Sale > "Apto para público general".
   - Varias a la vez: en la lista selecciona los productos y usa Acciones > "Marcar como apto para público general" (o "Marcar como solo Carabineros"). La lista tiene una columna con el check y filtros "Aptos para público general" / "Solo Carabineros".
5. A los vendedores que deban crear o editar clientes desde la caja, dales el permiso **Creación de contactos** (en Odoo 17 Community el usuario de POS no puede escribir clientes sin él).

## Cómo funciona
- **Vendedor, en la caja:** Cliente > DETAILS (o Crear). Pone el RUT en *Tax ID*, completa correo institucional, grado y unidad, y pulsa **Guardar y solicitar inscripción**. El RUT se valida (dígito verificador) y no puede repetirse.
- **Aprobador:** recibe una actividad (campana) en Odoo. Va a **Punto de Venta > Carabineros**, abre la solicitud y pulsa **Aprobar** o **Rechazar**. Al aprobar, queda activo hasta la misma fecha 12 meses después (ese último día incluido).
- **Estados:** No inscrito, Pendiente, Activo, Inactivo (vencido), Rechazado. Cada noche un proceso programado pasa a *Inactivo* a los vencidos.
- **Renovar:** el vendedor pulsa **Solicitar renovación** (o desde Odoo) y el aprobador vuelve a aprobar. Se puede renovar antes de que venza.
- **En la caja:** la lista de clientes muestra una insignia con el estado y la fecha; junto al nombre del cliente hay un check verde (activo) o una alerta roja. Si la venta tiene solo productos aptos para público general, se cobra normal a cualquiera. Si tiene al menos un producto solo Carabineros, al pulsar *Pago* hace falta un cliente activo; si no, aparece un aviso que nombra esos productos y no deja avanzar.
- **El servidor también bloquea:** al sincronizar cada venta se vuelve a comprobar, así que no se salta con una caja desactualizada.

## Opciones
- Activar o desactivar la regla por caja: Punto de Venta > Configuración > Ajustes (bloque "Carabineros") o en la ficha de la configuración del POS ("Aplicar regla de Carabineros", viene activada). Desactivada, esa caja vende todo a todos.
- Cambiar la duración: parámetro del sistema `dros_carabineros.validity_months` (por defecto 12).

## Límites a tener en cuenta
- Las devoluciones (total negativo o cero) no se bloquean. Las propinas y las líneas de descuento tampoco cuentan como producto restringido.
- Quien pueda editar productos en Odoo puede cambiar la marca; los vendedores de la caja no pueden.
- Para actualizar una instalación anterior del módulo usa `-u dros_carabineros`; los productos que ya existan quedan como "solo Carabineros".
- Una venta hecha sin conexión mientras el cliente estaba vigente se sincroniza igual aunque después venza; si lo revocan, sí se rechaza.
- Los textos están solo en español.
- No envía correos ni WhatsApp: el aviso al aprobador es la actividad dentro de Odoo (si tienes servidor de correo configurado, Odoo puede enviarle el aviso por correo).
- La fecha de vigencia se calcula con la zona horaria America/Santiago.
