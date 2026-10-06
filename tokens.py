import httpx
import re
from urllib.parse import urlparse, parse_qs
def get_token(user, password):
    url_login_page = "https://deimos.dgi.uanl.mx/cgi-bin/wspd_cgi.sh/login.htm"
    url = "https://deimos.dgi.uanl.mx/cgi-bin/wspd_cgi.sh/eselcarrera.htm"
    url_nexus = "https://api.nexus.uanl.mx/WebApi/Seguridad/CrearSesionSIASE"

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://deimos.dgi.uanl.mx",
        "Referer": "https://deimos.dgi.uanl.mx/cgi-bin/wspd_cgi.sh/login.htm",
        "User-Agent": "Mozilla/5.0"
    }

    with httpx.Client(timeout=30.0) as client:
        login_page_res = client.get(url_login_page, headers={"User-Agent": "Mozilla/5.0"})
        token_match = re.search(r'name="HTMLToken"\s+value="([^"]+)"', login_page_res.text, re.IGNORECASE)
        html_token = token_match.group(1) if token_match else ""

        data = {
            "HTMLTipCve": "01",
            "HTMLUsuCve": user,
            "HTMLPassword": password,
            "HTMLPrograma": "",
            "HTMLToken": html_token
        }

        res = client.post(url, data=data, headers=headers)

    headers_nexus = {
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64; rv:136.0) Gecko/20100101 Firefox/136.0",
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.5",
        "accept-encoding": "gzip, deflate, br, zstd",
        "control":  None,
        "clienteip": "0.0.0.0",
        "usuario": None,
        "usuarioclave": None,
        "tipoclave": "01",
        "sistemaid": "1",
        "content-type": "application/json",
        "content-length": "2",
        "origin": "https://plataformanexus.uanl.mx",
        "referer": "https://plataformanexus.uanl.mx/",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "te": "trailers"
    }

    # Aquí sí usamos el contenido de la respuesta
    html_content = res.text

    # Regex para extraer el contenido de attr("action", "...") dentro de #idfrNexus
    pattern = r'\$\(\s*"#idfrNexus"\s*\)\.attr\(\s*"action"\s*,\s*"([^"]+)"\s*\)'

    match = re.search(pattern, html_content, re.DOTALL)
    if match:
        url_login = match.group(1)
    else:
        raise ValueError("Credenciales inválidas o no se encontró el enlace a Nexus en SIASE.")
    url_login = url_login.split('=')
    control = url_login[2] + "="
    usu = url_login[1].split("&Ctrl")[0]
    headers_nexus["control"] = control
    headers_nexus["usuario"] = usu
    headers_nexus["usuarioclave"] = data["HTMLUsuCve"]


    asknexus = httpx.post(url_nexus,  headers=headers_nexus, json={}, timeout=30.0)
    resp_json = asknexus.json()
    if not resp_json.get('Sesion') or not resp_json['Sesion'].get('Token'):
        raise ValueError(f"Error al crear sesión en Nexus: {resp_json}")
    token = resp_json['Sesion']['Token']
    return token

