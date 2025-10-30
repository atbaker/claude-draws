-- Create submissions table for Claude Draws form submissions
CREATE TABLE submissions (
  id TEXT PRIMARY KEY,
  prompt TEXT NOT NULL,
  email TEXT,
  status TEXT NOT NULL DEFAULT 'pending', -- pending/processing/completed/failed
  created_at TEXT NOT NULL,
  completed_at TEXT,
  artwork_id TEXT,
  error_message TEXT
);

-- Index for efficiently querying pending submissions
CREATE INDEX idx_submissions_status_created ON submissions(status, created_at);

-- Index for looking up submissions by artwork_id
CREATE INDEX idx_submissions_artwork_id ON submissions(artwork_id) WHERE artwork_id IS NOT NULL;
