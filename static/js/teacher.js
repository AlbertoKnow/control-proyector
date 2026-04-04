/**
 * Lógica de la vista de docentes de ProyControl.
 * Control simple: encender / apagar proyector del aula.
 */

// Leer datos del proyector desde los atributos del botón
const btnOn  = document.getElementById('btn-on');
const btnOff = document.getElementById('btn-off');

const CLASSROOM_NUMBER = btnOn?.dataset.classroom;

// Etiquetas de estado
const STATUS_ICONS = {
  on:      '☀',
  off:     '▏',
  warming: '⏳',
  cooling: '⏳',
  unknown: '?',
};
const STATUS_TEXT = {
  on:          'Encendido',
  off:         'Apagado',
  warming:     'Calentando…',
  cooling:     'Enfriando…',
  unknown:     'Estado desconocido',
  unreachable: 'Proyector sin respuesta',
  offline:     'Proyector desconectado',
};

// ---------------------------------------------------------------------------
// Feedback visual
// ---------------------------------------------------------------------------

/**
 * Muestra un mensaje de feedback al docente.
 * @param {string} message
 * @param {'success'|'error'|'loading'} type
 * @param {number} duration - 0 = permanente
 */
function showFeedback(message, type = 'loading', duration = 0) {
  const el = document.getElementById('action-feedback');
  if (!el) return;
  el.className = `teacher-feedback fb-${type}`;
  el.textContent = message;
  el.style.display = 'block';
  if (duration > 0) {
    setTimeout(() => { el.style.display = 'none'; }, duration);
  }
}

function hideFeedback() {
  const el = document.getElementById('action-feedback');
  if (el) el.style.display = 'none';
}

// ---------------------------------------------------------------------------
// Actualizar UI de estado
// ---------------------------------------------------------------------------

/**
 * Actualiza el bloque de estado y el estado de los botones.
 * @param {string} status
 */
function applyStatus(status) {
  const display = document.getElementById('status-display');
  const icon    = document.getElementById('status-icon');
  const text    = document.getElementById('status-text');

  if (display) {
    display.className = `teacher-status status-${status}`;
  }
  if (icon) icon.textContent = STATUS_ICONS[status] || '?';
  if (text) text.textContent = STATUS_TEXT[status] || status;

  // Habilitar/deshabilitar botones según estado
  if (btnOn)  btnOn.disabled  = ['on',  'warming'].includes(status);
  if (btnOff) btnOff.disabled = ['off', 'cooling', 'unknown', 'unreachable', 'offline'].includes(status);
}

// ---------------------------------------------------------------------------
// Acción de encendido / apagado
// ---------------------------------------------------------------------------

/**
 * Envía el comando de encendido o apagado para el aula actual.
 * @param {'on'|'off'} action
 */
async function teacherPower(action) {
  if (!CLASSROOM_NUMBER) return;

  const btn        = action === 'on' ? btnOn : btnOff;
  const otherBtn   = action === 'on' ? btnOff : btnOn;
  const actionText = action === 'on' ? 'Encendiendo' : 'Apagando';

  // Estado de carga
  const originalContent = btn.innerHTML;
  btn.disabled    = true;
  otherBtn.disabled = true;
  btn.innerHTML   = `<span class="teacher-spinner"></span> ${actionText}…`;
  showFeedback(`${actionText} el proyector…`, 'loading');

  try {
    const res = await fetch(`/api/classroom/${CLASSROOM_NUMBER}/power-${action}`, {
      method: 'POST',
    });
    const data = await res.json();

    if (data.success) {
      const newStatus = action === 'on' ? 'warming' : 'cooling';
      applyStatus(newStatus);
      const msg = action === 'on'
        ? 'Proyector encendido. Espere unos segundos mientras calienta.'
        : 'Proyector apagado. Espere mientras enfría.';
      showFeedback(msg, 'success', 6000);
    } else {
      showFeedback(
        `No se pudo ${action === 'on' ? 'encender' : 'apagar'}: ${data.error || 'Error desconocido'}`,
        'error',
        6000,
      );
      // Restaurar botones al estado anterior
      btn.innerHTML = originalContent;
      btn.disabled  = false;
      otherBtn.disabled = false;
    }
  } catch (err) {
    showFeedback('Error de conexión con el servidor', 'error', 6000);
    btn.innerHTML = originalContent;
    btn.disabled  = false;
    otherBtn.disabled = false;
  }
}

// ---------------------------------------------------------------------------
// Consulta periódica de estado (cada 15 segundos)
// ---------------------------------------------------------------------------

async function pollStatus() {
  if (!CLASSROOM_NUMBER) return;
  try {
    const res  = await fetch(`/api/classroom/${CLASSROOM_NUMBER}/info`);
    const data = await res.json();
    if (data.projector?.status) {
      applyStatus(data.projector.status);
    }
  } catch (_) {
    // Silencioso — no interrumpir al docente con errores de red
  }
}

setInterval(pollStatus, 15000);
