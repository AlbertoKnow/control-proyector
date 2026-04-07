/**
 * Lógica del panel de administración de ProyControl.
 * Maneja controles de energía, escaneo y actualización de estado.
 */

// ---------------------------------------------------------------------------
// Utilidades
// ---------------------------------------------------------------------------

/**
 * Muestra un mensaje de alerta temporal en el contenedor indicado.
 * @param {string} containerId - ID del elemento donde mostrar la alerta.
 * @param {string} message - Texto a mostrar.
 * @param {'success'|'error'|'info'} type - Tipo de alerta.
 * @param {number} duration - Milisegundos antes de ocultarla (0 = permanente).
 */
function showAlert(containerId, message, type = 'info', duration = 4000) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.className = `alert alert-${type}`;
  el.textContent = message;
  el.style.display = 'block';
  if (duration > 0) {
    setTimeout(() => { el.style.display = 'none'; }, duration);
  }
}

/**
 * Etiqueta legible para los estados de energía.
 */
const STATUS_LABELS = {
  on:      'Encendido',
  off:     'Apagado',
  warming: 'Calentando',
  cooling: 'Enfriando',
  unknown: 'Desconocido',
  unreachable: 'Sin respuesta',
  offline: 'Desconectado',
};

// ---------------------------------------------------------------------------
// Control de energía
// ---------------------------------------------------------------------------

/**
 * Envía un comando de encendido o apagado a un proyector.
 * @param {number} projectorId - ID del proyector.
 * @param {'on'|'off'} action - Acción a ejecutar.
 * @param {boolean} detailPage - Si es true usa el contenedor de la página de detalle.
 */
async function powerAction(projectorId, action, detailPage = false) {
  const alertId = detailPage ? 'action-result' : 'scan-result';
  const endpoint = `/api/projectors/${projectorId}/power-${action}`;

  try {
    const res = await fetch(endpoint, { method: 'POST' });
    const data = await res.json();

    if (data.success) {
      const label = action === 'on' ? 'Encendido' : 'Apagado';
      showAlert(alertId, `${label} correctamente (IP: ${data.ip})`, 'success');
      const newStatus = action === 'on' ? 'warming' : 'cooling';
      applyStatusToCard(projectorId, newStatus);
      updateStatusCounters();
    } else {
      showAlert(alertId, `Error: ${data.error || 'No se pudo ejecutar el comando'}`, 'error');
    }
  } catch (err) {
    showAlert(alertId, 'Error de conexión con el servidor', 'error');
  }
}

// ---------------------------------------------------------------------------
// Actualizar estado
// ---------------------------------------------------------------------------

/**
 * Consulta el estado actual de un proyector y actualiza la UI.
 * @param {number} projectorId
 * @param {boolean} detailPage
 */
async function refreshStatus(projectorId, detailPage = false) {
  const alertId = detailPage ? 'action-result' : 'scan-result';

  try {
    const res = await fetch(`/api/projectors/${projectorId}/status`);
    const data = await res.json();
    applyStatusToCard(projectorId, data.status);

    if (detailPage) {
      const badge = document.getElementById('status-badge');
      if (badge) {
        badge.textContent = STATUS_LABELS[data.status] || data.status;
        badge.className = `badge-status status-${data.status}`;
      }
    }
  } catch (err) {
    showAlert(alertId, 'No se pudo obtener el estado del proyector', 'error');
  }
}

/**
 * Actualiza visualmente la tarjeta de un proyector con el nuevo estado.
 * @param {number} projectorId
 * @param {string} status
 */
function applyStatusToCard(projectorId, status) {
  const card = document.getElementById(`card-${projectorId}`);
  const statusEl = document.getElementById(`status-${projectorId}`);

  if (card) {
    card.className = `projector-card status-${status}`;

    // Actualizar estado habilitado/deshabilitado de los botones
    const btnOn  = card.querySelector('.btn-on');
    const btnOff = card.querySelector('.btn-off');
    if (btnOn)  btnOn.disabled  = ['on', 'warming'].includes(status);
    if (btnOff) btnOff.disabled = ['off', 'cooling', 'unknown'].includes(status);
  }
  if (statusEl) {
    statusEl.textContent = STATUS_LABELS[status] || status;
  }
}

/**
 * Recorre todos los proyectores visibles y actualiza su estado.
 * Llamada por el temporizador de auto-refresh cada 30 segundos.
 */
async function refreshAllStatuses() {
  const cards = document.querySelectorAll('.projector-card[id^="card-"]');
  const promises = Array.from(cards).map(card => {
    const id = parseInt(card.id.replace('card-', ''), 10);
    return refreshStatus(id);
  });
  await Promise.allSettled(promises);
  updateStatusCounters();
}

/**
 * Cuenta los proyectores por estado leyendo las clases de las tarjetas
 * y actualiza los contadores en la barra superior.
 */
function updateStatusCounters() {
  const counts = { on: 0, off: 0, warming: 0, cooling: 0, unknown: 0 };

  document.querySelectorAll('.projector-card[id^="card-"]').forEach(card => {
    for (const status of Object.keys(counts)) {
      if (card.classList.contains(`status-${status}`)) {
        counts[status]++;
        break;
      }
    }
  });

  for (const [status, count] of Object.entries(counts)) {
    const el = document.getElementById(`count-${status}`);
    if (el) el.textContent = count;
  }
}

// ---------------------------------------------------------------------------
// Encendido / apagado masivo
// ---------------------------------------------------------------------------

/**
 * Enciende o apaga todos los proyectores a la vez.
 * @param {'on'|'off'} action
 */
async function bulkPower(action) {
  const label = action === 'on' ? 'encender' : 'apagar';
  if (!confirm(`¿Seguro que deseas ${label} todos los proyectores?`)) return;

  const btnOn  = document.getElementById('btn-on-all');
  const btnOff = document.getElementById('btn-off-all');
  if (btnOn)  btnOn.disabled  = true;
  if (btnOff) btnOff.disabled = true;

  showAlert('scan-result', `${action === 'on' ? 'Encendiendo' : 'Apagando'} todos los proyectores…`, 'info', 0);

  try {
    const res  = await fetch(`/api/projectors/power-${action}-all`, { method: 'POST' });
    const data = await res.json();

    const msg = `${action === 'on' ? 'Encendido' : 'Apagado'} masivo: `
              + `${data.success} exitosos, ${data.failed} fallidos de ${data.total} proyectores.`;
    showAlert('scan-result', msg, data.failed === 0 ? 'success' : 'error', 8000);

    // Actualizar estado visual de todas las tarjetas
    const newStatus = action === 'on' ? 'warming' : 'cooling';
    document.querySelectorAll('.projector-card[id^="card-"]').forEach(card => {
      const id = parseInt(card.id.replace('card-', ''), 10);
      applyStatusToCard(id, newStatus);
    });
    updateStatusCounters();
  } catch (err) {
    showAlert('scan-result', 'Error de conexión durante la operación masiva', 'error', 6000);
  } finally {
    if (btnOn)  btnOn.disabled  = false;
    if (btnOff) btnOff.disabled = false;
  }
}

// ---------------------------------------------------------------------------
// Escaneo de red
// ---------------------------------------------------------------------------

/**
 * Lanza un escaneo manual de todas las subredes.
 * Deshabilita el botón durante el escaneo y muestra resultado.
 */
async function triggerScan() {
  const btn = document.getElementById('btn-scan');
  const icon = document.getElementById('scan-icon');
  if (!btn) return;

  btn.disabled = true;
  if (icon) icon.innerHTML = '<span class="spinner"></span>';

  try {
    const res = await fetch('/api/scan', { method: 'POST' });
    const data = await res.json();

    if (data.success) {
      const msg = `Escaneo completado: ${data.projectors_found} proyector(es) encontrado(s). ` +
                  `Nuevos: ${data.new} | Actualizados: ${data.updated} | Sin cambios: ${data.unchanged}`;
      showAlert('scan-result', msg, 'success', 8000);
      // Recargar la página para mostrar los cambios
      setTimeout(() => location.reload(), 2000);
    } else {
      showAlert('scan-result', 'Error durante el escaneo', 'error');
    }
  } catch (err) {
    showAlert('scan-result', 'Error de conexión durante el escaneo', 'error');
  } finally {
    btn.disabled = false;
    if (icon) icon.textContent = '🔍';
  }
}

// ---------------------------------------------------------------------------
// Asignación de aula
// ---------------------------------------------------------------------------

/**
 * Envía la asignación del proyector al aula seleccionada.
 * @param {Event} event
 * @param {number} projectorId
 */
async function assignClassroom(event, projectorId) {
  event.preventDefault();
  const select = document.getElementById('sel-classroom');
  const classroomId = select.value ? parseInt(select.value, 10) : null;

  try {
    const res = await fetch(`/api/projectors/${projectorId}/assign`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ classroom_id: classroomId }),
    });
    const data = await res.json();

    if (data.success) {
      showAlert('action-result', 'Asignación guardada correctamente', 'success');
    } else {
      showAlert('action-result', `Error: ${data.error || 'No se pudo guardar'}`, 'error');
    }
  } catch (err) {
    showAlert('action-result', 'Error de conexión con el servidor', 'error');
  }
}

// ---------------------------------------------------------------------------
// Actualizar MAC
// ---------------------------------------------------------------------------

/**
 * Envía la nueva MAC address del proyector.
 * @param {Event} event
 * @param {number} projectorId
 */
async function updateMac(event, projectorId) {
  event.preventDefault();
  const input = document.getElementById('inp-mac');
  const mac = input.value.trim().toUpperCase();

  if (!mac) {
    showAlert('action-result', 'Ingrese una MAC address válida', 'error');
    return;
  }

  try {
    const res = await fetch(`/api/projectors/${projectorId}/mac`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mac_address: mac }),
    });
    const data = await res.json();

    if (data.success) {
      showAlert('action-result', `MAC actualizada: ${data.mac_address}`, 'success');
      const display = document.getElementById('mac-display');
      if (display) display.textContent = data.mac_address;
    } else {
      showAlert('action-result', `Error: ${data.error || 'No se pudo actualizar'}`, 'error');
    }
  } catch (err) {
    showAlert('action-result', 'Error de conexión con el servidor', 'error');
  }
}
