import os
from django.conf import settings
from django.core.asgi import get_asgi_application
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "COMEXIGER.settings")

django_asgi_app = get_asgi_application()


import Aplicaciones.Rendimiento.routing
import Aplicaciones.Disponibilidad.routing


serve_static = os.getenv("SERVE_STATIC", "true").strip().lower() in {"1", "true", "yes", "on"}
if settings.DEBUG or serve_static:
    django_asgi_app = ASGIStaticFilesHandler(django_asgi_app)

application = ProtocolTypeRouter({
    "http": django_asgi_app,

    "websocket": AuthMiddlewareStack(
        URLRouter(
            Aplicaciones.Rendimiento.routing.websocket_urlpatterns
            + Aplicaciones.Disponibilidad.routing.websocket_urlpatterns
        )
    ),
})
