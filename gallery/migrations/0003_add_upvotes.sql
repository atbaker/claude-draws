-- Add upvote functionality to submissions
-- Each submission starts with 1 upvote (the submitter's)
ALTER TABLE submissions ADD COLUMN upvote_count INTEGER NOT NULL DEFAULT 1;

-- Update existing pending submissions to have 1 upvote
UPDATE submissions SET upvote_count = 1 WHERE status = 'pending';

-- Drop old index (will be replaced by composite index)
DROP INDEX IF EXISTS idx_submissions_status_created;

-- Create composite index for efficient upvote-based queue queries
-- Ordered by: status, upvote_count DESC (most upvoted first), created_at ASC (FIFO tiebreaker)
CREATE INDEX idx_submissions_queue_order ON submissions(status, upvote_count DESC, created_at ASC);
