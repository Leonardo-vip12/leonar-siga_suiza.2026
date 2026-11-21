from sqlalchemy import create_engine, text

engine = create_engine('postgresql+psycopg2://postgres:admin123@localhost:5432/siga_suiza_2026')
with engine.connect() as conn:
    result = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name"))
    tables = result.fetchall()
    print(f'Total tablas: {len(tables)}')
    for t in tables:
        print(f'  {t[0]}')
    
    # Count
    result2 = conn.execute(text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'"))
    count = result2.fetchone()[0]
    print(f'Conteo exacto: {count}')
    
    # Foreign keys
    result3 = conn.execute(text("""
        SELECT tc.table_name, kcu.column_name, 
               ccu.table_name AS foreign_table_name, 
               ccu.column_name AS foreign_column_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage AS ccu
            ON ccu.constraint_name = tc.constraint_name
            AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
        AND tc.table_schema = 'public'
        ORDER BY tc.table_name
    """))
    fks = result3.fetchall()
    print(f'Total FKs: {len(fks)}')
    for fk in fks[:15]:
        print(f'  {fk[0]}.{fk[1]} -> {fk[2]}.{fk[3]}')
    if len(fks) > 15:
        print(f'  ... y {len(fks) - 15} más')