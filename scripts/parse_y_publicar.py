"""
Parsea el archivo exportado por SUBDERE en Línea (módulo "Presentación de
Proyectos") y genera docs/data/proyectos.json, que es el ÚNICO archivo que
cambia en cada actualización semanal. El index.html del dashboard no se
vuelve a tocar salvo que cambie el diseño.

Uso:
    python parse_y_publicar.py /ruta/al/Listado_Proyectos_YYYYMMDD_HHMMSS.xls
"""

import sys
import json
from pathlib import Path
from datetime import datetime

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DRIVE_UPLOAD_DIR = BASE_DIR / "para_subir_a_drive"
DRIVE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
RAW_BACKUP_DIR = BASE_DIR / "data_raw"
RAW_BACKUP_DIR.mkdir(parents=True, exist_ok=True)

COLUMN_MAP = {
    "Año Creación": "anio_creacion",
    "Región": "region",
    "ID Comuna INE": "id_comuna_ine",
    "Circunscripción": "circunscripcion",
    "Distrito": "distrito",
    "Comuna": "comuna",
    "Tipo de Acción": "tipo_accion",
    "Programa": "programa",
    "Plan": "subprograma",
    "Nombre Proyecto": "nombre_proyecto",
    "Aporte Subdere ($)": "monto_subdere",
    "Estado": "estado",
    "Días en estado": "dias_en_estado",
    "Tipo solicitud": "tipo_solicitud",
    "Id. Proyecto": "id_proyecto",
    "Fecha Aprobación": "fecha_aprobacion",
    "Revisión URS": "revision_urs",
    "Observación Programa": "observacion_programa",
    "Elegibilidad": "elegibilidad",
    "Clasif. Especial": "clasificacion_especial",
}

COMUNA_A_PROVINCIA = {
    "LA SERENA": "Elqui", "COQUIMBO": "Elqui", "ANDACOLLO": "Elqui",
    "LA HIGUERA": "Elqui", "PAIHUANO": "Elqui", "VICUÑA": "Elqui",
    "OVALLE": "Limarí", "COMBARBALÁ": "Limarí", "MONTE PATRIA": "Limarí",
    "PUNITAQUI": "Limarí", "RÍO HURTADO": "Limarí",
    "ILLAPEL": "Choapa", "CANELA": "Choapa", "LOS VILOS": "Choapa", "SALAMANCA": "Choapa",
}

FIELDS_TO_PUBLISH = [
    "id_proyecto", "nombre_proyecto", "comuna", "provincia", "region",
    "programa", "subprograma", "tipo_accion", "estado",
    "anio_creacion", "anio_aprobacion", "monto_subdere", "dias_en_estado",
]


def parse_file(path: Path) -> pd.DataFrame:
    tables = pd.read_html(path)
    data_table = max(tables, key=lambda t: t.shape[0])
    header = data_table.iloc[0].tolist()
    df = data_table.iloc[1:].copy()
    df.columns = header

    known_cols = [c for c in COLUMN_MAP if c in df.columns]
    df = df[known_cols].rename(columns=COLUMN_MAP)

    if "monto_subdere" in df:
        df["monto_subdere"] = df["monto_subdere"].astype(str).str.replace(r"[^\d\-]", "", regex=True)
        df["monto_subdere"] = pd.to_numeric(df["monto_subdere"], errors="coerce").fillna(0)

    if "fecha_aprobacion" in df:
        df["fecha_aprobacion"] = pd.to_datetime(df["fecha_aprobacion"], format="%d/%m/%Y", errors="coerce")
        df["anio_aprobacion"] = df["fecha_aprobacion"].dt.year

    if "anio_creacion" in df:
        df["anio_creacion"] = pd.to_numeric(df["anio_creacion"], errors="coerce")

    if "dias_en_estado" in df:
        df["dias_en_estado"] = pd.to_numeric(df["dias_en_estado"], errors="coerce")

    for col in ["comuna", "programa", "subprograma", "estado", "tipo_accion", "region"]:
        if col in df:
            df[col] = df[col].astype(str).str.strip()

    if "comuna" in df:
        df["provincia"] = df["comuna"].map(COMUNA_A_PROVINCIA).fillna("Sin Provincia")

    # Descarta la fila de "Totales" (subtotal, no es un proyecto real)
    if "nombre_proyecto" in df:
        df = df[df["nombre_proyecto"].astype(str).str.strip().str.lower() != "totales"]
    if "estado" in df:
        df = df[df["estado"].notna() & (df["estado"].astype(str).str.strip().str.lower() != "nan")]

    return df.reset_index(drop=True)


def main():
    if len(sys.argv) < 2:
        print("Uso: python parse_y_publicar.py <archivo.xls>")
        sys.exit(1)

    src = Path(sys.argv[1])
    if not src.exists():
        print(f"No existe el archivo: {src}")
        sys.exit(1)

    df = parse_file(src)

    # Respaldo del archivo original (referencia histórica / trazabilidad)
    today = datetime.now().strftime("%Y-%m-%d")
    backup_path = RAW_BACKUP_DIR / f"Listado_Proyectos_{today}.xls"
    backup_path.write_bytes(src.read_bytes())

    cols = [c for c in FIELDS_TO_PUBLISH if c in df.columns]
    df_pub = df[cols].copy()
    df_pub = df_pub.where(pd.notnull(df_pub), None)

    payload = {
        "fecha_actualizacion": today,
        "total_proyectos": len(df_pub),
        "proyectos": json.loads(df_pub.to_json(orient="records", force_ascii=False)),
    }

    out_path = DRIVE_UPLOAD_DIR / "proyectos.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"Archivo listo para subir a Drive: {out_path}")
    print(f"  ({len(df_pub)} proyectos, actualizado al {today})")
    print(f"Respaldo del Excel original guardado en: {backup_path}")
    print()
    print("Siguiente paso MANUAL: sube/reemplaza este archivo en tu carpeta de Drive")
    print("(usa 'Administrar versiones' o 'Subir nueva versión' para conservar el mismo")
    print("ID de archivo — así el enlace del dashboard nunca cambia).")
    print()
    print("Cuando termines, corre: ./scripts/publicar_semana.sh")
    print("para dejar el respaldo subido a GitHub automáticamente.")


if __name__ == "__main__":
    main()
