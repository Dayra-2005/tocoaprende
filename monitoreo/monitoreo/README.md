# Sistema de Monitoreo Materno-Fetal (FastAPI + PostgreSQL)

1. En pgAdmin ejecuta `database.sql` dentro de tu base de datos.
2. Abre `app.py` y cambia `DB_CONFIG` (nombre de tu base y contraseña) y `API_KEY_DISPOSITIVO`.
3. En la terminal de VS Code:
   pip install -r requirements.txt
   python app.py
4. Abre http://127.0.0.1:8000  (la primera vez te pide crear el administrador principal).

Equipo real: POST a /api/lectura con header X-API-KEY y JSON {"id_paciente":1,"fcf":142,"toco":35.5}
Con dominio: usa HTTPS (el token va en la URL).
