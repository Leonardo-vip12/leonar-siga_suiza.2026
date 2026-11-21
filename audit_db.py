import os
import sys
sys.path.insert(0, '.')

# Use the project's own database module
from siga_backend.modules.mod_usuarios.database import Base, engine as usuarios_engine
from sqlalchemy import inspect

inspector = inspect(usuarios_engine)
tables = inspector.get_table_names()
print(f'Table names from mod-usuarios models:')
for t in tables:
    print(f'  {t}')

# Get columns for each table
for t in tables:
    columns = inspector.get_columns(t)
    print(f'\n  {t}: {len(columns)} columns')
    for c in columns:
        print(f'    - {c.get("name", "?")}: {c.get("type", "?")}')