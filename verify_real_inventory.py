import os
import subprocess

# Try using psql via subprocess with PGPASSWORD
env = os.environ.copy()
env['PGPASSWORD'] = 'admin123'

# Try siga_suiza_2026
print("=== Consultando PostgreSQL: siga_suiza_2026 ===")
sql1 = "SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name;"
result = subprocess.run(
    ['psql', '-U', 'postgres', '-d', 'siga_suiza_2026', '-h', 'localhost',
     '-t', '-A', '-c', sql1],
    capture_output=True, text=True, env=env
)
print("STDOUT:", result.stdout)
print("STDERR:", result.stderr[:200] if result.stderr else "")
print("Return code:", result.returncode)

if result.stdout.strip():
    tables = [t.strip() for t in result.stdout.strip().split('\n') if t.strip()]
    print(f"Total tablas: {len(tables)}")
    for t in tables:
        print(f"  {t}")
    
    # Count
    sql2 = "SELECT COUNT(*) AS total_tablas FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';"
    count_result = subprocess.run(
        ['psql', '-U', 'postgres', '-d', 'siga_suiza_2026', '-h', 'localhost',
         '-t', '-A', '-c', sql2],
        capture_output=True, text=True, env=env
    )
    print(f"Conteo exacto: {count_result.stdout.strip()}")
    
    # Check specific tables
    print("\n=== Verificación de tablas específicas ===")
    specific_tables = [
        'periodos_academicos', 'programa_configuraciones', 'programa_unidades',
        'carga_lectiva', 'silabos', 'planes_trabajo_docente', 'tutorias',
        'horarios_periodo', 'matricula_detalles', 'beneficios_estudiante',
        'registros_practicas', 'resoluciones_convalidacion', 'convalidaciones_detalle',
        'solicitudes_tramites', 'tesoreria_conceptos', 'tesoreria_pagos',
        'tesoreria_configuracion', 'core_role_permissions', 'perfiles_personal'
    ]
    
    all_tables = set(tables)
    print(f"Total tablas reales en BD: {len(all_tables)}")
    print("Resultados por tabla específica:")
    for table_name in specific_tables:
        exists = table_name in all_tables
        status = "EXISTE" if exists else "NO EXISTE"
        print(f"  {table_name}: {status}")
    
    # Foreign keys
    print("\n=== Claves foráneas ===")
    sql3 = "SELECT tc.table_name || '|' || kcu.column_name || '|' || ccu.table_name || '|' || ccu.column_name FROM information_schema.table_constraints AS tc JOIN information_schema.key_column_usage AS kcu ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema JOIN information_schema.constraint_column_usage AS ccu ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public';"
    fk_result = subprocess.run(
        ['psql', '-U', 'postgres', '-d', 'siga_suiza_2026', '-h', 'localhost',
         '-t', '-A', '-c', sql3],
        capture_output=True, text=True, env=env
    )
    fk_lines = [l.strip() for l in fk_result.stdout.strip().split('\n') if l.strip()]
    print(f"Total FKs: {len(fk_lines)}")
    for line in fk_lines[:10]:  # Show first 10
        parts = line.split('|')
        if len(parts) == 4:
            print(f"  {parts[0]}.{parts[1]} -> {parts[2]}.{parts[3]}")
    if len(fk_lines) > 10:
        print(f"  ... y {len(fk_lines) - 10} más")
else:
    print("No se obtuvieron tablas - intentando siga_core...")
    
    # Try siga_core
    sql1 = "SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name;"
    result = subprocess.run(
        ['psql', '-U', 'postgres', '-d', 'siga_core', '-h', 'localhost',
         '-t', '-A', '-c', sql1],
        capture_output=True, text=True, env=env
    )
    print("siga_core STDOUT:", result.stdout[:500])
    print("siga_core STDERR:", result.stderr[:200] if result.stderr else "")