-- ============================================================
-- MoTA Scholarship Management System — PostgreSQL Schema
-- Version: 1.0.0 | Date: 2026-09-26
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ============================================================
-- ENUM TYPES
-- ============================================================

CREATE TYPE user_role AS ENUM (
    'APPLICANT',
    'REVIEWER',
    'SENIOR_REVIEWER',
    'SCHEME_ADMIN',
    'SUPER_ADMIN'
);

CREATE TYPE application_status AS ENUM (
    'DRAFT',
    'SUBMITTED',
    'AI_REVIEW',
    'DEFICIENT',
    'MANUAL_SCRUTINY',
    'APPROVED',
    'REJECTED',
    'DISBURSED'
);

CREATE TYPE document_status AS ENUM (
    'PENDING',
    'PROCESSING',
    'VERIFIED',
    'FLAGGED',
    'REJECTED'
);

CREATE TYPE gender AS ENUM ('MALE', 'FEMALE', 'OTHER', 'PREFER_NOT_TO_SAY');

CREATE TYPE document_type AS ENUM (
    'AADHAAR_CARD',
    'CASTE_CERTIFICATE',
    'INCOME_CERTIFICATE',
    'MARKSHEET_10',
    'MARKSHEET_12',
    'MARKSHEET_UG',
    'MARKSHEET_PG',
    'ADMISSION_LETTER',
    'DOMICILE_CERTIFICATE',
    'BANK_PASSBOOK',
    'PASSPORT',
    'PHOTOGRAPH',
    'OTHER'
);

CREATE TYPE disbursement_status AS ENUM (
    'PENDING',
    'INITIATED',
    'SUCCESS',
    'FAILED'
);

-- ============================================================
-- TABLE: users
-- ============================================================
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    full_name       VARCHAR(255) NOT NULL,
    email           VARCHAR(255) UNIQUE,
    mobile          VARCHAR(15) UNIQUE NOT NULL,
    password_hash   TEXT,
    role            user_role NOT NULL DEFAULT 'APPLICANT',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    is_verified     BOOLEAN NOT NULL DEFAULT FALSE,
    aadhaar_hash    TEXT,
    date_of_birth   DATE,
    gender          gender,
    state_code      CHAR(2),
    district        VARCHAR(100),
    address_line1   TEXT,
    address_line2   TEXT,
    pincode         CHAR(6),
    profile_photo_url TEXT,
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_mobile ON users(mobile);
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_state ON users(state_code);

-- ============================================================
-- TABLE: otp_verifications
-- ============================================================
CREATE TABLE otp_verifications (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mobile      VARCHAR(15) NOT NULL,
    otp_hash    TEXT NOT NULL,
    purpose     VARCHAR(50) NOT NULL,
    attempts    SMALLINT NOT NULL DEFAULT 0,
    is_used     BOOLEAN NOT NULL DEFAULT FALSE,
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_otp_mobile ON otp_verifications(mobile, expires_at);

-- ============================================================
-- TABLE: schemes
-- ============================================================
CREATE TABLE schemes (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code                    VARCHAR(50) UNIQUE NOT NULL,
    name                    VARCHAR(255) NOT NULL,
    description             TEXT,
    ministry                VARCHAR(255) DEFAULT 'Ministry of Tribal Affairs',
    is_active               BOOLEAN NOT NULL DEFAULT FALSE,
    application_open_date   DATE NOT NULL,
    application_close_date  DATE NOT NULL,
    academic_year           VARCHAR(9) NOT NULL,
    min_age                 SMALLINT,
    max_age                 SMALLINT,
    max_annual_income       NUMERIC(12, 2),
    eligible_categories     TEXT[] DEFAULT '{"ST"}',
    eligible_genders        gender[],
    eligible_states         CHAR(2)[],
    min_percentage          NUMERIC(5, 2),
    eligible_levels         TEXT[],
    eligible_institutions   TEXT[],
    required_documents      document_type[] NOT NULL DEFAULT '{}',
    optional_documents      document_type[] DEFAULT '{}',
    merit_weights           JSONB NOT NULL DEFAULT '{"academic_score": 0.7, "income_score": 0.3}',
    total_seats             INTEGER,
    female_quota_pct        NUMERIC(5, 2) DEFAULT 30.0,
    state_wise_quota        JSONB,
    fellowship_amount       NUMERIC(12, 2),
    contingency_amount      NUMERIC(12, 2),
    duration_months         SMALLINT,
    ai_confidence_threshold NUMERIC(5, 2) DEFAULT 75.0,
    created_by              UUID REFERENCES users(id),
    updated_by              UUID REFERENCES users(id),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_schemes_active ON schemes(is_active, application_close_date);

-- ============================================================
-- TABLE: applications
-- ============================================================
CREATE SEQUENCE application_seq START 1;

CREATE TABLE applications (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    application_number      VARCHAR(30) UNIQUE NOT NULL,
    scheme_id               UUID NOT NULL REFERENCES schemes(id) ON DELETE RESTRICT,
    applicant_id            UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    assigned_reviewer_id    UUID REFERENCES users(id),
    status                  application_status NOT NULL DEFAULT 'DRAFT',
    academic_year           VARCHAR(9) NOT NULL,
    applicant_name          VARCHAR(255) NOT NULL,
    applicant_dob           DATE NOT NULL,
    applicant_gender        gender NOT NULL,
    state_code              CHAR(2) NOT NULL,
    district                VARCHAR(100),
    category                VARCHAR(10) NOT NULL DEFAULT 'ST',
    aadhaar_last4           CHAR(4),
    institution_name        VARCHAR(500),
    institution_state       CHAR(2),
    course_name             VARCHAR(255),
    course_level            VARCHAR(50),
    admission_year          SMALLINT,
    current_year            SMALLINT,
    percentage_10           NUMERIC(5, 2),
    percentage_12           NUMERIC(5, 2),
    percentage_ug           NUMERIC(5, 2),
    percentage_pg           NUMERIC(5, 2),
    annual_family_income    NUMERIC(12, 2),
    bank_account_number     TEXT,
    bank_ifsc               VARCHAR(11),
    bank_name               VARCHAR(255),
    overall_ai_score        NUMERIC(5, 2),
    ai_processing_done      BOOLEAN NOT NULL DEFAULT FALSE,
    ai_flags                JSONB DEFAULT '[]',
    merit_score             NUMERIC(8, 4),
    merit_rank              INTEGER,
    submitted_at            TIMESTAMPTZ,
    ai_reviewed_at          TIMESTAMPTZ,
    manually_reviewed_at    TIMESTAMPTZ,
    approved_at             TIMESTAMPTZ,
    rejected_at             TIMESTAMPTZ,
    disbursed_at            TIMESTAMPTZ,
    rejection_reason        TEXT,
    reviewer_notes          TEXT,
    deficiency_notes        JSONB DEFAULT '[]',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_scheme_applicant UNIQUE (scheme_id, applicant_id)
);

CREATE INDEX idx_apps_scheme ON applications(scheme_id);
CREATE INDEX idx_apps_applicant ON applications(applicant_id);
CREATE INDEX idx_apps_status ON applications(status);
CREATE INDEX idx_apps_reviewer ON applications(assigned_reviewer_id);
CREATE INDEX idx_apps_merit ON applications(scheme_id, merit_rank) WHERE status = 'APPROVED';

-- ============================================================
-- TABLE: documents
-- ============================================================
CREATE TABLE documents (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    application_id      UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    uploader_id         UUID NOT NULL REFERENCES users(id),
    document_type       document_type NOT NULL,
    original_filename   VARCHAR(500) NOT NULL,
    storage_key         TEXT NOT NULL UNIQUE,
    storage_bucket      VARCHAR(100) NOT NULL,
    file_size_bytes     BIGINT NOT NULL,
    mime_type           VARCHAR(100) NOT NULL,
    checksum_sha256     CHAR(64) NOT NULL,
    status              document_status NOT NULL DEFAULT 'PENDING',
    version             SMALLINT NOT NULL DEFAULT 1,
    extracted_text      TEXT,
    extracted_fields    JSONB DEFAULT '{}',
    confidence_score    NUMERIC(5, 2),
    match_score         NUMERIC(5, 2),
    ocr_engine          VARCHAR(50),
    ocr_processed_at    TIMESTAMPTZ,
    ai_flags            JSONB DEFAULT '[]',
    reviewed_by         UUID REFERENCES users(id),
    reviewed_at         TIMESTAMPTZ,
    reviewer_notes      TEXT,
    is_tampered         BOOLEAN DEFAULT FALSE,
    is_blurry           BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_docs_application ON documents(application_id);
CREATE INDEX idx_docs_type ON documents(document_type);
CREATE INDEX idx_docs_status ON documents(status);

-- ============================================================
-- TABLE: audit_logs
-- ============================================================
CREATE TABLE audit_logs (
    id          BIGSERIAL PRIMARY KEY,
    actor_id    UUID REFERENCES users(id),
    actor_role  user_role,
    action      VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id   UUID NOT NULL,
    old_value   JSONB,
    new_value   JSONB,
    ip_address  INET,
    user_agent  TEXT,
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX idx_audit_actor ON audit_logs(actor_id);
CREATE INDEX idx_audit_time ON audit_logs(created_at DESC);

-- ============================================================
-- TABLE: notifications
-- ============================================================
CREATE TABLE notifications (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    application_id  UUID REFERENCES applications(id) ON DELETE SET NULL,
    channel         VARCHAR(20) NOT NULL,
    subject         VARCHAR(500),
    body            TEXT NOT NULL,
    is_read         BOOLEAN NOT NULL DEFAULT FALSE,
    sent_at         TIMESTAMPTZ,
    delivered_at    TIMESTAMPTZ,
    failed_at       TIMESTAMPTZ,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_notif_user ON notifications(user_id, is_read);

-- ============================================================
-- TABLE: disbursements
-- ============================================================
CREATE TABLE disbursements (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    application_id      UUID NOT NULL REFERENCES applications(id),
    amount              NUMERIC(12, 2) NOT NULL,
    disbursement_type   VARCHAR(50) NOT NULL,
    status              disbursement_status NOT NULL DEFAULT 'PENDING',
    pfms_transaction_id VARCHAR(100),
    payment_date        DATE,
    utr_number          VARCHAR(50),
    bank_account_number TEXT,
    bank_ifsc           VARCHAR(11),
    initiated_by        UUID REFERENCES users(id),
    initiated_at        TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    failure_reason      TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_disb_application ON disbursements(application_id);
CREATE INDEX idx_disb_status ON disbursements(status);

-- ============================================================
-- TABLE: merit_lists
-- ============================================================
CREATE TABLE merit_lists (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scheme_id       UUID NOT NULL REFERENCES schemes(id),
    academic_year   VARCHAR(9) NOT NULL,
    generated_by    UUID REFERENCES users(id),
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_final        BOOLEAN NOT NULL DEFAULT FALSE,
    total_applicants INTEGER,
    total_selected  INTEGER,
    list_data       JSONB NOT NULL DEFAULT '[]',
    published_at    TIMESTAMPTZ,
    notes           TEXT,
    CONSTRAINT uq_merit_scheme_year UNIQUE (scheme_id, academic_year, is_final)
);

-- ============================================================
-- TRIGGERS
-- ============================================================
CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_updated_at_users
    BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
CREATE TRIGGER set_updated_at_applications
    BEFORE UPDATE ON applications FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
CREATE TRIGGER set_updated_at_documents
    BEFORE UPDATE ON documents FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
CREATE TRIGGER set_updated_at_schemes
    BEFORE UPDATE ON schemes FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

-- ============================================================
-- FUNCTIONS
-- ============================================================
CREATE OR REPLACE FUNCTION generate_application_number(p_scheme_code TEXT, p_year TEXT)
RETURNS TEXT AS $$
BEGIN
    RETURN 'MOTA/' || p_scheme_code || '/' || p_year || '/' ||
           LPAD(NEXTVAL('application_seq')::TEXT, 6, '0');
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- SEED DATA
-- ============================================================
INSERT INTO users (full_name, email, mobile, role, is_active, is_verified)
VALUES ('System Administrator', 'admin@mota.gov.in', '9999999999', 'SUPER_ADMIN', TRUE, TRUE);

INSERT INTO schemes (
    code, name, description, is_active,
    application_open_date, application_close_date, academic_year,
    max_annual_income, required_documents, merit_weights,
    total_seats, fellowship_amount, contingency_amount, duration_months,
    ai_confidence_threshold
) VALUES
(
    'NFST',
    'National Fellowship for Scheduled Tribe Students',
    'Provides financial assistance to ST students pursuing M.Phil and PhD programs.',
    TRUE, '2026-09-01', '2026-12-31', '2026-2027',
    600000.00,
    ARRAY['AADHAAR_CARD','CASTE_CERTIFICATE','INCOME_CERTIFICATE','MARKSHEET_UG','ADMISSION_LETTER']::document_type[],
    '{"academic_score": 0.70, "income_score": 0.20, "special_category": 0.10}',
    1000, 31000.00, 10000.00, 24, 78.0
),
(
    'NOS',
    'National Overseas Scholarship',
    'Scholarship for ST students pursuing Masters or PhD abroad.',
    TRUE, '2026-09-01', '2026-11-30', '2026-2027',
    800000.00,
    ARRAY['AADHAAR_CARD','CASTE_CERTIFICATE','INCOME_CERTIFICATE','MARKSHEET_UG','MARKSHEET_PG','PASSPORT','ADMISSION_LETTER']::document_type[],
    '{"academic_score": 0.75, "income_score": 0.15, "language_score": 0.10}',
    100, 1430000.00, 450000.00, 36, 80.0
);
