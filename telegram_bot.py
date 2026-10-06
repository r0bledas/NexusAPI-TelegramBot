import os
import time
import html
import threading
from datetime import datetime
from typing import Dict, Any, Optional, Set, Tuple, List
import httpx
from dotenv import load_dotenv

from tokens import get_token
from requests_utils import get_cursos, get_tareas, get_user

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

SIGNATURE = "\n\n━━━━━━━━━━━━━━━\n<i>Le debes una coca a Rau 🥤</i>"

# Per-chat isolated session storage (NO global/default credentials)
# chat_id -> {
#   "user": str,
#   "password": str,
#   "alerts": bool,
#   "sent_alerts": Set[str],
#   "known_due_dates": Dict[str, datetime]
# }
chat_sessions: Dict[int, Dict[str, Any]] = {}
# user -> {"token": str, "perfil": list, "cursos": list, "tareas": list, "timestamp": float}
user_cache: Dict[str, Dict[str, Any]] = {}
state_lock = threading.Lock()


def parse_due_date(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str[:19], fmt)
        except ValueError:
            continue
    return None


def make_task_key(curso: str, desc: str) -> str:
    return f"{curso.strip()}|{desc.strip()}"


def format_time_diff(seconds: float) -> str:
    total_mins = int(abs(seconds) // 60)
    days = total_mins // (24 * 60)
    hours = (total_mins % (24 * 60)) // 60
    mins = total_mins % 60
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if mins > 0 and days == 0:
        parts.append(f"{mins}m")
    return " ".join(parts) if parts else "unos minutos"


def get_unusual_time_warning(dt: Optional[datetime]) -> Optional[str]:
    """Warn if due time is not 23:59, and especially if it's before 23:00 (11:00 PM)."""
    if not dt:
        return None
    if dt.hour < 23:
        time_12h = dt.strftime("%I:%M %p")
        return f"🚨 <b>¡CUIDADO CON LA HORA! Vence a las {dt.strftime('%H:%M')} ({time_12h} — ANTES de las 11:00 PM)</b>"
    if (dt.hour, dt.minute) != (23, 59):
        time_12h = dt.strftime("%I:%M %p")
        return f"⚠️ <b>¡OJO CON LA HORA! Vence a las {dt.strftime('%H:%M')} ({time_12h} — NO a las 11:59 PM)</b>"
    return None


def detect_due_date_changes(
    chat_id: int, tareas: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Compares current `tareas` against `session['known_due_dates']`.
    Returns (moved_closer_list, postponed_list) and updates `known_due_dates`.
    """
    moved_closer: List[Dict[str, Any]] = []
    postponed: List[Dict[str, Any]] = []

    with state_lock:
        session = chat_sessions.get(chat_id)
        if not session:
            return moved_closer, postponed
        known: Optional[Dict[str, datetime]] = session.get("known_due_dates")
        is_first_snapshot = known is None
        if is_first_snapshot:
            known = {}
            session["known_due_dates"] = known

        for t in tareas:
            curso = str(t.get("Curso") or "General")
            desc = str(t.get("Descripcion") or "Sin descripción").strip()
            new_dt = parse_due_date(t.get("FechaEntrega"))
            if not new_dt:
                continue
            key = make_task_key(curso, desc)
            old_dt = known.get(key)

            if not is_first_snapshot and old_dt and old_dt != new_dt:
                diff_sec = (new_dt - old_dt).total_seconds()
                change_info = {
                    "curso": curso,
                    "desc": desc,
                    "old_dt": old_dt,
                    "new_dt": new_dt,
                    "diff_str": format_time_diff(diff_sec),
                }
                if diff_sec < 0:
                    moved_closer.append(change_info)
                else:
                    postponed.append(change_info)

            known[key] = new_dt

    return moved_closer, postponed


def send_due_date_change_notifications(
    client: httpx.Client,
    chat_id: int,
    moved_closer: List[Dict[str, Any]],
    postponed: List[Dict[str, Any]],
):
    now = datetime.now()
    # 1. Alarm message if any due date was pulled closer
    if moved_closer:
        lines = [
            "🚨⏰ <b>¡ALERTA! ¡FECHA DE ENTREGA ADELANTADA!</b> ⏰🚨\n"
            "<i>Un profesor movió la fecha de entrega para que venza <b>MÁS PRONTO</b>:</i>\n"
        ]
        for item in moved_closer:
            old_str = item["old_dt"].strftime("%d/%b/%Y %H:%M")
            new_str = item["new_dt"].strftime("%d/%b/%Y %H:%M")
            remaining = format_time_diff((item["new_dt"] - now).total_seconds())
            time_warn = get_unusual_time_warning(item["new_dt"])
            warn_line = f"\n  {time_warn}" if time_warn else ""
            lines.append(
                f"🚨 <b>{html.escape(item['desc'])}</b>\n"
                f"  📘 <i>{html.escape(item['curso'])}</i>\n"
                f"  ❌ Antes: <s>{old_str}</s>\n"
                f"  ⏰ <b>Ahora: {new_str}</b> (<b>-{item['diff_str']} menos de tiempo</b>)\n"
                f"  ⏳ Tiempo restante: <b>{remaining}</b>{warn_line}"
            )
        send_message(client, chat_id, "\n\n".join(lines), reply_markup=build_main_keyboard(chat_id))

    # 2. Separate message if any due date was postponed
    if postponed:
        lines = [
            "🎉📅 <b>¡FECHA DE ENTREGA APLAZADA (MÁS TIEMPO)!</b>\n"
            "<i>Se extendió la fecha límite de entrega:</i>\n"
        ]
        for item in postponed:
            old_str = item["old_dt"].strftime("%d/%b/%Y %H:%M")
            new_str = item["new_dt"].strftime("%d/%b/%Y %H:%M")
            time_warn = get_unusual_time_warning(item["new_dt"])
            warn_line = f"\n  {time_warn}" if time_warn else ""
            lines.append(
                f"📅 <b>{html.escape(item['desc'])}</b>\n"
                f"  📘 <i>{html.escape(item['curso'])}</i>\n"
                f"  🕒 Antes: <s>{old_str}</s>\n"
                f"  ✅ <b>Nueva fecha: {new_str}</b> (<b>+{item['diff_str']} extra</b>){warn_line}"
            )
        send_message(client, chat_id, "\n\n".join(lines), reply_markup=build_main_keyboard(chat_id))


def fetch_nexus_data(
    user: str,
    password: str,
    force_refresh: bool = False,
    chat_id: Optional[int] = None,
    client: Optional[httpx.Client] = None,
) -> Dict[str, Any]:
    now = time.time()
    with state_lock:
        cached = user_cache.get(user)
        if cached and not force_refresh and (now - cached.get("timestamp", 0) < 600):
            return cached

    token = get_token(user, password)
    perfil = get_user(token)
    cursos = get_cursos(token)
    tareas = get_tareas(token)

    data = {
        "token": token,
        "perfil": perfil,
        "cursos": cursos,
        "tareas": tareas,
        "timestamp": now,
    }
    with state_lock:
        user_cache[user] = data

    # Check due date changes for all chats logged into this user account
    with state_lock:
        matching_chats = [
            cid for cid, s in chat_sessions.items() if s.get("user") == user
        ]
    for cid in matching_chats:
        closer, later = detect_due_date_changes(cid, tareas)
        if client and (closer or later):
            send_due_date_change_notifications(client, cid, closer, later)

    return data


def format_due_badge(dt: Optional[datetime], now: datetime) -> str:
    if not dt:
        return "📅 Sin fecha"
    delta = dt - now
    total_sec = delta.total_seconds()
    days = (dt.date() - now.date()).days
    date_pretty = dt.strftime("%d/%b/%Y %H:%M")

    if total_sec < 0:
        badge = f"✅ Venció ({date_pretty})"
    elif days == 0:
        hours_left = max(0, int(total_sec // 3600))
        mins_left = max(0, int((total_sec % 3600) // 60))
        badge = f"🚨 <b>VENCE HOY</b> (en <b>{hours_left}h {mins_left}m</b> — {dt.strftime('%H:%M')})"
    elif days == 1:
        remaining = format_time_diff(total_sec)
        badge = f"⚠️ <b>VENCE MAÑANA</b> (en <b>{remaining}</b> — {date_pretty})"
    elif days <= 7:
        remaining = format_time_diff(total_sec)
        badge = f"⏳ En <b>{remaining}</b> ({date_pretty})"
    else:
        badge = f"📅 En <b>{days} días</b> ({date_pretty})"

    # Append unusual time warning for upcoming tasks
    if total_sec >= 0:
        time_warn = get_unusual_time_warning(dt)
        if time_warn:
            badge += f"\n  {time_warn}"
    return badge


def build_main_keyboard(chat_id: int):
    alerts_on = chat_sessions.get(chat_id, {}).get("alerts", True)
    alert_label = "🔔 Alertas Auto: ON" if alerts_on else "🔕 Alertas Auto: OFF"
    return {
        "inline_keyboard": [
            [
                {"text": "📋 Próximas Tareas", "callback_data": "pendientes"},
                {"text": "🚨 Esta Semana", "callback_data": "semana"},
            ],
            [
                {"text": "📚 Mis Cursos", "callback_data": "cursos"},
                {"text": "👤 Mi Perfil", "callback_data": "perfil"},
            ],
            [
                {"text": "📅 Todas las Tareas", "callback_data": "todas"},
                {"text": "🔄 Actualizar SIASE", "callback_data": "refresh"},
            ],
            [
                {"text": alert_label, "callback_data": "toggle_alerts"},
                {"text": "🗑️ Reset / Salir", "callback_data": "reset"},
            ],
        ]
    }


def format_perfil(data: Dict[str, Any]) -> str:
    perfiles = data.get("perfil", [])
    if not perfiles:
        return "❌ No se encontró información del perfil."
    lines = ["👤 <b>Perfil Académico NEXUS / SIASE</b>\n"]
    for p in perfiles:
        deps = ", ".join(p.get("Dependencias", [])) or "N/A"
        lines.append(
            f"• <b>Nombre:</b> {html.escape(str(p.get('NombreAlumno', '')))}\n"
            f"• <b>Matrícula:</b> <code>{html.escape(str(p.get('NombreUsuario', '')))}</code>\n"
            f"• <b>Correo:</b> {html.escape(str(p.get('CorreoUniversitario', '')))}\n"
            f"• <b>Dependencias:</b> {html.escape(deps)}"
        )
    return "\n\n".join(lines)


def format_cursos(data: Dict[str, Any]) -> str:
    cursos = data.get("cursos", [])
    if not cursos:
        return "📚 No se encontraron cursos activos."
    lines = [f"📚 <b>Mis Cursos Activos ({len(cursos)})</b>\n"]
    for i, c in enumerate(cursos, 1):
        nombre = html.escape(str(c.get("Nombre", "Sin nombre")))
        grupos = ", ".join(c.get("Grupos", [])) or "N/A"
        profs = "\n   └ 👨‍🏫 ".join(html.escape(p) for p in c.get("Profesores", [])) or "Sin profesor asignado"
        lines.append(
            f"<b>{i}. {nombre}</b> (Grupo <code>{html.escape(grupos)}</code>)\n"
            f"   └ 👨‍🏫 {profs}"
        )
    return "\n\n".join(lines)


def format_tareas(data: Dict[str, Any], mode: str = "pendientes", course_filter: Optional[str] = None) -> str:
    tareas = data.get("tareas", [])
    now = datetime.now()

    upcoming_items = []
    past_items = []
    for t in tareas:
        dt = parse_due_date(t.get("FechaEntrega"))
        curso = str(t.get("Curso") or "General")
        desc = str(t.get("Descripcion") or "Sin descripción").strip()
        if course_filter and course_filter.lower() not in curso.lower() and course_filter.lower() not in desc.lower():
            continue
        if dt and dt >= now:
            # Sort key: seconds until due date (closest first!)
            upcoming_items.append(((dt - now).total_seconds(), dt, curso, desc))
        else:
            past_items.append((dt or datetime.min, dt, curso, desc))

    # Strictly sort upcoming tasks by closest due date/time first
    upcoming_items.sort(key=lambda x: x[0])
    # Sort past tasks by most recently expired first
    past_items.sort(key=lambda x: x[0], reverse=True)

    if mode == "pendientes":
        filtered = [(dt, curso, desc) for _, dt, curso, desc in upcoming_items]
        title = f"📋 <b>Tareas a Vencer — De Más Próxima a Más Lejana ({len(filtered)})</b>"
    elif mode == "semana":
        filtered = [
            (dt, curso, desc)
            for _, dt, curso, desc in upcoming_items
            if dt and 0 <= (dt.date() - now.date()).days <= 7
        ]
        title = f"🚨 <b>Entregas en los Próximos 7 Días — Más Próximas Primero ({len(filtered)})</b>"
    else:
        filtered = (
            [(dt, curso, desc) for _, dt, curso, desc in upcoming_items]
            + [(dt, curso, desc) for _, dt, curso, desc in past_items]
        )
        title = f"📅 <b>Todas las Tareas (Próximas primero, vencidas al final — {len(filtered)})</b>"

    if course_filter:
        title += f"\n🔎 Filtro: <i>{html.escape(course_filter)}</i>"

    if not filtered:
        return f"{title}\n\n🎉 ¡No hay tareas pendientes en esta categoría!"

    lines = [title + "\n"]
    for idx, (dt, curso, desc) in enumerate(filtered[:25], 1):
        badge = format_due_badge(dt, now)
        lines.append(
            f"<b>{idx}. {html.escape(desc)}</b>\n"
            f"  📘 <i>{html.escape(curso)}</i>\n"
            f"  {badge}"
        )

    if len(filtered) > 25:
        lines.append(f"\n<i>...y {len(filtered) - 25} tareas más.</i>")

    return "\n\n".join(lines)


def handle_natural_text(text: str, data: Dict[str, Any]) -> str:
    q = text.lower().strip()
    if any(w in q for w in ["hola", "buenas", "hey", "ayuda", "help"]):
        nombre = data.get("perfil", [{}])[0].get("NombreAlumno", "Estudiante")
        return (
            f"👋 ¡Hola, <b>{html.escape(nombre)}</b>!\n\n"
            "Soy tu asistente de <b>Nexus / SIASE UANL</b>. Puedes usar los botones o escribirme:\n"
            "• <i>«¿Qué tengo para esta semana?»</i>\n"
            "• <i>«Tareas de Cálculo»</i> / <i>«Mecánica»</i> / <i>«Liderazgo»</i>\n"
            "• <i>«Mis cursos»</i> o <i>«Profesores»</i>\n"
            "• <code>/reset</code> o <code>/clear</code> para borrar tu sesión"
        )
    if any(w in q for w in ["semana", "hoy", "mañana", "urgente", "pronto"]):
        return format_tareas(data, mode="semana")
    if any(w in q for w in ["curso", "materia", "profe", "maestro", "grupo"]):
        return format_cursos(data)
    if any(w in q for w in ["perfil", "correo", "matricula", "matrícula", "quien soy"]):
        return format_perfil(data)
    if any(w in q for w in ["todas", "semestre", "pasadas"]):
        return format_tareas(data, mode="todas")

    for c in data.get("cursos", []):
        cname = str(c.get("Nombre", ""))
        words = [w for w in cname.lower().split() if len(w) > 3]
        if any(w in q for w in words):
            return format_tareas(data, mode="todas", course_filter=cname)

    return format_tareas(data, mode="pendientes")


def log_io(tag: str, chat_id: Any, detail: str):
    ts = datetime.now().strftime("%H:%M:%S")
    clean = " ".join(detail.splitlines()).strip()
    if len(clean) > 160:
        clean = clean[:157] + "..."
    print(f"[{ts}] [{tag}] [chat:{chat_id}] {clean}", flush=True)


def strip_html(text: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", text)


def send_message(client: httpx.Client, chat_id: int, text: str, reply_markup: Optional[Dict] = None):
    log_io("BOT -> OUT", chat_id, strip_html(text))
    full_text = text + SIGNATURE
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "text": full_text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    client.post(f"{API_BASE}/sendMessage", json=payload, timeout=15.0)


def try_delete_message(client: httpx.Client, chat_id: int, message_id: int):
    try:
        client.post(
            f"{API_BASE}/deleteMessage",
            json={"chat_id": chat_id, "message_id": message_id},
            timeout=5.0,
        )
        log_io("SYS", chat_id, f"Deleted sensitive login message (id={message_id})")
    except Exception:
        pass


def answer_callback(client: httpx.Client, callback_id: str, text: str = ""):
    client.post(
        f"{API_BASE}/answerCallbackQuery",
        json={"callback_query_id": callback_id, "text": text},
        timeout=10.0,
    )


def register_commands(client: httpx.Client):
    commands = [
        {"command": "start", "description": "Menú principal / Estado de sesión"},
        {"command": "login", "description": "Iniciar sesión: /login MATRICULA PASSWORD"},
        {"command": "pendientes", "description": "Tareas a vencer (de más próxima a más lejana)"},
        {"command": "semana", "description": "Tareas que vencen hoy o esta semana"},
        {"command": "cursos", "description": "Mis cursos, grupos y profesores"},
        {"command": "perfil", "description": "Mi información de alumno SIASE/Nexus"},
        {"command": "alertas", "description": "Activar/desactivar recordatorios automáticos"},
        {"command": "reset", "description": "Cerrar sesión y borrar mis datos del bot"},
    ]
    client.post(f"{API_BASE}/setMyCommands", json={"commands": commands}, timeout=15.0)


def clear_chat_session(chat_id: int) -> Optional[str]:
    with state_lock:
        session = chat_sessions.pop(chat_id, None)
        if session:
            u = session.get("user")
            still_used = any(s.get("user") == u for s in chat_sessions.values())
            if u and not still_used:
                user_cache.pop(u, None)
            return u
    return None


def send_login_prompt(client: httpx.Client, chat_id: int):
    msg = (
        "🔐 <b>Bienvenido a Nexus UANL Bot</b>\n\n"
        "Para consultar tus tareas, cursos y recibir alertas automáticas (incluyendo cambios de fecha "
        "y avisos si una tarea vence antes de las 11:00 PM), inicia sesión con tu cuenta de SIASE:\n\n"
        "👉 <code>/login TU_MATRICULA TU_CONTRASEÑA</code>\n\n"
        "<i>🔒 Tu mensaje con la contraseña se borrará automáticamente del chat y puedes usar "
        "<code>/reset</code> o <code>/clear</code> en cualquier momento para borrar tu sesión.</i>"
    )
    send_message(client, chat_id, msg)


def check_and_send_notifications_for_chat(
    client: httpx.Client, chat_id: int, force_sync: bool = False
):
    with state_lock:
        session = chat_sessions.get(chat_id)
        if not session or not session.get("alerts", True):
            return
        user = session["user"]
        password = session["password"]
        sent_alerts: Set[str] = session.setdefault("sent_alerts", set())

    try:
        data = fetch_nexus_data(
            user, password, force_refresh=force_sync, chat_id=chat_id, client=client
        )
    except Exception:
        return

    now = datetime.now()
    tareas = data.get("tareas", [])

    # Sort upcoming tasks by closest first so notifications also list the most urgent first
    upcoming_sorted = []
    for t in tareas:
        dt = parse_due_date(t.get("FechaEntrega"))
        if dt and dt >= now:
            upcoming_sorted.append(((dt - now).total_seconds(), dt, t))
    upcoming_sorted.sort(key=lambda x: x[0])

    thresholds: Tuple[Tuple[str, float, float], ...] = (
        ("48h", 48.0, 24.0),
        ("24h", 24.0, 6.0),
        ("6h", 6.0, 2.0),
        ("2h", 2.0, 0.0),
    )

    urgent_lines = []
    for sec_left, dt, t in upcoming_sorted:
        hours_left = sec_left / 3600.0
        curso = str(t.get("Curso") or "General")
        desc = str(t.get("Descripcion") or "Sin descripción").strip()
        task_id = f"{curso}|{desc}|{dt.isoformat()}"

        for label, max_h, min_h in thresholds:
            if min_h <= hours_left <= max_h:
                alert_key = f"{task_id}:{label}"
                with state_lock:
                    if alert_key in sent_alerts:
                        break
                    sent_alerts.add(alert_key)

                h_int = int(hours_left)
                m_int = int((hours_left - h_int) * 60)
                time_warn = get_unusual_time_warning(dt)
                warn_block = f"\n  {time_warn}" if time_warn else ""
                urgent_lines.append(
                    f"• <b>{html.escape(desc)}</b>\n"
                    f"  📘 <i>{html.escape(curso)}</i>\n"
                    f"  ⏰ Vence en <b>{h_int}h {m_int}m</b> ({dt.strftime('%d/%b %H:%M')}){warn_block}"
                )
                break

    if urgent_lines:
        header = (
            "🔔 <b>¡ALERTA AUTOMÁTICA DE TAREAS NEXUS!</b>\n"
            "Tienes entregas próximas a vencer (ordenadas de más próxima a más lejana):\n\n"
        )
        send_message(client, chat_id, header + "\n\n".join(urgent_lines), reply_markup=build_main_keyboard(chat_id))


def auto_notifier_loop():
    """Background daemon thread that checks all logged-in chats every 5 minutes and syncs SIASE every 15 minutes."""
    cycle = 0
    with httpx.Client(timeout=30.0) as client:
        while True:
            time.sleep(300)
            cycle += 1
            force_sync = (cycle % 3 == 0)  # Force live SIASE sync every 15 mins to detect due date changes
            with state_lock:
                active_chat_ids = list(chat_sessions.keys())
            for cid in active_chat_ids:
                try:
                    check_and_send_notifications_for_chat(client, cid, force_sync=force_sync)
                except Exception as e:
                    print(f"Notifier error for chat {cid}: {e}")


def process_action(client: httpx.Client, chat_id: int, action: str):
    if action in ("reset", "clear", "logout", "salir"):
        old_user = clear_chat_session(chat_id)
        if old_user:
            send_message(
                client,
                chat_id,
                f"🗑️ <b>Sesión cerrada y datos borrados</b> para la matrícula <code>{html.escape(old_user)}</code>.\n\n"
                "Usa <code>/login MATRICULA PASSWORD</code> cuando quieras volver a entrar.",
            )
        else:
            send_message(client, chat_id, "ℹ️ No tenías ninguna sesión activa. Usa <code>/login MATRICULA PASSWORD</code>.")
        return

    with state_lock:
        session = chat_sessions.get(chat_id)

    if not session:
        send_login_prompt(client, chat_id)
        return

    user = session["user"]
    password = session["password"]

    if action in ("toggle_alerts", "alertas", "notificaciones"):
        with state_lock:
            current = session.get("alerts", True)
            session["alerts"] = not current
            new_state = session["alerts"]
        status_str = "ACTIVADAS 🔔" if new_state else "DESACTIVADAS 🔕"
        send_message(
            client,
            chat_id,
            f"⚙️ Las alertas automáticas de tareas ahora están: <b>{status_str}</b>\n\n"
            "• Recordatorios a las <b>48h, 24h, 6h y 2h</b> antes de vencer.\n"
            "• 🚨 Alerta con alarma si una tarea se <b>adelanta</b> a una fecha más cercana.\n"
            "• 🎉 Aviso si una tarea se <b>aplaza</b> con más tiempo.\n"
            "• ⚠️ Advertencia si no vence a las 11:59 PM (o antes de las 11:00 PM).",
            reply_markup=build_main_keyboard(chat_id),
        )
        return

    try:
        force = action == "refresh"
        if force:
            send_message(client, chat_id, "🔄 Sincronizando en vivo con SIASE y verificando cambios de fecha...")
        data = fetch_nexus_data(user, password, force_refresh=force, chat_id=chat_id, client=client)
    except Exception as e:
        send_message(
            client,
            chat_id,
            f"❌ <b>Error al conectar con SIASE/Nexus:</b>\n<code>{html.escape(str(e))}</code>\n\n"
            "Verifica tus credenciales con <code>/login MATRICULA PASSWORD</code>.",
        )
        return

    if action in ("start", "menu", "refresh"):
        nombre = data.get("perfil", [{}])[0].get("NombreAlumno", user)
        now = datetime.now()
        upcoming = [
            t for t in data.get("tareas", [])
            if (dt := parse_due_date(t.get("FechaEntrega"))) and dt >= now
        ]
        week = [
            t for t in upcoming
            if (dt := parse_due_date(t.get("FechaEntrega"))) and 0 <= (dt.date() - now.date()).days <= 7
        ]
        early_tasks = [
            t for t in upcoming
            if (dt := parse_due_date(t.get("FechaEntrega"))) and (dt.hour, dt.minute) != (23, 59)
        ]
        early_warning = ""
        if early_tasks:
            early_warning = (
                f"\n⚠️ <b>¡Atención!</b> Tienes <b>{len(early_tasks)}</b> entregas próximas que "
                f"<b>NO vencen a las 11:59 PM</b> (revisa <i>Próximas Tareas</i>).\n"
            )

        msg = (
            f"🎓 <b>Nexus UANL Bot Activo</b>\n\n"
            f"👤 <b>Alumno:</b> {html.escape(nombre)} (<code>{html.escape(user)}</code>)\n"
            f"📚 <b>Cursos activos:</b> {len(data.get('cursos', []))}\n"
            f"📋 <b>Tareas pendientes:</b> {len(upcoming)}\n"
            f"🚨 <b>Vencen esta semana:</b> {len(week)}\n"
            f"🔔 <b>Alertas automáticas:</b> {'ON' if session.get('alerts', True) else 'OFF'}"
            f"{early_warning}\n"
            f"Selecciona una opción o escríbeme cualquier duda sobre tus materias:"
        )
        send_message(client, chat_id, msg, reply_markup=build_main_keyboard(chat_id))
    elif action in ("pendientes", "tareas"):
        send_message(client, chat_id, format_tareas(data, mode="pendientes"), reply_markup=build_main_keyboard(chat_id))
    elif action in ("semana", "urgentes"):
        send_message(client, chat_id, format_tareas(data, mode="semana"), reply_markup=build_main_keyboard(chat_id))
    elif action == "cursos":
        send_message(client, chat_id, format_cursos(data), reply_markup=build_main_keyboard(chat_id))
    elif action == "perfil":
        send_message(client, chat_id, format_perfil(data), reply_markup=build_main_keyboard(chat_id))
    elif action == "todas":
        send_message(client, chat_id, format_tareas(data, mode="todas"), reply_markup=build_main_keyboard(chat_id))
    else:
        reply = handle_natural_text(action, data)
        send_message(client, chat_id, reply, reply_markup=build_main_keyboard(chat_id))


def main():
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in .env")

    print("Starting NexusBot (@NexusEsGayBot) in manual-login mode...", flush=True)
    notifier_thread = threading.Thread(target=auto_notifier_loop, daemon=True)
    notifier_thread.start()

    offset = 0
    with httpx.Client(timeout=35.0) as client:
        register_commands(client)
        print("Bot is polling for messages (no pre-loaded credentials)...", flush=True)
        while True:
            try:
                resp = client.get(
                    f"{API_BASE}/getUpdates",
                    params={"offset": offset, "timeout": 25},
                )
                updates = resp.json().get("result", [])
                for upd in updates:
                    offset = upd["update_id"] + 1

                    if "callback_query" in upd:
                        cb = upd["callback_query"]
                        cb_id = cb["id"]
                        chat_id = cb["message"]["chat"]["id"]
                        from_user = cb.get("from", {}).get("username") or cb.get("from", {}).get("first_name", "user")
                        data_str = cb.get("data", "start")
                        log_io(f"USER -> IN (@{from_user})", chat_id, f"[Button: {data_str}]")
                        answer_callback(client, cb_id)
                        process_action(client, chat_id, data_str)

                    elif "message" in upd:
                        msg = upd["message"]
                        chat_id = msg["chat"]["id"]
                        message_id = msg.get("message_id")
                        from_user = msg.get("from", {}).get("username") or msg.get("from", {}).get("first_name", "user")
                        text = (msg.get("text") or "").strip()
                        if not text:
                            continue

                        if text.lower().startswith("/login"):
                            parts = text.split(maxsplit=2)
                            masked_u = parts[1].strip() if len(parts) > 1 else "?"
                            log_io(f"USER -> IN (@{from_user})", chat_id, f"/login {masked_u} ********")
                            if message_id:
                                try_delete_message(client, chat_id, message_id)
                            if len(parts) < 3:
                                send_message(
                                    client,
                                    chat_id,
                                    "🔑 <b>Formato de inicio de sesión:</b>\n<code>/login TU_MATRICULA TU_CONTRASEÑA</code>",
                                )
                            else:
                                u, p = parts[1].strip(), parts[2].strip()
                                send_message(client, chat_id, f"🔐 Conectando matrícula <code>{html.escape(u)}</code> con SIASE...")
                                try:
                                    with state_lock:
                                        chat_sessions[chat_id] = {
                                            "user": u,
                                            "password": p,
                                            "alerts": True,
                                            "sent_alerts": set(),
                                            "known_due_dates": None,
                                        }
                                    fetch_nexus_data(u, p, force_refresh=True, chat_id=chat_id, client=client)
                                    process_action(client, chat_id, "start")
                                    check_and_send_notifications_for_chat(client, chat_id, force_sync=False)
                                except Exception as e:
                                    clear_chat_session(chat_id)
                                    send_message(
                                        client,
                                        chat_id,
                                        f"❌ <b>No se pudo iniciar sesión en SIASE:</b>\n<code>{html.escape(str(e))}</code>",
                                    )
                            continue

                        log_io(f"USER -> IN (@{from_user})", chat_id, text)
                        if text.startswith("/"):
                            cmd = text.split()[0].lstrip("/").split("@")[0].lower()
                            process_action(client, chat_id, cmd)
                        else:
                            process_action(client, chat_id, text)

            except Exception as err:
                print(f"Polling error: {err}", flush=True)
                time.sleep(3)


if __name__ == "__main__":
    main()
