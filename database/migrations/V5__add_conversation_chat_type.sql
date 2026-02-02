-- V5: Add chat_type to conversations table
-- This migration adds a chat_type column to distinguish between 'afl' and 'resume' chats

-- Add chat_type column to conversations (default to 'afl' for existing records)
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS chat_type VARCHAR(20) NOT NULL DEFAULT 'afl';

-- Create index for faster queries by chat type
CREATE INDEX IF NOT EXISTS idx_conversations_chat_type ON conversations(chat_type);
