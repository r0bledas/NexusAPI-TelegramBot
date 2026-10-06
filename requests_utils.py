import requests
import json
from tokens import get_token


def get_area_ids(token):
    try:
        url = "https://api.nexus.uanl.mx/WebApi/Seguridad/ConsultarPerfil"
        headers = {
            'accept': 'application/json, text/plain, */*',
            'content-type': 'application/json',
            'origin': 'https://plataformanexus.uanl.mx',
            'referer': 'https://plataformanexus.uanl.mx/',
            'sistemaid': '1',
            'token': token,
            'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
        }
        response = requests.post(url, headers=headers, data=json.dumps({}))
        data_json = response.json()
        area_ids = []
        for cuenta in data_json.get("Persona", {}).get("Cuentas", []):
            for area in cuenta.get("AreasAcademicas", []):
                aid = area.get("AreaAcademicaId") or area.get("AreaAcademica", {}).get("AreaAcademicaId")
                if aid and str(aid) not in area_ids:
                    area_ids.append(str(aid))
        return area_ids if area_ids else ['44']
    except Exception:
        return ['44']


import concurrent.futures


def _fetch_portafolio_course(token, area_id, curso_id):
    try:
        url = "https://api.nexus.uanl.mx/WebApi/Portafolio/ConsultarPortafolio"
        headers = {
            'accept': 'application/json, text/plain, */*',
            'areaacademicaid': str(area_id),
            'content-type': 'application/json',
            'origin': 'https://plataformanexus.uanl.mx',
            'referer': 'https://plataformanexus.uanl.mx/',
            'rolid': '5',
            'sistemaid': '1',
            'token': token,
            'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
        }
        r = requests.post(url, headers=headers, data=json.dumps({"CursoId": int(curso_id)}), timeout=15)
        return int(curso_id), r.json().get("ElementosEvaluables", [])
    except Exception:
        return int(curso_id), []


def get_cursos(token):

  url = "https://api.nexus.uanl.mx/WebApi/Curso/ConsultarCarpetaCursos"

  payload = json.dumps({
    "CarpetaId": 0,
    "Pagina": 1,
    "Paginacion": 10
  })
  area_id = get_area_ids(token)[0]
  headers = {
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'es-MX,es-419;q=0.9,es;q=0.8,en;q=0.7',
    'areaacademicaid': str(area_id),
    'content-type': 'application/json',
    'origin': 'https://plataformanexus.uanl.mx',
    'priority': 'u=1, i',
    'referer': 'https://plataformanexus.uanl.mx/',
    'rolid': '5',
    'sec-ch-ua': '"Not;A=Brand";v="99", "Google Chrome";v="139", "Chromium";v="139"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Linux"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-site',
    'sistemaid': '1',
    'token': token,
    'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
  }

  response = requests.request("POST", url, headers=headers, data=payload)

  # Convertimos la respuesta a JSON
  data_json = response.json()
  # Carpeta → Cursos → Nombre y Profesores
  cursos_json = []

  for carpeta in data_json.get("Carpetas", []):
      for curso in carpeta.get("Cursos", []):
          # Extraer información del curso
          curso_id = curso.get("CursoId")
          nombre_curso = curso.get("Nombre")
          fecha_inicio = curso.get("FechaInicio")
          fecha_fin = curso.get("FechaFin")
          
          # Extraer profesores
          profesores = []
          for prof in curso.get("Profesores", []):
              nombre_profesor = f"{prof.get('Nombre')} {prof.get('ApellidoPaterno')} {prof.get('ApellidoMaterno')}"
              correo = prof.get("CorreoUniversitario")
              profesores.append(f"{nombre_profesor} ({correo})")
          
          # Extraer grupos
          grupos = [grupo.get("Nombre") for grupo in curso.get("Grupos", [])]

          # Construir diccionario del curso
          curso_info = {
              "CursoId": curso_id,
              "Nombre": nombre_curso,
              "FechaInicio": fecha_inicio,
              "FechaFin": fecha_fin,
              "Profesores": profesores,
              "Grupos": grupos
          }

          cursos_json.append(curso_info)

  return cursos_json


def get_tareas(token):
    url = "https://api.nexus.uanl.mx/WebApi/Tarea/ConsultarTareas"

    payload = json.dumps({
    })

    area_id = get_area_ids(token)[0]
    headers = {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'es-MX,es-419;q=0.9,es;q=0.8,en;q=0.7',
        'areaacademicaid': str(area_id),
        'content-type': 'application/json',
        'origin': 'https://plataformanexus.uanl.mx',
        'priority': 'u=1, i',
        'referer': 'https://plataformanexus.uanl.mx/',
        'rolid': '5',
        'sec-ch-ua': '"Not;A=Brand";v="99", "Google Chrome";v="139", "Chromium";v="139"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Linux"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'sistemaid': '1',
        'token': token,
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
    }

    response = requests.post(url, headers=headers, data=payload)
    data_json = response.json()
    raw_tareas = data_json.get("Tareas", [])

    # Fetch Portafolio in parallel for all distinct CursoIds to get submission status, grades, and feedback
    curso_ids = sorted({
        int(t.get("Curso", {}).get("CursoId"))
        for t in raw_tareas
        if t.get("Curso", {}).get("CursoId")
    })
    portafolio_map = {}
    if curso_ids:
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
            futures = [ex.submit(_fetch_portafolio_course, token, area_id, cid) for cid in curso_ids]
            for fut in concurrent.futures.as_completed(futures):
                cid, elementos = fut.result()
                for el in elementos:
                    el_id = el.get("ElementoId")
                    if el_id is not None:
                        portafolio_map[(cid, int(el_id))] = el

    tareas_json = []

    for tarea in raw_tareas:
        curso_obj = tarea.get("Curso", {}) or {}
        cid = curso_obj.get("CursoId")
        el_id = tarea.get("ElementoId")
        pf = portafolio_map.get((int(cid), int(el_id)), {}) if (cid and el_id) else {}

        entregas = pf.get("Entregas") or []
        cal_obj = pf.get("Calificacion")
        cal_ex = pf.get("CalificacionExamen")

        calificacion = None
        if isinstance(cal_obj, dict) and cal_obj.get("Valor") is not None:
            calificacion = float(cal_obj.get("Valor"))
        elif isinstance(cal_ex, dict):
            if cal_ex.get("Calificacion") is not None:
                calificacion = float(cal_ex.get("Calificacion"))
            elif cal_ex.get("Valor") is not None:
                calificacion = float(cal_ex.get("Valor"))

        entregada = bool(entregas) or (calificacion is not None) or (tarea.get("CantidadEntregados", 0) > 0)

        archivo_entregado = None
        fecha_subida = None
        if entregas:
            doc = entregas[0].get("Documento") or {}
            archivo_entregado = doc.get("Nombre")
            fecha_subida = entregas[0].get("FechaModificacion") or doc.get("FechaCreacion")

        retros = pf.get("Retroalimentaciones") or []
        retro_texto = None
        if retros and isinstance(retros[0], dict):
            retro_texto = retros[0].get("Descripcion")

        valor = tarea.get("Valor") if tarea.get("Valor") is not None else pf.get("Valor")
        puntos_obtenidos = None
        if calificacion is not None and valor is not None:
            try:
                puntos_obtenidos = round((float(calificacion) * float(valor)) / 100.0, 2)
            except Exception:
                pass

        tarea_info = {
            "ElementoId": el_id,
            "TipoElementoId": tarea.get("TipoElementoId"),
            "Descripcion": tarea.get("Descripcion"),
            "FechaEntrega": tarea.get("FechaFin"),
            "Curso": curso_obj.get("Nombre"),
            "CursoId": cid,
            "Valor": valor,
            "EnEquipo": bool(tarea.get("EnEquipo") or pf.get("EnEquipo")),
            "Entregada": entregada,
            "ArchivoEntregado": archivo_entregado,
            "FechaSubida": fecha_subida,
            "Calificacion": calificacion,
            "PuntosObtenidos": puntos_obtenidos,
            "Retroalimentacion": retro_texto,
        }

        tareas_json.append(tarea_info)

    return tareas_json

# Ejemplo de uso:
# token = "TU_TOKEN_AQUI"
# tareas = get_tareas(token)
# print(json.dumps(tareas, indent=4, ensure_ascii=False))

def parse_user(data_json):
    persona = data_json.get("Persona", {})
    nombre_completo = " ".join(filter(None, [
        persona.get("Nombre"),
        persona.get("ApellidoPaterno"),
        persona.get("ApellidoMaterno")
    ])).strip()

    userdata = []

    for cuenta in persona.get("Cuentas", []):
        dependencias = list({  # set para evitar duplicados automáticamente
            area.get("AreaAcademica", {}).get("Dependencia", {}).get("NombreCorto")
            for area in cuenta.get("AreasAcademicas", [])
            if area.get("AreaAcademica", {}).get("Dependencia", {}).get("NombreCorto")
        })

        userdata.append({
            "NombreAlumno": nombre_completo,
            "NombreUsuario": cuenta.get("NombreUsuario"),
            "CorreoUniversitario": cuenta.get("CorreoUniversitario"),
            "Dependencias": dependencias
        })

    return userdata


def get_user(token):
  url = "https://api.nexus.uanl.mx/WebApi/Seguridad/ConsultarPerfil"

  payload = json.dumps({})
  headers = {
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'es-MX,es-419;q=0.9,es;q=0.8,en;q=0.7',
    'content-type': 'application/json',
    'origin': 'https://plataformanexus.uanl.mx',
    'priority': 'u=1, i',
    'referer': 'https://plataformanexus.uanl.mx/',
    'sec-ch-ua': '"Not;A=Brand";v="99", "Google Chrome";v="139", "Chromium";v="139"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Linux"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-site',
    'sistemaid': '1',
    'token': token,
    'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
  }

  response = requests.request("POST", url, headers=headers, data=payload)
  data_json = response.json()

  userdata = parse_user(data_json)

  return userdata
