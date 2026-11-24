"""Orquestación del proceso: PDF editables → Excel de Emisión + reporte."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from .classifier import PerfilDocumento, clasificar_pdf
from .completitud import ResultadoCompletitud, evaluar_completitud
from .errors import error_excepcion, error_extraccion
from .excel_asesor import cruzar_con_seleccion, leer_titulares
from .excel_builder import generar_excel
from .labels import etiqueta_tipo_documento, etiquetas_campos
from .libs import config_manager, log_manager
from .models import ErrorProceso, SolicitudSalud
from .normalizer import extraer_pdf
from .periodo import (
    AvisoCarpetaMes,
    Periodo,
    listar_asesores,
    nombre_excel_emision,
    nombre_reporte,
    periodo_desde_flags,
    resolver_periodo,
)
from .report_builder import generar_reporte
from .selector import seleccionar_lote
from .settings import (
    DOCUMENTOS_DIR,
    EJEMPLOS_DIR,
    EXCEL_ASESORES_DIR,
    REPO_EDITABLES_DIR,
    SOLICITUDES_DIR,
    cargar_parametria,
)


def _find_pdfs(input_dir: Path, recursive: bool) -> list[Path]:
    pattern = "**/*.pdf" if recursive else "*.pdf"
    return sorted(input_dir.glob(pattern))


def _default_repo_root() -> Path:
    configured = config_manager.config.get("INPUTS")
    if configured:
        p = Path(configured)
        if p.is_dir():
            return p
    if REPO_EDITABLES_DIR.is_dir():
        return REPO_EDITABLES_DIR
    return SOLICITUDES_DIR if SOLICITUDES_DIR.is_dir() else DOCUMENTOS_DIR


def _default_input_dir() -> Path:
    """Fallback legacy: una sola carpeta de mes (documentos/solicitudes)."""
    configured = config_manager.config.get("INPUTS")
    if configured:
        p = Path(configured)
        if p.is_dir() and (any(p.glob("*.pdf")) or any(p.glob("**/*.pdf"))):
            if p.resolve() == SOLICITUDES_DIR.resolve() or p.name.lower() in (
                "solicitudes",
                "solicitudes escaneadas",
            ):
                meses = sorted([d for d in p.iterdir() if d.is_dir()], reverse=True)
                for m in meses:
                    if any(m.glob("*.pdf")):
                        return m
            return p
    if SOLICITUDES_DIR.is_dir():
        meses = sorted([d for d in SOLICITUDES_DIR.iterdir() if d.is_dir()], reverse=True)
        for m in meses:
            if any(m.glob("*.pdf")):
                return m
        return SOLICITUDES_DIR
    if EJEMPLOS_DIR.is_dir() and any(EJEMPLOS_DIR.glob("*.pdf")):
        return EJEMPLOS_DIR
    return DOCUMENTOS_DIR


def _default_excel_asesor() -> Path | None:
    base = EXCEL_ASESORES_DIR if EXCEL_ASESORES_DIR.is_dir() else DOCUMENTOS_DIR
    candidatos = sorted(base.glob("VENTAS SALUD ASESORES*.xlsx"))
    if not candidatos:
        return None
    # Opcional: EXCEL_ASESOR_PREFERIDO=<texto> elige el primer Excel cuyo nombre lo contenga.
    preferido = (os.environ.get("EXCEL_ASESOR_PREFERIDO") or "").strip().upper()
    if preferido:
        for c in candidatos:
            if preferido in c.name.upper():
                return c
    return candidatos[0]


def _es_repo_editables(path: Path) -> bool:
    """True si la ruta es la raíz multi-asesor (tiene SOLICITUDES ESCANEADAS dentro)."""
    if not path.is_dir():
        return False
    return bool(listar_asesores(path))


def procesar_lote(
    pdfs: list[Path],
    perfiles: list[PerfilDocumento | None] | None = None,
    parametria=None,
    *,
    asesor_origen: str = "",
    ruta_origen: str = "",
) -> tuple[list[SolicitudSalud], list[tuple[SolicitudSalud, ResultadoCompletitud]], list[ErrorProceso]]:
    completas: list[SolicitudSalud] = []
    incompletas: list[tuple[SolicitudSalud, ResultadoCompletitud]] = []
    errores: list[ErrorProceso] = []

    for i, pdf in enumerate(pdfs):
        perfil = (perfiles[i] if perfiles else None) or clasificar_pdf(pdf)
        try:
            solicitud = extraer_pdf(pdf)
            if solicitud is None:
                errores.append(error_extraccion(pdf.name, perfil))
                log_manager.info("  E1  %s  [%s]", pdf.name, perfil.tipo)
                continue

            solicitud.tipo_documento = perfil.tipo
            solicitud.tipo_documento_legible = etiqueta_tipo_documento(perfil.tipo)
            solicitud.asesor_origen = asesor_origen
            solicitud.ruta_origen = ruta_origen

            resultado = evaluar_completitud(solicitud, parametria)
            mod = (
                "A"
                if solicitud.modulo == 1
                else "B"
                if solicitud.modulo == 2
                else solicitud.modulo
            )
            if resultado.completa:
                completas.append(solicitud)
                log_manager.info(
                    "  OK  %s  — plan %s mod %s — %s",
                    pdf.name,
                    solicitud.plan,
                    mod,
                    solicitud.apellido_nombre_tomador or "(sin tomador)",
                )
            else:
                incompletas.append((solicitud, resultado))
                campos = ", ".join(etiquetas_campos(resultado.faltantes))
                log_manager.info("  Incompleta  %s  — %s", pdf.name, campos)
            log_manager.info_file(
                "%s %s [%s] plan=%s mod=%s faltantes=%s -> %s",
                "OK" if resultado.completa else "INCOMPLETA",
                pdf.name,
                perfil.tipo,
                solicitud.plan,
                solicitud.modulo,
                resultado.faltantes,
                solicitud.apellido_nombre_tomador,
            )
        except Exception as exc:
            errores.append(error_excepcion(pdf.name, perfil, exc))
            log_manager.info("  E1  %s  — %s", pdf.name, exc)

    return completas, incompletas, errores


def _recoger_resultados_carpeta(
    pdfs: list[Path],
    input_dir: Path,
    *,
    sin_filtro: bool,
    excel_asesor: Path | None,
    usar_excel_asesor: bool,
    parametria,
    asesor_origen: str = "",
    ruta_origen: str = "",
) -> dict:
    """Filtra y extrae una carpeta; no escribe Excel ni reporte."""
    ignorados = []
    revisar = []
    a_procesar = pdfs
    perfiles: list[PerfilDocumento | None] | None = None
    selecciones_procesar = []

    if not sin_filtro:
        sel = seleccionar_lote(pdfs)
        a_procesar = [s.path for s in sel["procesar"]]
        perfiles = [s.perfil for s in sel["procesar"]]
        selecciones_procesar = sel["procesar"]
        ignorados = sel["ignorar"]
        revisar = sel["revisar"]
        log_manager.info(
            "  PDFs: %s | a procesar: %s | ignorar: %s | revisar: %s",
            len(pdfs),
            len(a_procesar),
            len(ignorados),
            len(revisar),
        )
        for s in ignorados:
            log_manager.info("  Ignorado  %s  — %s", s.path.name, s.motivo)
        for s in revisar:
            log_manager.info("  Revisar   %s  — %s", s.path.name, s.motivo)

    cruce = None
    if usar_excel_asesor:
        excel_path = excel_asesor or _default_excel_asesor()
        if excel_path and excel_path.exists() and selecciones_procesar:
            try:
                hoja, titulares = leer_titulares(excel_path, mes_hint=input_dir.name)
                cruce = cruzar_con_seleccion(titulares, selecciones_procesar)
                log_manager.info_file(
                    "Cruce Excel asesor (%s): %s titulares | cubiertos≈%s | faltantes≈%s",
                    hoja,
                    len(titulares),
                    len(cruce["cubiertos"]),
                    len(cruce["faltantes"]),
                )
            except Exception as exc:
                log_manager.warning("  No se pudo cruzar con Excel asesor: %s", exc)

    completas: list[SolicitudSalud] = []
    incompletas: list[tuple[SolicitudSalud, ResultadoCompletitud]] = []
    errores: list[ErrorProceso] = []
    if a_procesar:
        completas, incompletas, errores = procesar_lote(
            a_procesar,
            perfiles,
            parametria=parametria,
            asesor_origen=asesor_origen,
            ruta_origen=ruta_origen,
        )
    else:
        log_manager.warning("  No hay solicitudes para procesar tras el filtro")

    return {
        "completas": completas,
        "incompletas": incompletas,
        "errores": errores,
        "ignorados": ignorados,
        "revisar": revisar,
        "cruce": cruce,
    }


def _procesar_carpeta_mes(
    input_dir: Path,
    output_excel: Path,
    output_reporte: Path,
    *,
    recursive: bool,
    excel_asesor: Path | None,
    sin_filtro: bool,
    usar_excel_asesor: bool,
    parametria,
    avisos_carpetas: list[AvisoCarpetaMes] | None = None,
) -> int:
    """Modo diagnóstico: una carpeta → un Excel/reporte."""
    pdfs = _find_pdfs(input_dir, recursive)
    if not pdfs:
        log_manager.warning("  Sin PDFs en: %s", log_manager.short_path(input_dir))
        return 1

    log_manager.info_file("Encontrados %s PDF(s) en %s", len(pdfs), input_dir)
    data = _recoger_resultados_carpeta(
        pdfs,
        input_dir,
        sin_filtro=sin_filtro,
        excel_asesor=excel_asesor,
        usar_excel_asesor=usar_excel_asesor,
        parametria=parametria,
        ruta_origen=str(input_dir),
    )
    completas = data["completas"]
    incompletas = data["incompletas"]
    errores = data["errores"]
    ignorados = data["ignorados"]
    revisar = data["revisar"]
    cruce = data["cruce"]

    if not completas and not incompletas and not errores and not ignorados and not revisar:
        generar_reporte(
            [],
            [],
            output_path=output_reporte,
            incompletas=[],
            ignorados=ignorados,
            revisar=revisar,
            cruce=cruce,
            emision_path=None,
            parametria=parametria,
            avisos_carpetas=avisos_carpetas,
        )
        log_manager.info("  Reporte: %s", log_manager.short_path(output_reporte))
        return 1

    excel_path = None
    if completas or incompletas:
        excel_path = generar_excel(
            completas,
            parametria,
            incompletas=incompletas,
            output_path=output_excel,
        )
        log_manager.info(
            "  Excel emisión: %s (%s completa/s | %s incompleta/s)",
            log_manager.short_path(excel_path),
            len(completas),
            len(incompletas),
        )
    else:
        log_manager.warning("  Sin emisiones — no se generó Excel")

    reporte_path = generar_reporte(
        completas,
        errores,
        output_path=output_reporte,
        incompletas=incompletas,
        ignorados=ignorados,
        revisar=revisar,
        cruce=cruce,
        emision_path=excel_path,
        parametria=parametria,
        avisos_carpetas=avisos_carpetas,
    )
    log_manager.info(
        "  Totales: %s OK | %s incompleta/s | %s excluido/s | %s ignorado/s | %s revisar",
        len(completas),
        len(incompletas),
        len(errores),
        len(ignorados),
        len(revisar),
    )
    log_manager.info("  Reporte: %s", log_manager.short_path(reporte_path))
    return 0 if (completas or incompletas) else 1


def process_repo(
    repo_root: Path,
    periodo: Periodo,
    *,
    recursive: bool = True,
    excel_asesor: Path | None = None,
    sin_filtro: bool = False,
    usar_excel_asesor: bool = False,
    output_dir: Path | None = None,
) -> int:
    """
    Procesa el período en todos los asesores.
    Un Excel y un reporte en output_dir (default settings.OUTPUT_DIR).
    """
    from collections import defaultdict

    from .lote import separar_duplicados_ambiguos, tomar_snapshot
    from .settings import OUTPUT_DIR

    del recursive  # el snapshot ya lista **/*.pdf
    parametria = cargar_parametria()
    asesores = listar_asesores(repo_root)
    if not asesores:
        log_manager.error("No se encontraron carpetas de asesor en: %s", repo_root)
        return 1

    dest = Path(output_dir) if output_dir else OUTPUT_DIR
    dest.mkdir(parents=True, exist_ok=True)
    lote = tomar_snapshot(repo_root, periodo)

    log_manager.info("")
    log_manager.info("Emisión Plan Familia VAVI — %s", periodo.etiqueta)
    log_manager.info("Repo: %s | asesores: %s | PDFs snapshot: %s", log_manager.short_path(repo_root), len(asesores), len(lote.items))
    log_manager.info("Salida: %s", log_manager.short_path(dest))
    log_manager.info("")

    for aviso in lote.avisos:
        log_manager.warning(
            "  Carpeta mal nombrada: %s — %s",
            aviso.nombre_carpeta,
            aviso.motivo,
        )

    grupos: dict[tuple[str, Path], list] = defaultdict(list)
    for item in lote.items:
        grupos[(item.asesor, item.mes_dir)].append(item)

    asesores_con_mes = {nombre for nombre, _ in grupos}
    sin_carpeta_nombres = [a.name for a in asesores if a.name not in asesores_con_mes]

    completas: list[SolicitudSalud] = []
    incompletas: list[tuple[SolicitudSalud, ResultadoCompletitud]] = []
    errores: list[ErrorProceso] = []
    ignorados = []
    revisar = []

    for (asesor_nombre, mes_dir), items in sorted(grupos.items(), key=lambda x: x[0][0]):
        pdfs = [i.pdf for i in items]
        log_manager.info("▸ %s  (%s)", asesor_nombre, mes_dir.name)
        log_manager.info_file("Encontrados %s PDF(s) en %s", len(pdfs), mes_dir)
        data = _recoger_resultados_carpeta(
            pdfs,
            mes_dir,
            sin_filtro=sin_filtro,
            excel_asesor=excel_asesor,
            usar_excel_asesor=usar_excel_asesor,
            parametria=parametria,
            asesor_origen=asesor_nombre,
            ruta_origen=str(mes_dir),
        )
        completas.extend(data["completas"])
        incompletas.extend(data["incompletas"])
        errores.extend(data["errores"])
        ignorados.extend(data["ignorados"])
        revisar.extend(data["revisar"])
        log_manager.info("")

    todas = list(completas) + [s for s, _ in incompletas]
    emitibles, ambiguos = separar_duplicados_ambiguos(todas, periodo.slug)
    ids_ok = {(s.asesor_origen, s.archivo_origen) for s in emitibles}
    completas = [s for s in completas if (s.asesor_origen, s.archivo_origen) in ids_ok]
    incompletas = [
        (s, r) for s, r in incompletas if (s.asesor_origen, s.archivo_origen) in ids_ok
    ]
    if ambiguos:
        log_manager.warning(
            "Duplicados ambiguos: %s grupo/s (hoja Duplicados)",
            len(ambiguos),
        )

    if sin_carpeta_nombres:
        log_manager.info(
            "Sin carpeta %s: %s",
            periodo.slug,
            ", ".join(sin_carpeta_nombres),
        )

    duplicados = [s for grupo in ambiguos for s in grupo]
    excel_path = None
    if completas or incompletas or duplicados:
        excel_path = generar_excel(
            completas,
            parametria,
            incompletas=incompletas,
            duplicados=duplicados,
            output_path=dest / nombre_excel_emision(periodo),
        )
        log_manager.info(
            "Excel emisión: %s (%s completa/s | %s incompleta/s | %s duplicado/s)",
            log_manager.short_path(excel_path),
            len(completas),
            len(incompletas),
            len(duplicados),
        )
    else:
        log_manager.warning("Sin emisiones — no se generó Excel")

    reporte_path = generar_reporte(
        completas,
        errores,
        output_path=dest / nombre_reporte(periodo),
        incompletas=incompletas,
        ignorados=ignorados,
        revisar=revisar,
        emision_path=excel_path,
        parametria=parametria,
        avisos_carpetas=list(lote.avisos),
        duplicados_ambiguos=ambiguos,
    )
    log_manager.info(
        "Totales: %s OK | %s incompleta/s | %s excluido/s | %s ignorado/s | %s revisar | %s ambiguo/s",
        len(completas),
        len(incompletas),
        len(errores),
        len(ignorados),
        len(revisar),
        sum(len(g) for g in ambiguos),
    )
    log_manager.info("Reporte: %s", log_manager.short_path(reporte_path))
    log_manager.info(
        "Fin: %s asesor/es con mes | %s sin carpeta",
        len(grupos),
        len(sin_carpeta_nombres),
    )
    return 0 if (completas or incompletas or errores or ignorados or revisar or lote.items) else 1


def process(
    input_dir: Path | None = None,
    output_dir: Path | None = None,
    *,
    recursive: bool = False,
    excel_asesor: Path | None = None,
    sin_filtro: bool = False,
    usar_excel_asesor: bool = False,
    mes: int | None = None,
    anio: int | None = None,
    repo_root: Path | None = None,
) -> int:
    """
    Ejecuta el lote.
    - Sin --input: usa repo de solicitudes + --mes/--anio (o mes en curso por calendario).
    - Con --input a una carpeta de mes: modo legacy (1 carpeta → output_dir).
    Returns:
        0 si hay al menos una solicitud OK; 1 en caso contrario.
    """
    # Graph: sin --input / --repo. Dev local sigue con GRAPH_ENABLED=false.
    if input_dir is None and repo_root is None:
        from .graph_config import graph_enabled, cargar_graph_config
        from .graph_conector import process_via_graph

        if graph_enabled():
            dest = Path(output_dir) if output_dir else Path(config_manager.config["OUTPUTS"])
            dest.mkdir(parents=True, exist_ok=True)
            try:
                periodo = periodo_desde_flags(mes=mes, anio=anio)
            except ValueError as exc:
                log_manager.error("%s", exc)
                return 1
            cfg_graph = cargar_graph_config()
            if cfg_graph.publicar_todo_en_salida:
                destino_log = f"GRAPH_SALIDA={cfg_graph.salida or '(raíz)'} (emision + reporte)"
            else:
                destino_log = "raíz VAVI (emision) + GRAPH_SALIDA (reporte)"
            log_manager.info(
                "Modo Graph — %s → staging temporal → %s",
                periodo.etiqueta,
                destino_log,
            )
            return process_via_graph(periodo, output_dir=dest)

    # Modo repo (default): multi-asesor
    if input_dir is None:
        root = Path(repo_root).resolve() if repo_root else _default_repo_root()
        if repo_root is not None and not root.is_dir():
            log_manager.error("No existe el repo indicado (--repo): %s", root)
            return 1
        if _es_repo_editables(root):
            try:
                periodo = resolver_periodo(root, mes=mes, anio=anio)
            except ValueError as exc:
                log_manager.error("%s", exc)
                return 1
            return process_repo(
                root,
                periodo,
                recursive=True,
                excel_asesor=excel_asesor,
                sin_filtro=sin_filtro,
                usar_excel_asesor=usar_excel_asesor,
                output_dir=Path(output_dir) if output_dir else None,
            )
        if repo_root is not None:
            log_manager.error(
                "La ruta --repo no es un repo multi-asesor (falta 'SOLICITUDES ESCANEADAS' "
                "dentro de carpetas de asesor): %s",
                root,
            )
            return 1
        # INPUTS apunta a una sola carpeta legacy
        input_dir = _default_input_dir()

    input_dir = Path(input_dir)
    if _es_repo_editables(input_dir) and not any(input_dir.glob("*.pdf")):
        try:
            periodo = resolver_periodo(input_dir, mes=mes, anio=anio)
        except ValueError as exc:
            log_manager.error("%s", exc)
            return 1
        return process_repo(
            input_dir,
            periodo,
            recursive=True,
            excel_asesor=excel_asesor,
            sin_filtro=sin_filtro,
            usar_excel_asesor=usar_excel_asesor,
            output_dir=Path(output_dir) if output_dir else None,
        )

    output_dir = Path(output_dir) if output_dir else Path(config_manager.config["OUTPUTS"])
    if not input_dir.exists():
        log_manager.error("No existe la carpeta de entrada: %s", input_dir)
        return 1

    parametria = cargar_parametria()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_manager.info("")
    log_manager.info("Emisión Plan Familia VAVI — carpeta puntual")
    log_manager.info("Entrada: %s", log_manager.short_path(input_dir))
    log_manager.info("")
    return _procesar_carpeta_mes(
        input_dir,
        output_excel=output_dir / f"emision_plan_familia_{timestamp}.xlsx",
        output_reporte=output_dir / f"reporte_resultados_{timestamp}.xlsx",
        recursive=recursive,
        excel_asesor=excel_asesor,
        sin_filtro=sin_filtro,
        usar_excel_asesor=usar_excel_asesor,
        parametria=parametria,
    )
