from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from Aplicaciones.Disponibilidad.models import Disponibilidad
from Aplicaciones.Usuario.web_decorators import web_admin_required
from .models import Mesa, Usuario

CARGOS_PERMITIDOS = {
    "ADMIN",
    "EMBONCHADOR/A",
    "CLASIFICADOR/A",
    "EMPADOR",
    "EMPACADOR",
    "CONTROL",
}

CARGOS_MESA_CERO = {"ADMIN", "EMPADOR", "EMPACADOR", "CONTROL"}


@ensure_csrf_cookie
def inicio(request):
    if request.method == "POST":
        username = (request.POST.get("usuario") or "").strip()
        password = (request.POST.get("contrasena") or "").strip()

        usuario = Usuario.objects.filter(username__iexact=username).first()

        if not usuario or not usuario.check_password(password):
            messages.error(request, "Credenciales incorrectas")
            return render(request, "iniciose.html")

        if (usuario.cargo or "").strip().upper() != "ADMIN":
            messages.error(request, "ACCESO DENEGADO.")
            return render(request, "iniciose.html")

        request.session["web_user_id"] = usuario.id
        request.session["web_username"] = usuario.username
        request.session.set_expiry(60 * 60 * 8)  # 8 horas

        messages.success(request, f"Bienvenido {usuario.nombres}")
        return redirect("dispo")

    return render(request, "iniciose.html")


def cerrarsesion(request):
    request.session.flush()
    messages.success(request, "Sesion cerrada correctamente.")
    return redirect("iniciose")


@web_admin_required
def dispo(request):
    disponibilidades = Disponibilidad.objects.all().order_by("-fecha_entrada")
    return render(
        request,
        "disponibilidad.html",
        {
            "disponibilidades": disponibilidades,
            "web_username": request.session.get("web_username"),
        },
    )


@web_admin_required
def inicios(request):
    listado_usuarios = Usuario.objects.all()
    mesas = Mesa.objects.all().order_by("nombre")
    return render(request, "usuariore.html", {"usuario": listado_usuarios, "mesas": mesas})


@web_admin_required
def nuevo_usuario(request):
    mesas = Mesa.objects.all().order_by("nombre")
    return render(request, "nuevo_usuario.html", {"mesas": mesas})


@web_admin_required
@require_POST
def guardar_mesa(request):
    nombre = (request.POST.get("nombre") or "").strip()
    is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"

    if not nombre:
        if is_ajax:
            return JsonResponse({"success": False, "message": "Ingrese el nombre de la mesa."}, status=400)
        messages.error(request, "Ingrese el nombre de la mesa.")
        return redirect("nuevo_usuario")

    if not nombre.isdigit() or int(nombre) <= 0:
        if is_ajax:
            return JsonResponse({"success": False, "message": "La mesa debe ser un numero mayor a 0."}, status=400)
        messages.error(request, "La mesa debe ser un numero mayor a 0.")
        return redirect("nuevo_usuario")

    if Mesa.objects.filter(nombre__iexact=nombre).exists():
        if is_ajax:
            return JsonResponse({"success": False, "message": "Esa mesa ya existe."}, status=409)
        messages.warning(request, "Esa mesa ya existe.")
        return redirect("nuevo_usuario")

    mesa = Mesa.objects.create(nombre=nombre)
    if is_ajax:
        return JsonResponse(
            {"success": True, "message": "Mesa agregada correctamente.", "mesa": {"id": mesa.id, "nombre": mesa.nombre}},
            status=201
        )
    messages.success(request, "Mesa agregada correctamente.")
    return redirect("nuevo_usuario")


@web_admin_required
@require_POST
def guardar_usuario(request):
    nombres = (request.POST.get("nombres") or "").strip()
    apellidos = (request.POST.get("apellidos") or "").strip()
    mesa = (request.POST.get("mesa") or "").strip()
    cargo = (request.POST.get("cargo") or "").strip().upper()
    username = (request.POST.get("username") or "").strip()
    password = (request.POST.get("password") or "").strip()

    if not nombres or not apellidos or not username or not password:
        messages.error(request, "Todos los campos son obligatorios.")
        return redirect("nuevo_usuario")

    if cargo not in CARGOS_PERMITIDOS:
        messages.error(request, "Cargo no permitido.")
        return redirect("nuevo_usuario")

    if Usuario.objects.filter(username__iexact=username).exists():
        messages.error(request, "Ese usuario ya existe.")
        return redirect("nuevo_usuario")

    if len(password) < 6:
        messages.error(request, "La contrasena debe tener al menos 6 caracteres.")
        return redirect("nuevo_usuario")

    if cargo in CARGOS_MESA_CERO:
        mesa = "0"
    else:
        if not mesa.isdigit() or int(mesa) <= 0:
            messages.error(request, "La mesa debe ser un numero mayor a 0.")
            return redirect("nuevo_usuario")
        if not Mesa.objects.filter(nombre=mesa).exists():
            messages.error(request, "La mesa seleccionada no existe.")
            return redirect("nuevo_usuario")

    u = Usuario(
        nombres=nombres,
        apellidos=apellidos,
        mesa=mesa,
        cargo=cargo,
        username=username,
    )
    u.set_password(password)
    u.save()

    messages.success(request, "Usuario guardado exitosamente.")
    return redirect("usuariore")


@web_admin_required
def eliminar_usuario(request, id):
    try:
        usuario_eliminar = Usuario.objects.get(id=id)
        usuario_eliminar.delete()
        messages.success(request, "Usuario eliminado exitosamente.")
    except Usuario.DoesNotExist:
        messages.error(request, "El usuario no existe.")
    return redirect("usuariore")


@web_admin_required
@require_POST
def procesar_edicion_usuario(request):
    try:
        user_id = request.POST["id"]
        usuario = Usuario.objects.get(id=user_id)

        usuario.nombres = (request.POST.get("nombres") or "").strip()
        usuario.apellidos = (request.POST.get("apellidos") or "").strip()
        usuario.mesa = (request.POST.get("mesa") or "").strip()
        usuario.cargo = (request.POST.get("cargo") or "").strip()

        nuevo_username = (request.POST.get("username") or "").strip()
        if not nuevo_username:
            messages.error(request, "El usuario (username) es obligatorio.")
            return redirect("usuariore")

        if Usuario.objects.filter(username__iexact=nuevo_username).exclude(id=usuario.id).exists():
            messages.error(request, "Ese usuario (username) ya esta registrado. Elige otro.")
            return redirect("usuariore")

        usuario.username = nuevo_username

        nueva_password = (request.POST.get("password") or "").strip()
        if nueva_password:
            usuario.set_password(nueva_password)

        usuario.save()
        messages.success(request, "Usuario actualizado correctamente")
    except Usuario.DoesNotExist:
        messages.error(request, "El usuario no existe.")
    except Exception as e:
        messages.error(request, f"Error al procesar la edicion: {e}")

    return redirect("usuariore")
