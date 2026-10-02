"""
Puesta a punto: la lista de servicios externos que el proyecto necesita
(Configuración › Puesta a punto) y su estado. Cada entrada dice para qué
sirve, cómo se paga, dónde se consigue y qué variables van en el .env del
servidor. El estado se calcula SOLO con bool(os.environ.get(var)): el valor
de una llave nunca sale de aquí, ni llega a una plantilla ni a una alerta.

Vivía en dashboard.py (SERVICIOS_LLAVES / _estado_llaves, que siguen ahí como
alias de SERVICIOS / estado); se movió para que alertas.py lo lea sin importar
el dashboard. `_llaves_visibles` (qué rol ve las tarjetas) se queda en
dashboard.py.
"""
import os

from flask_babel import gettext

import idiomas


# Configuración › Puesta a punto: una tarjeta por servicio externo. Cada
# entrada dice para qué sirve, cómo se paga, dónde se consigue y qué variables
# van en el .env del servidor. El estado se calcula SOLO con
# bool(os.environ.get(var)) — el valor de una llave nunca sale de aquí ni
# llega a la plantilla. `{callback_meli}` en un paso se reemplaza por la URL
# real del callback cuando hay request (ver estado).
SERVICIOS = (
    {
        "id": "anthropic",
        "nombre": idiomas.N_("Anthropic (guiones y prompts)"),
        "para_que": idiomas.N_("Escribe los 5 prompts por idea y los guiones de las finales."),
        "costo": idiomas.N_("Se paga por uso: centavos por guion."),
        "url": "https://console.anthropic.com/settings/keys",
        "url_texto": "console.anthropic.com › API keys",
        "variables": ["ANTHROPIC_API_KEY"],
        "nota": idiomas.N_("Sin ella no hay prompts ni guiones."),
        "pasos": [
            idiomas.N_("Entra a console.anthropic.com e inicia sesión (o crea la cuenta de la empresa)."),
            idiomas.N_("En «Billing» carga saldo o pon una tarjeta: sin saldo la llave existe pero no responde."),
            idiomas.N_("Ve a «API keys» › «Create key», ponle un nombre (por ejemplo «creatv») y cópiala: solo se muestra una vez."),
            idiomas.N_("Pégala como ANTHROPIC_API_KEY en el .env del servidor y reinicia los dos servicios."),
        ],
    },
    {
        "id": "wavespeed",
        "nombre": idiomas.N_("WaveSpeed (videos e imágenes de Crear)"),
        "para_que": idiomas.N_("Genera cada video (Wan 3.0, Kling O3 Pro, Seedance 2.5) e imagen (Seedream) de Crear y de los lotes de Sprints."),
        "costo": idiomas.N_("Por segundo de video y por imagen: el precio se muestra antes de cada generación."),
        "url": "https://wavespeed.ai/",
        "url_texto": "wavespeed.ai › API Keys",
        "variables": ["WAVESPEED_API_KEY"],
        "nota": idiomas.N_("Sin ella no se genera ningún video ni imagen en Crear ni en Sprints."),
        "pasos": [
            idiomas.N_("Crea la cuenta en wavespeed.ai."),
            idiomas.N_("Carga saldo en «Billing»: sin saldo la llave existe pero cada generación falla."),
            idiomas.N_("Ve a «API Keys», crea una llave nueva y cópiala: solo se muestra una vez."),
            idiomas.N_("Pégala como WAVESPEED_API_KEY en el .env del servidor."),
            idiomas.N_("Reinicia los dos servicios (iaplusyou y creatv-worker): el worker es el que la usa al generar."),
        ],
    },
    {
        "id": "fal",
        "nombre": idiomas.N_("fal.ai (voz y música)"),
        "para_que": idiomas.N_("Voz en off (ElevenLabs), subtítulos por palabra (Whisper) y música (Stable Audio) de las finales."),
        "costo": idiomas.N_("Se paga por uso: alrededor de $0.05 por final."),
        "url": "https://fal.ai/dashboard/keys",
        "url_texto": "fal.ai › Dashboard › Keys",
        "variables": ["FAL_KEY"],
        "nota": idiomas.N_("Sin ella las finales salen sin voz ni música."),
        "pasos": [
            idiomas.N_("Regístrate en fal.ai (con Google o GitHub; no pide verificación de negocio)."),
            idiomas.N_("En «Billing» agrega una tarjeta o saldo prepago."),
            idiomas.N_("Ve a «Keys» › «Add key», elige alcance «API» y copia la llave."),
            idiomas.N_("Pégala como FAL_KEY en el .env del servidor y reinicia."),
        ],
    },
    {
        "id": "higgsfield",
        "nombre": idiomas.N_("Higgsfield (video e imagen)"),
        "para_que": idiomas.N_("Genera la imagen candidata y el video de cada pieza."),
        "costo": idiomas.N_("Por créditos: ~1.5 por imagen y ~8 por video; se compran por paquetes."),
        "url": "https://higgsfield.ai/",
        "url_texto": "higgsfield.ai › API",
        "variables": ["HF_API_KEY_ID", "HF_API_KEY_SECRET"],
        "nota": idiomas.N_("Solo la usa el flujo viejo «Nueva idea»; Crear no la necesita."),
        "opcional": True,
        "pasos": [
            idiomas.N_("Inicia sesión en higgsfield.ai y compra un paquete de créditos en «Billing»."),
            idiomas.N_("Abre la sección «API» (o «Developers») de tu cuenta y crea una llave nueva."),
            idiomas.N_("Copia los dos valores: el Key ID y el Key Secret (el secreto solo se muestra una vez)."),
            idiomas.N_("Pégalos como HF_API_KEY_ID y HF_API_KEY_SECRET en el .env del servidor y reinicia."),
        ],
    },
    {
        "id": "r2",
        "nombre": idiomas.N_("Cloudflare R2 (almacenamiento)"),
        "para_que": idiomas.N_("Guarda cada imagen y video generado y les da una URL pública permanente."),
        "costo": idiomas.N_("Casi gratis: 10 GB al mes sin costo y sin cobro por descarga."),
        "url": "https://dash.cloudflare.com/?to=/:account/r2",
        "url_texto": "dash.cloudflare.com › R2 › Manage API tokens",
        "variables": ["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME", "R2_PUBLIC_BASE_URL"],
        "nota": idiomas.N_("Sin ella los videos no tienen URL pública y Meta no puede usarlos."),
        "pasos": [
            idiomas.N_("En dash.cloudflare.com entra a «R2» y crea un bucket (ese nombre es R2_BUCKET_NAME)."),
            idiomas.N_("En «Settings» del bucket activa «Public access» (r2.dev o un dominio propio): esa URL es R2_PUBLIC_BASE_URL."),
            idiomas.N_("Vuelve a R2 › «Manage R2 API tokens» › «Create API token» con permiso «Object Read & Write»."),
            idiomas.N_("Copia el Access Key ID y el Secret Access Key; el Account ID está en la barra lateral de R2."),
            idiomas.N_("Pega las cinco variables en el .env del servidor y reinicia."),
        ],
    },
    {
        "id": "smtp",
        "nombre": idiomas.N_("Correo de la plataforma (cuentas y avisos)"),
        "para_que": idiomas.N_("Manda el enlace para confirmar el correo de cada cuenta y el de recuperar la contraseña; "
                    "también los avisos (propuestas pendientes, ganadores, rechazos de Meta, lanzamientos fallidos)."),
        "costo": idiomas.N_("Depende del proveedor de correo; con una cuenta normal no cuesta."),
        "url": "https://support.google.com/accounts/answer/185833",
        "url_texto": idiomas.N_("Google › Contraseñas de aplicación"),
        "variables": ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "SMTP_FROM", "PLATAFORMA_URL"],
        "nota": idiomas.N_("Sin esto nadie puede confirmar su correo ni recuperar la contraseña solo (el administrador "
                "tiene que marcar las cuentas a mano en el panel) y los avisos solo quedan en la bitácora."),
        "opcional": True,
        "pasos": [
            idiomas.N_("Elige la cuenta que va a enviar (Gmail, Outlook o el correo del dominio)."),
            idiomas.N_("Si es Gmail: en myaccount.google.com › Seguridad activa la «Verificación en dos pasos» y luego, "
            "en «Contraseñas de aplicación», crea una para «Creatv»: los 16 caracteres que te da son SMTP_PASS "
            "(no la contraseña normal de la cuenta). SMTP_USER es la dirección completa y SMTP_FROM la misma."),
            idiomas.N_("Anota el servidor y el puerto (Gmail: smtp.gmail.com y 587, STARTTLS)."),
            idiomas.N_("Pega SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS y SMTP_FROM en el .env del servidor, junto con "
            "PLATAFORMA_URL (la dirección pública del sitio, p. ej. https://app.creatvmachine.com: es la base de "
            "los enlaces que van en los correos), y reinicia los dos servicios."),
            idiomas.N_("Prueba con «Reenviar» en Configuración › Cuenta: debe llegar el correo de confirmación. "
            "Abajo, en «Correo de avisos», escribe a qué dirección llegan los avisos de este proyecto."),
        ],
    },
    {
        "id": "meli",
        "nombre": idiomas.N_("MercadoLibre (opcional)"),
        "para_que": idiomas.N_("Trae las publicaciones activas de una tienda de MercadoLibre al catálogo."),
        "costo": idiomas.N_("Gratis: solo lectura de tus publicaciones."),
        "url": "https://developers.mercadolibre.com/",
        "url_texto": "developers.mercadolibre.com",
        "variables": ["MELI_APP_ID", "MELI_SECRET"],
        "nota": idiomas.N_("Sin esto no aparece el botón «Conectar con MercadoLibre» en Tienda."),
        "opcional": True,
        "pasos": [
            idiomas.N_("En developers.mercadolibre.com entra con la cuenta de la tienda y ve a «Mis aplicaciones» › «Crear nueva aplicación»."),
            idiomas.N_("Marca los permisos de lectura y «offline_access» (para renovar el token solo)."),
            idiomas.N_("En «URI de redirect» pon exactamente {callback_meli}."),
            idiomas.N_("Copia el App ID y la Secret Key y pégalos como MELI_APP_ID y MELI_SECRET en el .env del servidor; reinicia."),
            idiomas.N_("Luego, en «Conectar tu tienda» › MercadoLibre, pulsa «Conectar con MercadoLibre»."),
        ],
    },
    {
        "id": "reddit",
        "nombre": idiomas.N_("Reddit (Nicho: comentarios reales)"),
        "para_que": idiomas.N_("Trae posts y comentarios de Reddit a un estudio de Nicho para armar avatares con evidencia."),
        "costo": idiomas.N_("Gratis para uso propio (100 llamadas por minuto). Si el producto se vende, Reddit pide permiso comercial."),
        "url": "https://www.reddit.com/prefs/apps",
        "url_texto": "reddit.com › preferences › apps",
        "variables": ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"],
        "nota": idiomas.N_("Sin ellas la tarjeta Reddit de cada estudio queda apagada; el resto de Nicho funciona."),
        "opcional": True,
        "pasos": [
            idiomas.N_("Entra a reddit.com/prefs/apps con la cuenta de la empresa y pulsa «create another app…»."),
            idiomas.N_("Tipo «script», nombre «creatv-machine», redirect uri http://localhost:8080 (no se usa) y crea la app."),
            idiomas.N_("Copia el id (bajo el nombre de la app) como REDDIT_CLIENT_ID y el «secret» como REDDIT_CLIENT_SECRET."),
            idiomas.N_("Pon REDDIT_USER_AGENT con la forma «creatv-machine/1.0 (by u/tu_usuario)» y reinicia los dos servicios."),
        ],
    },
    {
        "id": "youtube_api",
        "nombre": idiomas.N_("YouTube Data API (Nicho: comentarios de videos)"),
        "para_que": idiomas.N_("Busca videos por palabras clave y trae sus comentarios a un estudio de Nicho. Es una llave distinta del OAuth de publicación."),
        "costo": idiomas.N_("Gratis: 100 búsquedas por día por proyecto de Google y 10 000 unidades para leer comentarios."),
        "url": "https://console.cloud.google.com/apis/credentials",
        "url_texto": idiomas.N_("console.cloud.google.com › APIs y servicios › Credenciales"),
        "variables": ["YOUTUBE_API_KEY"],
        "nota": idiomas.N_("Sin ella la tarjeta YouTube de cada estudio queda apagada."),
        "opcional": True,
        "pasos": [
            idiomas.N_("En el proyecto de Google Cloud donde ya está habilitada «YouTube Data API v3» (SETUP.md §2), ve a «Credenciales»."),
            idiomas.N_("«Crear credenciales» › «Clave de API»; en «Restricciones de API» limítala a YouTube Data API v3."),
            idiomas.N_("Cópiala como YOUTUBE_API_KEY en el .env del servidor y reinicia los dos servicios."),
        ],
    },
    {
        "id": "apify",
        "nombre": idiomas.N_("Apify (Nicho: reseñas/comentarios · Referentes: Ad Library)"),
        "para_que": idiomas.N_("Corre los actores de Apify: en Nicho trae reseñas de Amazon o comentarios de TikTok; en la biblioteca de referentes trae anuncios de la Ad Library de Meta (alternativa a Atria, sí cubre Latinoamérica)."),
        "costo": idiomas.N_("Se paga por resultado (Amazon ≈ US$ 3 por 1 000 reseñas; TikTok ≈ US$ 0,50 por 1 000 comentarios) más cómputo; el estimado se muestra antes de cada clic."),
        "url": "https://console.apify.com/account/integrations",
        "url_texto": "console.apify.com › Settings › Integrations",
        "variables": ["APIFY_TOKEN"],
        "nota": idiomas.N_("Sin él la tarjeta Amazon / TikTok de cada estudio queda apagada. Zona gris de términos de uso de esas plataformas: es responsabilidad de quien pone el token."),
        "opcional": True,
        "pasos": [
            idiomas.N_("Crea la cuenta en apify.com (trae crédito gratis mensual) y agrega una tarjeta si vas a pasar de ese crédito."),
            idiomas.N_("En «Settings» › «Integrations» copia el «Personal API token»."),
            idiomas.N_("Pégalo como APIFY_TOKEN en el .env del servidor y reinicia los dos servicios."),
        ],
    },
    {
        "id": "atria",
        "nombre": idiomas.N_("Atria (biblioteca de referentes: Ad Library de Meta)"),
        "para_que": idiomas.N_("Trae anuncios reales de la Ad Library de Meta para la biblioteca de referentes -- la fuente cubre la Unión Europea."),
        "costo": idiomas.N_("Incluido en el plan mensual de Atria (1 200 llamadas/mes); no cobra por resultado. El contador de uso está en Referentes (admin)."),
        "url": "https://tryatria.com",
        "url_texto": "tryatria.com",
        "variables": ["ATRIA_API_KEY"],
        "nota": idiomas.N_("Sin ella la fuente Atria queda apagada en «Traer referentes» (por proyecto y en el panel admin); Apify sigue disponible si tiene su propio token."),
        "opcional": True,
        "pasos": [
            idiomas.N_("Crea la cuenta en tryatria.com y elige un plan."),
            idiomas.N_("Copia la API key desde el panel de Atria."),
            idiomas.N_("Pégala como ATRIA_API_KEY en el .env del servidor y reinicia los dos servicios."),
        ],
    },
    {
        "id": "trendtrack",
        "nombre": idiomas.N_("TrendTrack (biblioteca de referentes: anuncios de Meta)"),
        "para_que": idiomas.N_("Trae anuncios reales de Meta que TrendTrack ha registrado para la biblioteca de referentes; busca por palabra clave."),
        "costo": idiomas.N_("Un crédito de TrendTrack por anuncio revisado (US$ 1 = 1 000 créditos); el plan Pro incluye 20 000 créditos al mes. El uso está en Referentes (admin)."),
        "url": "https://www.trendtrack.io",
        "url_texto": "trendtrack.io",
        "variables": ["TRENDTRACK_API_KEY"],
        "nota": idiomas.N_("Sin ella la fuente TrendTrack queda apagada en «Traer referentes». La API pide el plan Pro o superior: el Starter no la incluye."),
        "opcional": True,
        "pasos": [
            idiomas.N_("En trendtrack.io elige el plan Pro o superior (incluye la API y 20 000 créditos al mes)."),
            idiomas.N_("Crea una API key en tu workspace de TrendTrack (guía: docs.trendtrack.io › Getting Started)."),
            idiomas.N_("Pégala como TRENDTRACK_API_KEY en el .env del servidor y reinicia los dos servicios."),
        ],
    },
)


def estado(callback_meli=None):
    """Tarjetas de Configuración › Puesta a punto (solo admin). Devuelve una
    lista de dicts {id, nombre, para_que, costo, estado, url, url_texto,
    variables, faltan, nota, pasos, opcional} donde `estado` es «configurada»
    (todas las variables presentes), «falta» (ninguna) o «parcial» (algunas).
    Solo mira bool(os.environ.get(var)): ningún valor sale de aquí.
    `callback_meli` es la URL real del callback de MercadoLibre para el paso
    de la app (fuera de un request se deja el texto genérico). La conexión
    con Meta no es una llave del servidor: vive en Experimentos
    (_meta_conectar.html)."""
    callback = callback_meli or "<url del sitio>/meli/callback"
    tarjetas = []
    for s in SERVICIOS:
        nota, pasos = s["nota"], s["pasos"]
        presentes = [v for v in s["variables"] if bool((os.environ.get(v) or "").strip())]
        faltan = [v for v in s["variables"] if v not in presentes]
        if not faltan:
            estado = "configurada"
        elif not presentes:
            estado = "falta"
        else:
            estado = "parcial"
        # Ojo: gettext(s["nombre"]) confunde al extractor de Babel (agarra el
        # literal "nombre" del subíndice como si fuera el mensaje) — por eso
        # cada valor pasa primero por una variable antes de traducirse.
        nombre_valor, para_que_valor, costo_valor = s["nombre"], s["para_que"], s["costo"]
        url_texto_valor = s["url_texto"]
        tarjetas.append({
            "id": s["id"],
            "nombre": gettext(nombre_valor),
            "para_que": gettext(para_que_valor),
            "costo": gettext(costo_valor),
            "estado": estado,
            "url": s["url"],
            "url_texto": gettext(url_texto_valor),
            "variables": list(s["variables"]),
            "faltan": faltan,
            "nota": gettext(nota),
            "opcional": bool(s.get("opcional")),
            "pasos": [gettext(p).replace("{callback_meli}", callback) for p in pasos],
        })
    return tarjetas
