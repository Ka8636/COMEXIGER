from django.db.models import Sum
from django.db import IntegrityError
from django.shortcuts import render, redirect
from django.contrib import messages
from datetime import datetime
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Rendimiento, QRUsado
from .serializers import RendimientoSerializer

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from rest_framework import viewsets, status
from rest_framework.decorators import api_view, action, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


from Aplicaciones.Usuario.web_decorators import web_admin_required


def _mesa_sort_key(item):
    """
    Ordena mesas numéricas correctamente (2, 3, 10) y deja fallback para textos.
    """
    try:
        return (0, int(str(item.numero_mesa).strip()))
    except (TypeError, ValueError):
        return (1, str(item.numero_mesa).strip().lower())


# ================== VISTAS WEB ==================
@web_admin_required
def inicio(request):
    listadoRendimiento = Rendimiento.objects.filter(qr_id="JORNADA").order_by('-fecha_entrada')
    return render(request, 'rendimiento.html', {'rendimiento': listadoRendimiento})

@web_admin_required
def nuevo_rendimiento(request):
    return render(request, "nuevo_rendimiento.html")

@web_admin_required
@require_POST
def guardar_rendimiento(request):
    """
    Manual (web). Si no lo usas, puedes eliminar esta vista.
    """
    if request.method == "POST":
        try:
            numero_mesa = request.POST["numero_mesa"]
            fecha_entrada_str = request.POST.get("fecha_entrada")
            bonches = int(request.POST.get("bonches", 0))

            if fecha_entrada_str:
                try:
                    fecha_entrada_dt = datetime.strptime(fecha_entrada_str, "%Y-%m-%dT%H:%M")
                    fecha_entrada_dt = timezone.make_aware(
                        fecha_entrada_dt, timezone.get_current_timezone()
                    )
                except Exception:
                    fecha_entrada_dt = timezone.now()
            else:
                fecha_entrada_dt = timezone.now()

            nuevo = Rendimiento.objects.create(
                qr_id="MANUAL",
                numero_mesa=numero_mesa,
                fecha_entrada=fecha_entrada_dt,
                bonches=bonches
            )

            nuevo.recalcular()
            nuevo.save()

            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "rendimientos",
                {"type": "nuevo_rendimiento", "data": RendimientoSerializer(nuevo).data}
            )

            messages.success(request, "Rendimiento guardado exitosamente")
            return redirect('rendimiento')

        except Exception as e:
            messages.error(request, f"Error al guardar rendimiento: {e}")
            return redirect('nuevo_rendimiento')

    messages.error(request, "Error al guardar rendimiento")
    return redirect('nuevo_rendimiento')

@web_admin_required
def eliminar_rendimiento(request, id):
    try:
        rendimiento_eliminar = Rendimiento.objects.get(id=id)
        rendimiento_eliminar.delete()
        messages.success(request, "Rendimiento eliminado exitosamente")
    except Rendimiento.DoesNotExist:
        messages.error(request, "El rendimiento no existe.")
    return redirect('rendimiento')

@web_admin_required
@require_POST
def procesar_edicion_rendimiento(request):
    if request.method == "POST":
        try:
            rendimiento = Rendimiento.objects.get(id=request.POST["id"])

            numero_mesa = (request.POST.get("numero_mesa") or "").strip()
            bonches_raw = (request.POST.get("bonches") or "").strip()
            fecha_entrada_raw = (request.POST.get("fecha_entrada") or "").strip()
            hora_inicio_raw = (request.POST.get("hora_inicio") or "").strip()
            hora_final_raw = (request.POST.get("hora_final") or "").strip()

            if not numero_mesa.isdigit() or int(numero_mesa) < 1:
                raise ValueError("Numero de mesa invalido.")

            if not bonches_raw.isdigit() or int(bonches_raw) < 0:
                raise ValueError("Bonches invalido.")

            if not fecha_entrada_raw:
                raise ValueError("La fecha de entrada es obligatoria.")
            if not hora_inicio_raw:
                raise ValueError("La hora de inicio es obligatoria.")
            if not hora_final_raw:
                raise ValueError("La hora final es obligatoria.")

            try:
                fecha_entrada_dt = datetime.strptime(fecha_entrada_raw, "%Y-%m-%dT%H:%M")
                hora_inicio_dt = datetime.strptime(hora_inicio_raw, "%Y-%m-%dT%H:%M")
                hora_final_dt = datetime.strptime(hora_final_raw, "%Y-%m-%dT%H:%M")
            except Exception:
                raise ValueError("Formato de fecha u hora invalido.")

            fecha_entrada_aware = timezone.make_aware(fecha_entrada_dt, timezone.get_current_timezone())
            hora_inicio_aware = timezone.make_aware(hora_inicio_dt, timezone.get_current_timezone())
            hora_final_aware = timezone.make_aware(hora_final_dt, timezone.get_current_timezone())

            if hora_final_aware < hora_inicio_aware:
                raise ValueError("La hora final no puede ser menor que la hora de inicio.")

            # Campo rendimiento NO editable desde esta vista.
            rendimiento.numero_mesa = numero_mesa
            rendimiento.bonches = int(bonches_raw)
            rendimiento.fecha_entrada = fecha_entrada_aware
            rendimiento.hora_inicio = hora_inicio_aware
            rendimiento.hora_final = hora_final_aware

            rendimiento.recalcular()
            rendimiento.save()

            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "rendimientos",
                {"type": "nuevo_rendimiento", "data": RendimientoSerializer(rendimiento).data}
            )

            messages.success(request, "Rendimiento actualizado correctamente")

        except Exception as e:
            messages.error(request, f"Error al procesar la edición: {e}")

        return redirect('rendimiento')


# ================== API REST ==================

class RendimientoViewSet(viewsets.ModelViewSet):
    queryset = Rendimiento.objects.all().order_by('-fecha_entrada')
    serializer_class = RendimientoSerializer

    @action(detail=False, methods=['get'])
    def activos(self, request):
        serializer = self.get_serializer(
            Rendimiento.objects.filter(qr_id="JORNADA", hora_final__isnull=True).order_by('-fecha_entrada'),
            many=True
        )
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def por_mesa(self, request):
        mesa = request.query_params.get('mesa')
        if not mesa:
            return Response({"error": "Parámetro 'mesa' requerido"}, status=400)

        serializer = self.get_serializer(
            Rendimiento.objects.filter(qr_id="JORNADA", numero_mesa=mesa).order_by('-fecha_entrada'),
            many=True
        )
        return Response(serializer.data)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_rendimiento_list(request):
    # ---------- GET ----------
    if request.method == 'GET':
        rendimientos = Rendimiento.objects.filter(qr_id="JORNADA")

        if request.query_params.get("fecha"):
            rendimientos = rendimientos.filter(
                fecha_entrada__date=request.query_params["fecha"]
            )

        if request.query_params.get("desde") and request.query_params.get("hasta"):
            rendimientos = rendimientos.filter(
                fecha_entrada__date__range=[
                    request.query_params["desde"],
                    request.query_params["hasta"]
                ]
            )
        elif request.query_params.get("desde"):
            rendimientos = rendimientos.filter(
                fecha_entrada__date__gte=request.query_params["desde"]
            )
        elif request.query_params.get("hasta"):
            rendimientos = rendimientos.filter(
                fecha_entrada__date__lte=request.query_params["hasta"]
            )

        ordenar = request.query_params.get("ordenar")
        reciente = request.query_params.get("reciente")

        if ordenar:
            if ordenar == "mesa":
                data = list(rendimientos)
                data.sort(key=_mesa_sort_key, reverse=(reciente == "true"))
                serializer = RendimientoSerializer(data, many=True)
                return Response(serializer.data)

            campo = {"fecha": "fecha_entrada"}.get(ordenar)
            if campo:
                if reciente == "true":
                    campo = f"-{campo}"
                rendimientos = rendimientos.order_by(campo)

        serializer = RendimientoSerializer(rendimientos, many=True)
        return Response(serializer.data)

    # ---------- POST (QR) ----------
    data = request.data
    codigo = data.get("qr_id")
    mesa = data.get("numero_mesa")

    if not codigo or not mesa:
        return Response({"error": "Datos incompletos"}, status=status.HTTP_400_BAD_REQUEST)

    hoy = timezone.localdate()

    jornada_base = (Rendimiento.objects
        .filter(qr_id="JORNADA", numero_mesa=mesa, hora_final__isnull=True)
        .order_by("-hora_inicio", "-fecha_entrada")
        .first()
    )


    if not jornada_base:
        return Response(
            {"error": "No hay jornada iniciada para esta mesa hoy. Primero inicia jornada."},
            status=status.HTTP_409_CONFLICT
        )

    if QRUsado.objects.filter(qr_id=codigo).exists():
        return Response({"error": "Este QR ya fue utilizado"}, status=status.HTTP_409_CONFLICT)

    try:
        QRUsado.objects.create(qr_id=codigo)
    except IntegrityError:
        # Evita 500 por escaneo concurrente del mismo QR
        return Response({"error": "Este QR ya fue utilizado"}, status=status.HTTP_409_CONFLICT)

    jornada_base.bonches += 1
    jornada_base.recalcular()
    jornada_base.save()

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "rendimientos",
        {"type": "nuevo_rendimiento", "data": RendimientoSerializer(jornada_base).data}
    )

    return Response(RendimientoSerializer(jornada_base).data, status=200)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def api_rendimiento_detail(request, pk):
    try:
        rendimiento = Rendimiento.objects.get(pk=pk)
    except Rendimiento.DoesNotExist:
        return Response(status=404)

    if request.method == 'GET':
        return Response(RendimientoSerializer(rendimiento).data)

    if request.method == 'PUT':
        serializer = RendimientoSerializer(rendimiento, data=request.data, partial=True)
        if serializer.is_valid():
            obj = serializer.save()   
            obj.recalcular()          
            obj.save()                

            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "rendimientos",
                {"type": "nuevo_rendimiento", "data": RendimientoSerializer(obj).data}
            )

            return Response(RendimientoSerializer(obj).data)

        return Response(serializer.errors, status=400)

    if request.method == 'DELETE':
        rendimiento.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_rendimiento_stats(request):
    jornadas = Rendimiento.objects.filter(qr_id="JORNADA")
    return Response({
        'total_rendimientos': jornadas.count(),
        'rendimientos_activos': jornadas.filter(hora_final__isnull=True).count(),
        'total_bonches': jornadas.aggregate(Sum('bonches'))['bonches__sum'] or 0,
        'mesas_activas': jornadas.filter(hora_final__isnull=True).values('numero_mesa').distinct().count()
    })
