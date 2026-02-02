-- V4: Add IP address tracking to page_views table
-- This migration adds an ip_address column to track visitor IPs

-- Add ip_address column to page_views
ALTER TABLE page_views ADD COLUMN IF NOT EXISTS ip_address VARCHAR(45);

-- Create index for faster IP-based queries
CREATE INDEX IF NOT EXISTS idx_page_views_ip_address ON page_views(ip_address);
