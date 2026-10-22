-- =====================================================
-- BASE DE DATOS: SISTEMA DE GESTION DE PACIENTES
-- PostgreSQL - pgAdmin 4
-- =====================================================


-- =====================================================
-- 1. TABLA: OPERADOR
-- =====================================================

CREATE TABLE IF NOT EXISTS operador (
    id_operador SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    apellido VARCHAR(100) NOT NULL,
    fecha_nacimiento DATE NOT NULL,
    celular VARCHAR(20),
    carnet_identidad VARCHAR(20) UNIQUE NOT NULL,
    cargo VARCHAR(100) NOT NULL DEFAULT 'Operador',
    fecha_registro TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario VARCHAR(50) UNIQUE NOT NULL,
    contrasena VARCHAR(255) NOT NULL
);


-- =====================================================
-- 2. TABLA: ADMINISTRADOR
-- =====================================================

CREATE TABLE IF NOT EXISTS administrador (
    id_administrador SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    apellido VARCHAR(100) NOT NULL,
    fecha_nacimiento DATE NOT NULL,
    celular VARCHAR(20),
    carnet_identidad VARCHAR(20) UNIQUE NOT NULL,
    cargo VARCHAR(100) NOT NULL DEFAULT 'Administrador',
    fecha_registro TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario VARCHAR(50) UNIQUE NOT NULL,
    contrasena VARCHAR(255) NOT NULL
);


-- =====================================================
-- 3. TABLA: SERVICIO TECNICO
-- =====================================================

CREATE TABLE IF NOT EXISTS servicio_tecnico (
    id_tecnico SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    apellido VARCHAR(100) NOT NULL,
    fecha_nacimiento DATE NOT NULL,
    celular VARCHAR(20),
    carnet_identidad VARCHAR(20) UNIQUE NOT NULL,
    cargo VARCHAR(100) NOT NULL DEFAULT 'Servicio tecnico',
    fecha_registro TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario VARCHAR(50) UNIQUE NOT NULL,
    contrasena VARCHAR(255) NOT NULL
);


-- =====================================================
-- 4. TABLA: PACIENTE
-- El operador registra al paciente.
-- =====================================================

CREATE TABLE IF NOT EXISTS paciente (
    id_paciente SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    apellido VARCHAR(100) NOT NULL,
    fecha_nacimiento DATE NOT NULL,
    celular VARCHAR(20),
    carnet_identidad VARCHAR(20) UNIQUE NOT NULL,
    fecha_registro TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    mes_gestacion SMALLINT NOT NULL
        CHECK (mes_gestacion BETWEEN 1 AND 9),

    -- Identifica al operador que registro al paciente
    id_operador INTEGER NOT NULL,

    -- Relacion con la tabla operador
    CONSTRAINT fk_paciente_operador
        FOREIGN KEY (id_operador)
        REFERENCES operador(id_operador)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);


-- =====================================================
-- 5. INDICE PARA BUSCAR PACIENTES POR OPERADOR
-- =====================================================

CREATE INDEX IF NOT EXISTS idx_paciente_operador
ON paciente(id_operador);


-- =====================================================
-- 6. TABLA: SESION_TOKEN
-- Token alfanumerico creado por Python que aparece en la URL.
-- =====================================================

CREATE TABLE IF NOT EXISTS sesion_token (
    token VARCHAR(64) PRIMARY KEY,
    rol VARCHAR(20) NOT NULL
        CHECK (rol IN ('administrador', 'operador', 'tecnico')),
    id_usuario INTEGER NOT NULL,
    creado TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expira TIMESTAMP NOT NULL
);


-- =====================================================
-- 7. TABLA: LECTURA_DOPPLER
-- Frecuencia cardiaca fetal (latidos por minuto).
-- =====================================================

CREATE TABLE IF NOT EXISTS lectura_doppler (
    id_lectura BIGSERIAL PRIMARY KEY,
    id_paciente INTEGER NOT NULL
        REFERENCES paciente(id_paciente) ON DELETE CASCADE,
    fcf SMALLINT NOT NULL,
    fecha TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- =====================================================
-- 8. TABLA: LECTURA_TOCODINAMOMETRO
-- Presion de la contraccion uterina (escala 0 a 100).
-- =====================================================

CREATE TABLE IF NOT EXISTS lectura_tocodinamometro (
    id_lectura BIGSERIAL PRIMARY KEY,
    id_paciente INTEGER NOT NULL
        REFERENCES paciente(id_paciente) ON DELETE CASCADE,
    presion NUMERIC(5,1) NOT NULL,
    fecha TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- =====================================================
-- 9. INDICES PARA LAS LECTURAS
-- =====================================================

CREATE INDEX IF NOT EXISTS idx_doppler_pac ON lectura_doppler(id_paciente, fecha);
CREATE INDEX IF NOT EXISTS idx_toco_pac ON lectura_tocodinamometro(id_paciente, fecha);
CREATE INDEX IF NOT EXISTS idx_doppler_fecha ON lectura_doppler(fecha);
CREATE INDEX IF NOT EXISTS idx_toco_fecha ON lectura_tocodinamometro(fecha);


-- =====================================================
-- 10. TABLA: REPORTE_TECNICO
-- Informes del servicio tecnico sobre los sensores.
-- =====================================================

CREATE TABLE IF NOT EXISTS reporte_tecnico (
    id_reporte SERIAL PRIMARY KEY,
    id_tecnico INTEGER NOT NULL
        REFERENCES servicio_tecnico(id_tecnico) ON DELETE RESTRICT,
    sensor VARCHAR(30) NOT NULL
        CHECK (sensor IN ('Doppler fetal', 'Tocodinamometro', 'Otro')),
    tipo VARCHAR(30) NOT NULL
        CHECK (tipo IN ('Falla', 'Cambio de componente', 'Mantenimiento')),
    que_fallo TEXT NOT NULL,
    por_que TEXT NOT NULL,
    componente_cambiado TEXT,
    acciones TEXT,
    fecha TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- =====================================================
-- 11. TABLA: PACIENTE_ACTIVA
-- A que paciente se le asignan los datos que el equipo
-- envia por WiFi (una sola fila: el equipo es uno solo).
-- =====================================================

CREATE TABLE IF NOT EXISTS paciente_activa (
    id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    id_paciente INTEGER
        REFERENCES paciente(id_paciente) ON DELETE SET NULL,
    id_operador INTEGER
        REFERENCES operador(id_operador) ON DELETE SET NULL,
    actualizado TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- =====================================================
-- FIN DE LA CREACION DE TABLAS
-- =====================================================
