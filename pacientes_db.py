import pandas as pd
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def calcular_edad(fecha_nac):
    try:
        if hasattr(fecha_nac, 'year'):
            hoy = datetime.now()
            return hoy.year - fecha_nac.year - (
                (hoy.month, hoy.day) < (fecha_nac.month, fecha_nac.day)
            )
        if isinstance(fecha_nac, str):
            for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%m/%d/%Y']:
                try:
                    dt = datetime.strptime(fecha_nac, fmt)
                    hoy = datetime.now()
                    return hoy.year - dt.year
                except: pass
    except: pass
    return None

def cargar_base_datos(ruta_excel):
    pacientes = {}
    try:
        logger.info(f"Intentando cargar: {ruta_excel}")
        logger.info(f"Archivo existe: {os.path.exists(ruta_excel)}")

        # Leer hojas
        df = pd.read_excel(ruta_excel, sheet_name="Pacientes", dtype=str)

        # Obtener lista de todas las hojas disponibles
        excel_file = pd.ExcelFile(ruta_excel)
        todas_las_hojas = excel_file.sheet_names
        logger.info(f"📋 HOJAS DISPONIBLES EN EL EXCEL: {todas_las_hojas}")

        # Intentar leer citas con diferentes nombres de hoja
        citas_df = None
        sheet_nombres_a_intentar = ["RegistroCitasPaciente", "REGISTRODECITASPACIENTE", "Registro Citas Paciente", "registrodecitaspaciente", "Registro de Citas Paciente"]

        for sheet_name in sheet_nombres_a_intentar:
            logger.info(f"🔍 Intentando cargar hoja: '{sheet_name}'")
            if sheet_name in todas_las_hojas:
                try:
                    citas_df = pd.read_excel(ruta_excel, sheet_name=sheet_name, dtype=str)
                    logger.info(f"✅ EXITO: Hoja de citas encontrada: '{sheet_name}'")
                    logger.info(f"📊 Filas en hoja de citas: {len(citas_df)}")
                    logger.info(f"📊 Columnas en hoja de citas: {list(citas_df.columns)}")
                    break
                except Exception as e:
                    logger.error(f"❌ Error cargando '{sheet_name}': {e}")
            else:
                logger.warning(f"⚠️ Hoja '{sheet_name}' NO está en el Excel")

        if citas_df is None or citas_df.empty:
            logger.warning("⚠️ No se encontró hoja de citas válida, procederá sin historial")
            citas_df = pd.DataFrame()

        logger.info(f"Filas cargadas: {len(df)}")
        logger.info(f"Columnas Pacientes: {list(df.columns)}")

        # Mapear columnas por coincidencia flexible (ignorar tildes)
        col_map = {}
        for col in df.columns:
            # Buscar coincidencias sin tildes/caracteres especiales
            col_clean = col.lower().replace("número", "numero").replace("ó", "o").replace("í", "i").replace("á", "a").replace("é", "e").replace("ü", "u").replace("ñ", "n").replace("•", "")

            if "numero" in col_clean and "identificacion" in col_clean:
                col_map["cedula"] = col
            elif "primer nombre" in col_clean:
                col_map["primer_nombre"] = col
            elif "segundo nombre" in col_clean:
                col_map["segundo_nombre"] = col
            elif "primer apellido" in col_clean:
                col_map["primer_apellido"] = col
            elif "segundo apellido" in col_clean:
                col_map["segundo_apellido"] = col
            elif "tipo" in col_clean and "identificacion" in col_clean:
                col_map["tipo_identificacion"] = col
            elif "sexo" in col_clean and "biologico" in col_clean:
                col_map["sexo"] = col
            elif "identidad" in col_clean and "genero" in col_clean:
                col_map["identidad_genero"] = col
            elif "estado civil" in col_clean:
                col_map["estado_civil"] = col
            elif "fecha" in col_clean and "nacimiento" in col_clean:
                col_map["fecha_nacimiento"] = col
            elif col == "EPS (*)":
                col_map["eps"] = col
            elif "nivel" in col_clean and "educativo" in col_clean:
                col_map["nivel_educativo"] = col
            elif "vinculacion" in col_clean:
                col_map["tipo_vinculacion"] = col
            elif "nacionalidad" in col_clean:
                col_map["nacionalidad"] = col
            elif "ocupacion" in col_clean:
                col_map["ocupacion"] = col
            elif "etnia" in col_clean and "comunidad" not in col_clean:
                col_map["etnia"] = col
            elif "comunidad" in col_clean and "etnica" in col_clean:
                col_map["comunidad_etnica"] = col
            elif "categoria" in col_clean and "discapacidad" in col_clean:
                col_map["categoria_discapacidad"] = col
            elif "telefono" in col_clean and "no." in col_clean:
                col_map["telefono"] = col
            elif "correo" in col_clean or "email" in col_clean:
                col_map["email"] = col
            elif "pais" in col_clean:
                col_map["pais"] = col
            elif "dpto" in col_clean or "departamento" in col_clean:
                col_map["departamento"] = col
            elif "ciudad" in col_clean:
                col_map["ciudad"] = col
            elif "zona" in col_clean and "territorial" in col_clean:
                col_map["zona_territorial"] = col
            elif "direccion" in col_clean and "casilla" not in col_clean and "principal" not in col_clean:
                col_map["direccion"] = col
            elif col == "nombre_plan":
                col_map["plan"] = col

        logger.info(f"Columnas mapeadas: {col_map}")

        for _, row in df.iterrows():
            try:
                # Obtener cédula
                cedula_col = col_map.get("cedula")
                if not cedula_col:
                    logger.warning("No se encontró columna de cédula, saltando fila")
                    continue

                cedula_raw = row.get(cedula_col, "")
                if pd.isna(cedula_raw) or str(cedula_raw).strip() == "":
                    continue

                # Limpiar cédula - quitar decimales si tiene
                cedula = str(cedula_raw).strip().replace(".0", "").replace(" ", "")

                logger.info(f"Procesando cédula: {cedula}")

                # Citas del paciente
                citas = []
                if not citas_df.empty:
                    if "identificacion" in citas_df.columns:
                        try:
                            # Normalizar la cédula para comparación
                            cedula_clean = str(cedula).strip()
                            citas = citas_df[
                                citas_df["identificacion"].astype(str).str.strip().str.replace(" ", "") == cedula_clean.replace(" ", "")
                            ].to_dict('records')
                            if citas:
                                logger.info(f"✅ {len(citas)} citas encontradas para cédula {cedula}")
                            else:
                                logger.debug(f"Sin citas para cédula {cedula}")
                        except Exception as e:
                            logger.error(f"Error al buscar citas para {cedula}: {e}")
                            citas = []
                    else:
                        logger.warning(f"Columna 'identificacion' no encontrada en hoja de citas. Columnas: {list(citas_df.columns)}")
                else:
                    logger.debug("DataFrame de citas está vacío")

                # Ordenar citas por fecha descendente si existe columna fecha
                if citas:
                    try:
                        citas = sorted(citas,
                            key=lambda x: pd.to_datetime(x.get("fecha_cita", ""), errors='coerce'),
                            reverse=True)
                    except Exception as e:
                        logger.warning(f"No se pudieron ordenar citas: {e}")

                # Procesar citas para el historial
                historial_citas = []
                for c in citas:
                    historial_citas.append({
                        "estado": str(c.get("estado", "")).strip(),
                        "tipo": str(c.get("tipo", "")).strip(),
                        "fecha": str(c.get("fecha_cita", "")).strip(),
                        "profesional": str(c.get("profesional", "")).strip(),
                        "id": str(c.get("id", "")).strip()
                    })

                ultima_cita = None
                if historial_citas:
                    ultima_cita = historial_citas[0]

                nombre = " ".join(filter(None, [
                    str(row.get(col_map.get("primer_nombre", "Primer Nombre (*)"), "") or "").strip(),
                    str(row.get(col_map.get("segundo_nombre", "Segundo Nombre"), "") or "").strip(),
                    str(row.get(col_map.get("primer_apellido", "Primer Apellido (*)"), "") or "").strip(),
                    str(row.get(col_map.get("segundo_apellido", "Segundo Apellido"), "") or "").strip()
                ]))

                # Planes del paciente
                planes_str = str(row.get(col_map.get("plan", "nombre_plan"), "") or "").strip()

                pacientes[cedula] = {
                    # Identificación
                    "nombre": nombre,
                    "cedula": cedula,
                    "tipo_identificacion": str(row.get(col_map.get("tipo_identificacion", ""), "") or ""),

                    # Datos demográficos
                    "edad": calcular_edad(row.get(col_map.get("fecha_nacimiento", "Fecha de Nacimiento (*)"))),
                    "sexo": str(row.get(col_map.get("sexo", "Sexo Biológico (*)"), "") or ""),
                    "identidad_genero": str(row.get(col_map.get("identidad_genero", ""), "") or ""),
                    "estado_civil": str(row.get(col_map.get("estado_civil", "Estado civil (*)"), "") or ""),

                    # Datos personales
                    "nacionalidad": str(row.get(col_map.get("nacionalidad", ""), "") or ""),
                    "ocupacion": str(row.get(col_map.get("ocupacion", ""), "") or ""),
                    "etnia": str(row.get(col_map.get("etnia", ""), "") or ""),
                    "comunidad_etnica": str(row.get(col_map.get("comunidad_etnica", ""), "") or ""),
                    "categoria_discapacidad": str(row.get(col_map.get("categoria_discapacidad", ""), "") or ""),
                    "nivel_educativo": str(row.get(col_map.get("nivel_educativo", ""), "") or ""),

                    # Ubicación
                    "pais": str(row.get(col_map.get("pais", ""), "") or ""),
                    "departamento": str(row.get(col_map.get("departamento", ""), "") or ""),
                    "ciudad": str(row.get(col_map.get("ciudad", "Ciudad (*)"), "") or ""),
                    "zona_territorial": str(row.get(col_map.get("zona_territorial", ""), "") or ""),
                    "direccion": str(row.get(col_map.get("direccion", "Dirección (*)"), "") or ""),

                    # Contacto
                    "telefono": str(row.get(col_map.get("telefono", "No. Telefono"), "") or ""),
                    "email": str(row.get(col_map.get("email", "Correo electrónico"), "") or ""),

                    # Salud
                    "eps": str(row.get(col_map.get("eps", "EPS (*)"), "") or ""),
                    "plan": planes_str,
                    "planes": [p.strip() for p in planes_str.split(",") if p.strip()] if planes_str else [],
                    "tipo_vinculacion": str(row.get(col_map.get("tipo_vinculacion", "Tipo de vinculación (*)"), "") or ""),

                    # Historial
                    "ultima_cita": ultima_cita,
                    "historial_citas": historial_citas
                }

            except Exception as e:
                logger.error(f"Error procesando fila: {e}")
                import traceback
                logger.error(traceback.format_exc())
                continue

        logger.info(f"Total pacientes cargados: {len(pacientes)}")
        logger.info(f"Cedulas: {list(pacientes.keys())}")
        return pacientes

    except Exception as e:
        logger.error(f"ERROR CRITICO cargando Excel: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {}


def buscar_cedula_flexible(cedula_buscada, pacientes_db):
    """Buscar cedula con flexibilidad ante errores de deteccion."""
    cedula_str = str(cedula_buscada).strip()

    # Busqueda exacta primero
    if cedula_str in pacientes_db:
        return pacientes_db[cedula_str]

    logger.info(f"Busqueda flexible para: {cedula_str} (len: {len(cedula_str)})")

    # Probar quitando UN digito de cada posicion
    for i in range(len(cedula_str)):
        sin_digito = cedula_str[:i] + cedula_str[i+1:]
        if sin_digito in pacientes_db:
            logger.info(f"Cedula encontrada sin digito en posicion {i}: {cedula_str} = {sin_digito}")
            return pacientes_db[sin_digito]

    # Si tiene 9 digitos, probar agregando un cero al inicio
    if len(cedula_str) == 9:
        con_cero = "0" + cedula_str
        if con_cero in pacientes_db:
            logger.info(f"Cedula encontrada con cero al inicio: {cedula_str} = {con_cero}")
            return pacientes_db[con_cero]

    logger.warning(f"No se encontro variacion de: {cedula_str}")
    return None
