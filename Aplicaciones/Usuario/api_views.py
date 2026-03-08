# Aplicaciones/Usuario/api_views.py

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.hashers import make_password, check_password
import json

from .models import Usuario, Mesa
from .jwt_utils import crear_access_token, crear_refresh_token
from Aplicaciones.Usuario.jwt_decorators import jwt_required

CARGOS_PERMITIDOS = {
    "ADMIN",
    "EMBONCHADOR/A",
    "CLASIFICADOR/A",
    "EMPACADOR",
    "CONTROL",
}
CARGOS_MESA_CERO = {"ADMIN", "EMPADOR", "EMPACADOR", "CONTROL"}
MAX_ADMINISTRADORES = 2


@csrf_exempt
def registrar_usuario_api(request):
    """
    API para registro desde Flutter
    POST: /api/registrar/
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Método no permitido. Use POST"}, status=405)

    try:
        data = json.loads(request.body.decode("utf-8"))

        campos_requeridos = ["nombres", "apellidos", "mesa", "cargo", "username", "password"]
        faltantes = [c for c in campos_requeridos if not str(data.get(c, "")).strip()]
        if faltantes:
            return JsonResponse(
                {"success": False, "error": f"Campos requeridos faltantes: {', '.join(faltantes)}"},
                status=400
            )

        username = data["username"].strip()
        if Usuario.objects.filter(username__iexact=username).exists():
            return JsonResponse({"success": False, "error": f"El usuario '{username}' ya existe"}, status=400)

        cargo = (data.get("cargo") or "").strip().upper()
        if cargo not in CARGOS_PERMITIDOS:
            return JsonResponse({"success": False, "error": "Cargo no permitido"}, status=400)

        if cargo == "ADMIN" and Usuario.objects.filter(cargo__iexact="ADMIN").count() >= MAX_ADMINISTRADORES:
            return JsonResponse({"success": False, "error": "Solo se permiten hasta 2 administradores"}, status=400)

        mesa = (data.get("mesa") or "").strip()
        if cargo in CARGOS_MESA_CERO:
            mesa = "0"
        else:
            if not mesa.isdigit() or int(mesa) <= 0:
                return JsonResponse({"success": False, "error": "La mesa debe ser un numero mayor a 0"}, status=400)
            if not Mesa.objects.filter(nombre=mesa).exists():
                return JsonResponse({"success": False, "error": "La mesa seleccionada no existe"}, status=400)

        usuario = Usuario(
            nombres=data["nombres"].strip(),
            apellidos=data["apellidos"].strip(),
            mesa=mesa,
            cargo=cargo,
            username=username,
        )
        usuario.password = make_password(data["password"].strip())
        usuario.save()

        return JsonResponse({
            "success": True,
            "message": "Usuario registrado exitosamente",
            "data": {
                "id": usuario.id,
                "nombres": usuario.nombres,
                "apellidos": usuario.apellidos,
                "mesa": usuario.mesa,
                "cargo": usuario.cargo,
                "username": usuario.username
            }
        }, status=201)

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "JSON inválido en el cuerpo de la solicitud"}, status=400)
    except Exception as e:
        return JsonResponse({"success": False, "error": f"Error del servidor: {str(e)}"}, status=500)


@csrf_exempt
def login_usuario_api(request):
    """
    API para login (Flutter + listener)
    POST: /api/login/

    Devuelve:
      tokens: {access, refresh}
      data: info del usuario
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Método no permitido. Use POST"}, status=405)

    try:
        data = json.loads(request.body.decode("utf-8"))
        username = (data.get("username") or "").strip()
        password = (data.get("password") or "").strip()

        if not username or not password:
            return JsonResponse({"success": False, "error": "Usuario y contraseña son requeridos"}, status=400)


        usuario = Usuario.objects.filter(username__iexact=username).first()
        if not usuario:
            return JsonResponse({"success": False, "error": "Usuario no encontrado"}, status=404)

        if not check_password(password, usuario.password):
            return JsonResponse({"success": False, "error": "Credenciales incorrectas"}, status=401)

        payload_access = {
            "sub": str(usuario.id),
            "type": "access",
            "username": usuario.username,
            "cargo": usuario.cargo,
            "mesa": usuario.mesa,
        }

        payload_refresh = {
            "sub": str(usuario.id),
            "type": "refresh",
            "username": usuario.username,
        }

        access = crear_access_token(payload_access, minutes=60)   # 60 min
        refresh = crear_refresh_token(payload_refresh, days=7)    # 7 días

        return JsonResponse({
            "success": True,
            "message": "Login exitoso",
            "tokens": {"access": access, "refresh": refresh},
            "data": {
                "id": usuario.id,
                "nombres": usuario.nombres,
                "apellidos": usuario.apellidos,
                "mesa": usuario.mesa,
                "cargo": usuario.cargo,
                "username": usuario.username,
                "tipo": "usuario"
            }
        }, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "JSON inválido en el cuerpo de la solicitud"}, status=400)
    except Exception as e:
        return JsonResponse({"success": False, "error": f"Error del servidor: {str(e)}"}, status=500)


@csrf_exempt
@jwt_required
def obtener_mesas_api(request):
    """
    API para obtener todas las mesas registradas
    GET: /api/mesas/
    """
    if request.method != "GET":
        return JsonResponse({"success": False, "error": "Método no permitido. Use GET"}, status=405)

    try:
        mesas = Mesa.objects.all().order_by("nombre")
        mesas_list = [{"id": m.id, "nombre": m.nombre} for m in mesas]

        return JsonResponse({"success": True, "data": mesas_list, "count": len(mesas_list)}, status=200)

    except Exception as e:
        return JsonResponse({"success": False, "error": f"Error del servidor: {str(e)}"}, status=500)


@csrf_exempt
def verificar_mesa_api(request):
    """
    API para verificar si una mesa existe
    POST: /api/verificar_mesa/
    Body JSON: {"nombre": "Mesa 1"}
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Método no permitido. Use POST"}, status=405)

    try:
        data = json.loads(request.body.decode("utf-8"))
        nombre_mesa = (data.get("nombre") or "").strip()

        if not nombre_mesa:
            return JsonResponse({"success": False, "error": "El nombre de la mesa es requerido"}, status=400)

        existe = Mesa.objects.filter(nombre__iexact=nombre_mesa).exists()

        return JsonResponse({"success": True, "existe": existe, "nombre": nombre_mesa}, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "JSON inválido"}, status=400)
    except Exception as e:
        return JsonResponse({"success": False, "error": f"Error del servidor: {str(e)}"}, status=500)
