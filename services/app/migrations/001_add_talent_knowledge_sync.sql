ALTER TABLE talent_pool
    ADD COLUMN IF NOT EXISTS knowledge_sync_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS knowledge_document_id VARCHAR(100),
    ADD COLUMN IF NOT EXISTS knowledge_chunk_count INTEGER,
    ADD COLUMN IF NOT EXISTS knowledge_sync_error VARCHAR(500),
    ADD COLUMN IF NOT EXISTS knowledge_synced_at TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_talent_pool_knowledge_sync_status'
    ) THEN
        ALTER TABLE talent_pool
            ADD CONSTRAINT ck_talent_pool_knowledge_sync_status
            CHECK (knowledge_sync_status IN ('pending', 'syncing', 'success', 'failed'));
    END IF;
END
$$;
