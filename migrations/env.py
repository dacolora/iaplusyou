import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db  # noqa: E402

db.asegurar_carpeta()  # checkout limpio: data/ todavía no existe

config = context.config
if config.config_file_name is not None:
    # disable_existing_loggers=False: por defecto fileConfig APAGA todo logger
    # que ya exista (creatv.organico, creatv.tareas.*…). En el worker, alembic
    # corre antes de importar la app, pero en los tests la migración corre en
    # el mismo proceso que el resto de la suite y dejaba mudos los loggers de
    # los módulos ya importados (caplog vacío).
    fileConfig(config.config_file_name, disable_existing_loggers=False)
config.set_main_option("sqlalchemy.url", db.url())
target_metadata = db.metadata


def run_migrations_offline():
    context.configure(url=db.url(), target_metadata=target_metadata, literal_binds=True,
                      dialect_opts={"paramstyle": "named"}, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}),
                                     prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
