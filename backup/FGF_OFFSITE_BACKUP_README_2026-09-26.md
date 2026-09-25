# FGF Off-Site Backup & Recovery Kit — 2026-09-26

Purpose: create a local copy that survives Supabase pausing, migration, deletion, or account loss.

Back up:
1. PostgreSQL roles, schema and data.
2. Supabase Storage bucket fgf-video-transcripts.
3. This GitHub repository.
4. Save the resulting archive on a separate local/cloud location.

Prerequisites:
- Supabase CLI
- Docker Desktop for database dump
- Supabase database password
- Project access

Set SUPABASE_DB_URL to the Session Pooler connection string from Supabase Dashboard > Connect, then run backup/backup_fgf_database.bat.

Run backup/backup_fgf_storage.bat to copy the transcript Storage bucket.

Zip the generated backup folders and save the ZIP outside Supabase and outside GitHub.

Restore to a new Supabase project using restore_fgf_database.bat, then recreate the private Storage bucket and copy the saved Storage files back.

NEVER put service-role keys, database passwords, GitHub tokens or LLM API keys into this repository or backup archive.

Current checkpoint:
Project qdoixzfkkmvzjfkhzups
Database ~16 MB
Storage 342 objects / ~3.20 MB
